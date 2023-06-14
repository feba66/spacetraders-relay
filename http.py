
import datetime
from http import HTTPStatus
import http.server
import json
import socketserver
import sys
from threading import Lock
import requests
from feba_ratelimit import BurstyLimiter, Limiter

SERVER_URL = "https://api.spacetraders.io/v2"
session = requests.session()

@BurstyLimiter(Limiter(2, 1.05), Limiter(10, 10.5))
def req_and_log(url: str, method: str, data=None, json=None):
    r = session.request(method, SERVER_URL + url, data=data, json=json)
    return r


class myHandler(http.server.BaseHTTPRequestHandler):
    req_lock = Lock()

    def req(self, path, method, data=None, json=None):
        with self.req_lock:  # thanks to threads we need to tidy up a bit with this lock
            if "Authorization" in self.headers.keys():
                session.headers.update({"Authorization": self.headers.get("Authorization")})
            elif "Authorization" in session.headers:
                session.headers.pop("Authorization")
            r = req_and_log(path, method, data, json)
            while r.status_code in [408, 429, 503]:
                r = req_and_log(path, method, data, json)
        self.send_response(r.status_code)
        self.send_header("content-type", r.headers["content-type"])
        self.send_header("content-length", r.headers["content-length"])
        self.end_headers()
        self.wfile.write(r.content)

    def get_body(self):
        content_len = int(self.headers.get('Content-Length'))
        return json.loads(self.rfile.read(content_len).decode())
    
    def do_GET(self):
        self.req(self.path, "get")
    def do_POST(self):
        post_body = self.get_body()
        self.req(self.path, "post",json=post_body)
    def do_PATCH(self):
        post_body = self.get_body()
        self.req(self.path, "post",json=post_body)

IP = ""
PORT = 8000
with socketserver.ThreadingTCPServer((IP, PORT), myHandler) as httpd:
    print("serving at port", PORT)
    httpd.serve_forever()
