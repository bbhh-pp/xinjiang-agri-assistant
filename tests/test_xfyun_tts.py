import base64
import json
import os
import unittest
from unittest.mock import patch

import xfyun_tts


class FakeSocket:
    def __init__(self, inbound):
        self.inbound = bytearray(inbound)
        self.sent = bytearray()

    def settimeout(self, _timeout):
        pass

    def sendall(self, data):
        self.sent.extend(data)

    def recv(self, count):
        if not self.inbound:
            return b""
        result = self.inbound[:count]
        del self.inbound[:count]
        return bytes(result)

    def close(self):
        pass


class FakeSslContext:
    def wrap_socket(self, sock, server_hostname):
        self.server_hostname = server_hostname
        return sock


class XfyunTtsTests(unittest.TestCase):
    def test_synthesis_handshake_request_and_audio_response(self):
        audio = b"fake-mp3-data"
        frame_body = json.dumps({
            "code": 0,
            "message": "success",
            "data": {"audio": base64.b64encode(audio).decode(), "status": 2},
        }).encode()
        inbound = b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n\r\n"
        inbound += bytes([0x81, len(frame_body)]) + frame_body
        fake_socket = FakeSocket(inbound)
        fake_context = FakeSslContext()
        env = {
            "XFYUN_TTS_APP_ID": "test-app-id",
            "XFYUN_TTS_API_KEY": "test-api-key",
            "XFYUN_TTS_API_SECRET": "test-api-secret",
        }
        with patch.dict(os.environ, env, clear=False):
            with patch.object(xfyun_tts.socket, "create_connection", return_value=fake_socket):
                with patch.object(xfyun_tts.ssl, "create_default_context", return_value=fake_context):
                    result = xfyun_tts.synthesize_uyghur("بۇغداي")
        self.assertEqual(result, audio)
        self.assertEqual(fake_context.server_hostname, "tts-api.xfyun.cn")
        self.assertIn(b"GET /v2/tts?", fake_socket.sent)
        self.assertIn(b"Upgrade: websocket", fake_socket.sent)
        _http_header, frame = bytes(fake_socket.sent).split(b"\r\n\r\n", 1)
        length = frame[1] & 0x7F
        offset = 2
        if length == 126:
            length = int.from_bytes(frame[offset:offset + 2], "big")
            offset += 2
        mask = frame[offset:offset + 4]
        offset += 4
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(frame[offset:offset + length]))
        decoded_payload = json.loads(payload)
        self.assertEqual(decoded_payload["common"]["app_id"], "test-app-id")
        self.assertEqual(decoded_payload["data"]["text"], base64.b64encode("بۇغداي".encode()).decode())

    def test_missing_credentials_fails_without_network(self):
        with patch.dict(os.environ, {
            "XFYUN_TTS_APP_ID": "", "XFYUN_TTS_API_KEY": "", "XFYUN_TTS_API_SECRET": ""
        }, clear=False):
            with patch.object(xfyun_tts.socket, "create_connection") as connect:
                with self.assertRaises(xfyun_tts.TTSFailure):
                    xfyun_tts.synthesize_uyghur("بۇغداي")
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
