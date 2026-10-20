"""Manual end-to-end image check; requires an existing SHENNONG_API_KEY."""

import base64
import json
import os
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import Handler


def main() -> None:
    if not os.environ.get("SHENNONG_API_KEY", "").strip():
        raise SystemExit("请先在后端环境设置 SHENNONG_API_KEY。")
    image_path = Path(__file__).with_name("wheat-leaf-rust.jpg")
    image = "data:image/jpeg;base64," + base64.b64encode(image_path.read_bytes()).decode("ascii")
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({"image": image, "question": "这片小麦叶子有什么可见异常？"}).encode("utf-8")
        req = request.Request(
            f"http://127.0.0.1:{server.server_port}/api/ask-image",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=220) as response:
                result = json.load(response)
                print("HTTP:", response.status)
        except error.HTTPError as exc:
            result = json.load(exc)
            print("HTTP:", exc.code)
        print("图片观察:", result.get("observation", ""))
        print("神农回答:", result.get("answer", ""))
        print("错误:", result.get("error", ""))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


if __name__ == "__main__":
    main()
