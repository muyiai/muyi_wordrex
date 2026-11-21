"""开发用静态服务器：提供 pipeline/out/publish（run.py publish 生成，data/ 是数据、media/ 是插画和录音）。

- 带 CORS 头：浏览器里的 weweb 页面在另一个端口，跨域
- 支持 JSONP：weweb 在浏览器里把 wx.request 实现成 JSONP（?callback=xxx），返回 xxx(<json>)

用法：python3 pipeline/tools/serve.py [端口，默认 8787]
"""
import re
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

BUILD = Path(__file__).resolve().parent.parent / "out" / "publish"
CALLBACK_RE = re.compile(r"^[A-Za-z_$][\w$.]*$")


class DevHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def do_GET(self):
        parts = urlsplit(self.path)
        callback = parse_qs(parts.query).get("callback", [""])[0]
        if not callback:
            return super().do_GET()
        if not CALLBACK_RE.match(callback):
            return self.send_error(400, "bad callback")
        file = (BUILD / parts.path.lstrip("/")).resolve()
        if BUILD not in file.parents or not file.is_file():
            return self.send_error(404)
        body = f"{callback}({file.read_text(encoding='utf-8')})".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/javascript; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8787
    server = ThreadingHTTPServer(("0.0.0.0", port), partial(DevHandler, directory=str(BUILD)))
    print(f"数据服务：http://localhost:{port}  （{BUILD}）")
    server.serve_forever()
