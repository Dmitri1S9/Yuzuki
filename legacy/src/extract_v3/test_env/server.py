"""Local test environment for manually evaluating the model. Serves the static page + data.json, and
proxies POST /api/chat to Ollama (avoids CORS entirely: the page's fetch stays same-origin).

Run: python -m extract_v3.test_env.server
Then open http://localhost:8899 in a browser on this machine.
"""
import http.server
import json
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
PORT = 8899
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(HERE), **kwargs)

    def do_POST(self):
        if self.path != "/api/chat":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = urllib.request.Request(OLLAMA_URL, data=body, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = resp.read()
                status = resp.status
        except urllib.error.HTTPError as e:
            # Ollama's own error body (e.g. bad options, model not found) -- forward it, don't swallow it.
            data = e.read() or json.dumps({"error": f"HTTP {e.code}: {e.reason}"}).encode("utf-8")
            status = e.code
        except Exception as e:
            data = json.dumps({"error": f"{type(e).__name__}: {e}"}).encode("utf-8")
            status = 502
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        if self.path == "/api/chat":  # only log the interesting requests, not every static-file GET
            print(f"[{self.log_date_time_string()}] {fmt % args}")


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Test env: http://localhost:{PORT}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
