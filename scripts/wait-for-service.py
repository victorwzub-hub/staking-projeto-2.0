from __future__ import annotations

import argparse
import socket
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("host")
    parser.add_argument("port", type=int)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((args.host, args.port), timeout=1):
                print(f"{args.host}:{args.port} is available")
                return
        except OSError:
            time.sleep(0.5)
    raise SystemExit(f"Timed out waiting for {args.host}:{args.port}")


if __name__ == "__main__":
    main()
