from __future__ import annotations

import argparse
import json
import socket

from .protocol import parse_address


def main() -> None:
    parser = argparse.ArgumentParser(description="Lihat rating pemain Jiwa Jawa")
    parser.add_argument("--node", action="append", default=["127.0.0.1:9101", "127.0.0.1:9102", "127.0.0.1:9103"])
    args = parser.parse_args()
    nodes = [parse_address(item) for item in args.node]
    request = json.dumps({"rpc": "rating_query"}).encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(0.5)
    try:
        for _ in range(4):
            for node in nodes:
                sock.sendto(request, node)
            try:
                raw, _ = sock.recvfrom(60_000)
            except socket.timeout:
                continue
            response = json.loads(raw.decode())
            if response.get("rpc") != "rating_response":
                continue
            ratings = response.get("ratings", [])
            if not ratings:
                print("Belum ada pertandingan yang selesai.")
                return
            print(f"{'#':>3}  {'Pemain':<24} {'Rating':>7} {'Main':>5}")
            for row in ratings:
                print(f"{row['rank']:>3}  {row['player']:<24.24} {row['rating']:>7} {row['games']:>5}")
            return
        raise SystemExit("Klaster logger tidak menjawab.")
    finally:
        sock.close()


if __name__ == "__main__":
    main()
