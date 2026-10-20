"""Fine-tune the merged Uyghur Whisper checkpoint with labeled local audio.

Manifest columns: audio,text,split,speaker_id (speaker_id optional).
Each clip should be a single utterance of at most 30 seconds.
"""

import argparse
import csv
import gc
import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from uyghur_asr import MODEL_DIR, SAMPLE_RATE


MAX_CLIP_SECONDS = 30


@dataclass(frozen=True)
class Row:
    audio: Path
    text: str
    split: str
    speaker_id: str


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", value)).strip()


def read_manifest(path: Path) -> list[Row]:
    if not path.is_file():
        raise ValueError(f"找不到标注文件：{path}")
    rows = []
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"audio", "text", "split"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("CSV 必须包含 audio,text,split 列；建议增加 speaker_id 列。")
        for line, item in enumerate(reader, start=2):
            name = (item.get("audio") or "").strip()
            caption = normalize_text(item.get("text") or "")
            split = (item.get("split") or "").strip().lower()
            speaker_id = (item.get("speaker_id") or "").strip()
            if not name or not caption or split not in {"train", "validation"}:
                raise ValueError(f"第 {line} 行缺少音频/文字，或 split 不是 train/validation。")
            audio = Path(name)
            if not audio.is_absolute():
                audio = path.parent / audio
            audio = audio.resolve()
            if not audio.is_file():
                raise ValueError(f"第 {line} 行音频不存在：{audio}")
            if audio.suffix.lower() not in {".mp3", ".wav"}:
                raise ValueError(f"第 {line} 行只支持 MP3/WAV：{audio}")
            rows.append(Row(audio, caption, split, speaker_id))
    train = [row for row in rows if row.split == "train"]
    validation = [row for row in rows if row.split == "validation"]
    if not train or not validation:
        raise ValueError("训练集和验证集至少各需要一条带文字的录音。")
    if len({row.audio for row in rows}) != len(rows):
        raise ValueError("同一音频重复出现在 CSV 中，请去重。")
    train_speakers = {row.speaker_id for row in train if row.speaker_id}
    val_speakers = {row.speaker_id for row in validation if row.speaker_id}
    overlap = train_speakers & val_speakers
    if overlap:
        raise ValueError(f"训练集和验证集有相同说话人：{', '.join(sorted(overlap))}")
    return rows


def load_audio(path: Path):
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly

    try:
        info = sf.info(path)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"无法解码音频：{path}") from exc
    if info.duration > MAX_CLIP_SECONDS:
        raise ValueError(f"音频超过 {MAX_CLIP_SECONDS} 秒，请先切成短句：{path}")
    try:
        audio, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    except (RuntimeError, ValueError) as exc:
        raise ValueError(f"无法解码音频：{path}") from exc
    if sample_rate <= 0 or not len(audio) or len(audio) / sample_rate > MAX_CLIP_SECONDS:
        raise ValueError(f"音频为空或超过 {MAX_CLIP_SECONDS} 秒，请先切成短句：{path}")
    mono = audio.mean(axis=1)
    if sample_rate != SAMPLE_RATE:
        divisor = math.gcd(sample_rate, SAMPLE_RATE)
        mono = resample_poly(mono, SAMPLE_RATE // divisor, sample_rate // divisor)
    return np.asarray(mono, dtype=np.float32)


def edit_distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def error_rates(references: list[str], predictions: list[str]) -> tuple[float, float]:
    word_errors = word_count = char_errors = char_count = 0
    for reference, prediction in zip(references, predictions, strict=True):
        ref, pred = normalize_text(reference), normalize_text(prediction)
        ref_words, pred_words = ref.split(), pred.split()
        word_errors += edit_distance(ref_words, pred_words)
        word_count += len(ref_words)
        char_errors += edit_distance(list(ref), list(pred))
        char_count += len(ref)
    return word_errors / max(1, word_count), char_errors / max(1, char_count)


def train(args, rows: list[Row]) -> None:
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from torch.utils.data import DataLoader, Dataset
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    if not torch.cuda.is_available():
        raise RuntimeError("训练需要 CUDA GPU。当前未检测到可用显卡；可在带 GPU 的电脑或云环境运行。")
    if not (args.model_dir / "model.safetensors").is_file():
        raise RuntimeError("基础模型未下载。请先运行 .\\install-asr.ps1。")

    torch.manual_seed(args.seed)
    processor = WhisperProcessor.from_pretrained(args.model_dir)
    processor.tokenizer.set_prefix_tokens(language=args.language, task="transcribe")
    base = WhisperForConditionalGeneration.from_pretrained(args.model_dir)
    base.config.forced_decoder_ids = None
    base.config.suppress_tokens = []
    base.config.use_cache = False
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model = get_peft_model(base, LoraConfig(
        # Whisper receives input_features, while PEFT's generic Seq2Seq wrapper
        # forwards input_ids; leave task_type unset for this audio model.
        target_modules=["q_proj", "v_proj"],
        r=args.rank,
        lora_alpha=args.rank * 2,
        lora_dropout=0.05,
    )).cuda()
    model.print_trainable_parameters()

    class SpeechDataset(Dataset):
        def __init__(self, items):
            self.items = items

        def __len__(self):
            return len(self.items)

        def __getitem__(self, index):
            item = self.items[index]
            audio = load_audio(item.audio)
            features = processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_features[0]
            labels = processor.tokenizer(item.text).input_ids
            if labels and labels[0] == base.config.decoder_start_token_id:
                labels = labels[1:]
            return {"input_features": features, "labels": labels}

    def collate(batch):
        features = torch.stack([item["input_features"] for item in batch])
        labels = processor.tokenizer.pad(
            [{"input_ids": item["labels"]} for item in batch], return_tensors="pt"
        )
        token_ids = labels.input_ids.masked_fill(labels.attention_mask.ne(1), -100)
        return {"input_features": features, "labels": token_ids}

    train_rows = [row for row in rows if row.split == "train"]
    val_rows = [row for row in rows if row.split == "validation"]
    loader = DataLoader(SpeechDataset(train_rows), batch_size=args.batch_size, shuffle=True, collate_fn=collate)
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad), lr=args.learning_rate)
    scaler = torch.amp.GradScaler("cuda")
    best_wer = float("inf")
    adapter_dir = args.output / "best-adapter"
    args.output.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        optimizer.zero_grad(set_to_none=True)
        for step, batch in enumerate(loader, start=1):
            features = batch["input_features"].cuda(non_blocking=True)
            labels = batch["labels"].cuda(non_blocking=True)
            with torch.amp.autocast("cuda", dtype=torch.float16):
                loss = model(input_features=features, labels=labels).loss / args.gradient_accumulation
            scaler.scale(loss).backward()
            total_loss += loss.item() * args.gradient_accumulation
            if step % args.gradient_accumulation == 0 or step == len(loader):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                optimizer.zero_grad(set_to_none=True)

        model.eval()
        predictions = []
        with torch.inference_mode():
            for row in val_rows:
                audio = load_audio(row.audio)
                features = processor(audio, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_features.cuda()
                generated = base.generate(features, language=args.language, task="transcribe", max_new_tokens=225)
                predictions.append(processor.tokenizer.batch_decode(generated, skip_special_tokens=True)[0])
        wer, cer = error_rates([row.text for row in val_rows], predictions)
        print(f"epoch {epoch}: loss={total_loss / len(loader):.4f}, WER={wer:.3f}, CER={cer:.3f}", flush=True)
        if wer < best_wer:
            best_wer = wer
            model.save_pretrained(adapter_dir)
            processor.save_pretrained(adapter_dir)
            (args.output / "validation-results.txt").write_text(
                "\n".join(f"参考：{row.text}\n预测：{prediction}\n" for row, prediction in zip(val_rows, predictions, strict=True))
                + f"\nWER={wer:.4f}\nCER={cer:.4f}\n",
                encoding="utf-8",
            )

    del model, base, optimizer
    gc.collect()
    torch.cuda.empty_cache()
    if args.export_merged:
        print("正在合并最佳 LoRA 权重并导出完整模型……", flush=True)
        base = WhisperForConditionalGeneration.from_pretrained(args.model_dir)
        merged = PeftModel.from_pretrained(base, adapter_dir).merge_and_unload()
        merged.config.use_cache = True
        merged_dir = args.output / "merged"
        merged.save_pretrained(merged_dir, safe_serialization=True)
        processor.save_pretrained(merged_dir)
        print(f"完整模型：{merged_dir}")
    print(f"最佳验证 WER={best_wer:.3f}；LoRA：{adapter_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="微调 Rekipjan 的维语 Whisper 模型")
    parser.add_argument("--manifest", type=Path, required=True, help="UTF-8 CSV：audio,text,split,speaker_id")
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--output", type=Path, default=Path("training-output"))
    parser.add_argument("--language", default="uzbek", help="与原模型卡一致的语言 token")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--gradient-accumulation", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--validate-only", action="store_true", help="只检查标注 CSV 和路径，不加载模型")
    parser.add_argument("--no-export-merged", dest="export_merged", action="store_false")
    args = parser.parse_args()
    if min(args.epochs, args.batch_size, args.gradient_accumulation, args.rank) < 1 or args.learning_rate <= 0:
        parser.error("epochs/batch-size/gradient-accumulation/rank 和 learning-rate 必须大于 0")
    try:
        rows = read_manifest(args.manifest)
        print(f"标注有效：训练 {sum(row.split == 'train' for row in rows)} 条，验证 {sum(row.split == 'validation' for row in rows)} 条。")
        if not args.validate_only:
            train(args, rows)
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, f"错误：{exc}\n")


if __name__ == "__main__":
    main()
