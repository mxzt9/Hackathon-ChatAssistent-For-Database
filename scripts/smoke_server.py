"""Быстрая проверка работающего сервера: python scripts/smoke_server.py."""

import argparse
import json
from urllib.request import urlopen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    for path in ("/", "/widget", "/assets/widget.js", "/api/health"):
        with urlopen(args.url.rstrip("/") + path, timeout=10) as response:
            assert response.status == 200, path
            if path == "/api/health":
                print(json.loads(response.read()))
    print("Сервер и виджет доступны")


if __name__ == "__main__":
    main()
