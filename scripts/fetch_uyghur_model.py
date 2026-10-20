"""Fetch the reviewed deployment model artifact and verify its pinned digest."""

from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.request import urlopen


MODEL_URL = "https://github.com/gheyret/uyghurasr_python/releases/download/tunji/uyghur_asr.onnx"
MODEL_SHA256 = "b9b053af61a1f1056672a58ab458ff52dccc2ea5664763937297d148eff80904"


def fetch(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix="uyghur-asr-", delete=False) as temp:
        temp_path = Path(temp.name)
        try:
            with urlopen(MODEL_URL, timeout=120) as response:
                while block := response.read(1024 * 1024):
                    digest.update(block)
                    temp.write(block)
            if digest.hexdigest() != MODEL_SHA256:
                raise RuntimeError("下载的识别模型 SHA-256 与项目固定值不符，已停止构建。")
            temp.flush()
            os.fsync(temp.fileno())
            os.replace(temp_path, destination)
        finally:
            temp_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    fetch(args.destination)
    print(f"维语 ONNX 模型已下载并校验：{args.destination}")


if __name__ == "__main__":
    main()
