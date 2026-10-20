"""Download only the merged model files into the project-local models folder."""

from huggingface_hub import snapshot_download

from uyghur_asr import MODEL_DIR, MODEL_ID


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=MODEL_ID,
        allow_patterns="whisper-small-uyghur-merged/*",
        local_dir=MODEL_DIR.parent,
    )
    if not (MODEL_DIR / "model.safetensors").is_file():
        raise RuntimeError("下载未完成：缺少 model.safetensors，请重试。")
    print(f"维语识别模型已保存到 {MODEL_DIR}")


if __name__ == "__main__":
    main()
