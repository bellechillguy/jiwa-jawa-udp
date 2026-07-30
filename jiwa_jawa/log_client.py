from __future__ import annotations

import json
import queue
import socket
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable

from .protocol import Address


class RaftLogClient:
    """Pengirim log asinkron dengan outbox lokal dan deduplikasi event_id."""

    def __init__(self, nodes: Iterable[Address], outbox: str | Path) -> None:
        self.nodes = list(nodes)
        self.outbox = Path(outbox)
        self.ack_file = self.outbox.with_suffix(self.outbox.suffix + ".acked")
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._closed = threading.Event()
        self._acked = self._load_acked()
        self._load_pending()
        self._thread = threading.Thread(target=self._run, name="raft-log-client", daemon=True)
        self._thread.start()

    def _load_acked(self) -> set[str]:
        if not self.ack_file.exists():
            return set()
        return {line.strip() for line in self.ack_file.read_text(encoding="utf-8").splitlines() if line.strip()}

    def _load_pending(self) -> None:
        if not self.outbox.exists():
            return
        for line in self.outbox.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("event_id") not in self._acked:
                self._queue.put(event)

    def submit(self, event_type: str, **fields: Any) -> str:
        event = {
            "event_id": str(uuid.uuid4()),
            "type": event_type,
            "timestamp": time.time(),
            **fields,
        }
        self.outbox.parent.mkdir(parents=True, exist_ok=True)
        with self.outbox.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            handle.flush()
        self._queue.put(event)
        return event["event_id"]

    def _mark_acked(self, event_id: str) -> None:
        if event_id in self._acked:
            return
        self._acked.add(event_id)
        with self.ack_file.open("a", encoding="utf-8") as handle:
            handle.write(event_id + "\n")

    def _deliver(self, event: dict[str, Any]) -> bool:
        if not self.nodes:
            return False
        request = json.dumps({"rpc": "client_append", "event": event}, separators=(",", ":")).encode()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.35)
        try:
            for _ in range(5):
                for node in self.nodes:
                    sock.sendto(request, node)
                deadline = time.monotonic() + 0.35
                while time.monotonic() < deadline:
                    try:
                        raw, _ = sock.recvfrom(16_384)
                    except socket.timeout:
                        break
                    try:
                        response = json.loads(raw.decode())
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        continue
                    if response.get("rpc") == "log_ack" and response.get("event_id") == event["event_id"]:
                        return True
            return False
        finally:
            sock.close()

    def _run(self) -> None:
        while not self._closed.is_set():
            try:
                event = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            if event["event_id"] in self._acked:
                continue
            if self._deliver(event):
                self._mark_acked(event["event_id"])
            elif not self._closed.wait(0.8):
                self._queue.put(event)

    def close(self) -> None:
        self._closed.set()
        self._thread.join(timeout=2.0)


class NullLogClient:
    def submit(self, _event_type: str, **_fields: Any) -> str:
        return ""

    def close(self) -> None:
        pass

