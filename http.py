
import datetime
from http import HTTPStatus
import http.server
import json
import logging
import os
import socketserver
import sys
from threading import Lock
import threading
from dotenv import find_dotenv, load_dotenv
import requests
from feba_ratelimit import BurstyLimiter, Limiter

SERVER_URL = "https://api.spacetraders.io/v2"
session = requests.session()


@BurstyLimiter(Limiter(2, 1.05), Limiter(10, 10.5))
def req_and_log(url: str, method: str, data=None, json=None):
    r = session.request(method, SERVER_URL + url, data=data, json=json)
    return r


class Logger():
    logger: logging.Logger
    lock: Lock

    def __init__(self) -> None:
        self.lock = Lock()
        load_dotenv(find_dotenv(".env"))
        self.logger = logging.getLogger(
            "ST-Relay-" + str(threading.current_thread().native_id))
        self.logger.setLevel(logging.DEBUG)

        formatter = logging.Formatter("%(asctime)s - %(thread)d - %(name)s - %(levelname)s - %(message)s")

        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        fh = logging.FileHandler(os.getenv("WORKING_FOLDER") + "ST-Relay.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)

        ch.setFormatter(formatter)
        fh.setFormatter(formatter)
        self.logger.addHandler(fh)
        self.logger.addHandler(ch)

    def info(self, msg):
        with self.lock:
            self.logger.info(msg)

    def debug(self, msg):
        with self.lock:
            self.logger.debug(msg)

    def warning(self, msg):
        with self.lock:
            self.logger.warning(msg)

    def error(self, msg):
        with self.lock:
            self.logger.error(msg)

    def critical(self, msg):
        with self.lock:
            self.logger.critical(msg)


logger = Logger()


class myHandler(http.server.BaseHTTPRequestHandler):
    req_lock = Lock()

    def req(self, path: str, method: str, data=None, json=None):
        with self.req_lock:  # thanks to threads we need to tidy up a bit with this lock
            if "Authorization" in self.headers.keys():
                session.headers.update({"Authorization": self.headers.get("Authorization")})
            elif "Authorization" in session.headers:
                session.headers.pop("Authorization")
            r = req_and_log(path, method, data, json)
            while r.status_code in [408, 429, 503]:
                r = req_and_log(path, method, data, json)

        logger.info(f"{method.upper()} {path} {r.status_code}")
        self.send_response_only(r.status_code)
        self.send_header('Server', self.version_string())
        self.send_header('Date', self.date_time_string())
        self.send_header("content-type", r.headers["content-type"])
        if "content-length" in r.headers:
            self.send_header("content-length", r.headers["content-length"])
        self.end_headers()
        if "content-length" in r.headers:
            self.wfile.write(r.content)

    def get_body(self):
        content_len = int(self.headers.get('Content-Length'))
        return json.loads(self.rfile.read(content_len).decode())

    def do_GET(self):
        self.req(self.path, "get")

    def do_POST(self):
        post_body = self.get_body()
        self.req(self.path, "post", json=post_body)

    def do_PATCH(self):
        post_body = self.get_body()
        self.req(self.path, "patch", json=post_body)


if __name__ == "__main__":
    IP = ""
    PORT = 8000
    with socketserver.ThreadingTCPServer((IP, PORT), myHandler) as httpd:
        print("serving at port", PORT)
        httpd.serve_forever()
