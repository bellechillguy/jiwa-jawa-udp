from __future__ import annotations

import json
import queue
import random
import socket
import threading
import time
import zlib
from dataclasses import dataclass
from typing import Any

Address = tuple[str, int]


class DeliveryError(TimeoutError):
    pass


@dataclass
class Received:
    payload: dict[str, Any]
    address: Address
    sequence: int


class ReliableUDP:
    """Kanal pesan andal berbasis UDP dengan ACK, CRC, dan retransmisi.

    Satu socket dapat berbicara dengan beberapa peer. Nomor urut dan deteksi
    duplikat disimpan per peer supaya retransmisi tidak menjalankan aksi dua kali.
    """

    VERSION = 1
    MAX_PACKET = 60_000

    def __init__(
        self,
        bind: Address,
        *,
        timeout: float = 0.25,
        max_retries: int = 40,
        drop_rate: float = 0.0,
        socket_timeout: float = 0.1,
    ) -> None:
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind(bind)
        self.socket.settimeout(socket_timeout)
        self.address = self.socket.getsockname()
        self.timeout = timeout
        self.max_retries = max_retries
        self.drop_rate = drop_rate
        self._next_sequence: dict[Address, int] = {}
        self._seen: dict[Address, set[int]] = {}
        self._acks: dict[tuple[Address, int], threading.Event] = {}
        self._ack_lock = threading.Lock()
        self._send_lock = threading.Lock()
        self._inbox: queue.Queue[Received] = queue.Queue()
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._receive_loop, name="reliable-udp", daemon=True)
        self._thread.start()

    @staticmethod
    def _canonical(value: dict[str, Any]) -> bytes:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    @classmethod
    def _encode(cls, body: dict[str, Any]) -> bytes:
        packet = {**body, "crc32": zlib.crc32(cls._canonical(body)) & 0xFFFFFFFF}
        encoded = cls._canonical(packet)
        if len(encoded) > cls.MAX_PACKET:
            raise ValueError("Pesan UDP terlalu besar.")
        return encoded

    @classmethod
    def _decode(cls, raw: bytes) -> dict[str, Any] | None:
        try:
            packet = json.loads(raw.decode("utf-8"))
            checksum = int(packet.pop("crc32"))
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None
        if zlib.crc32(cls._canonical(packet)) & 0xFFFFFFFF != checksum:
            return None
        if packet.get("version") != cls.VERSION:
            return None
        return packet

    @staticmethod
    def _peer(address: tuple[Any, ...]) -> Address:
        return str(address[0]), int(address[1])

    def _send_raw(self, raw: bytes, address: Address) -> None:
        if self.drop_rate and random.random() < self.drop_rate:
            return
        self.socket.sendto(raw, address)

    def send(self, payload: dict[str, Any], address: Address) -> int:
        address = self._peer(address)
        with self._send_lock:
            sequence = self._next_sequence.get(address, 1)
            self._next_sequence[address] = sequence + 1
        body = {"version": self.VERSION, "kind": "data", "sequence": sequence, "payload": payload}
        raw = self._encode(body)
        acknowledged = threading.Event()
        key = address, sequence
        with self._ack_lock:
            self._acks[key] = acknowledged
        try:
            for _attempt in range(self.max_retries):
                if self._closed.is_set():
                    raise DeliveryError("Socket sudah ditutup.")
                self._send_raw(raw, address)
                if acknowledged.wait(self.timeout):
                    return sequence
            raise DeliveryError(f"Pesan {sequence} ke {address[0]}:{address[1]} tidak mendapat ACK.")
        finally:
            with self._ack_lock:
                self._acks.pop(key, None)

    def _send_ack(self, sequence: int, address: Address) -> None:
        body = {"version": self.VERSION, "kind": "ack", "sequence": sequence}
        self._send_raw(self._encode(body), address)

    def _receive_loop(self) -> None:
        while not self._closed.is_set():
            try:
                raw, source = self.socket.recvfrom(self.MAX_PACKET + 1)
            except socket.timeout:
                continue
            except OSError:
                break
            address = self._peer(source)
            packet = self._decode(raw)
            if packet is None:
                continue
            try:
                sequence = int(packet["sequence"])
            except (KeyError, TypeError, ValueError):
                continue
            if packet.get("kind") == "ack":
                with self._ack_lock:
                    event = self._acks.get((address, sequence))
                if event:
                    event.set()
                continue
            if packet.get("kind") != "data" or not isinstance(packet.get("payload"), dict):
                continue
            self._send_ack(sequence, address)
            seen = self._seen.setdefault(address, set())
            if sequence in seen:
                continue
            seen.add(sequence)
            if len(seen) > 4096:
                floor = max(seen) - 2048
                self._seen[address] = {item for item in seen if item >= floor}
            self._inbox.put(Received(packet["payload"], address, sequence))

    def receive(self, timeout: float | None = None) -> Received:
        return self._inbox.get(timeout=timeout)

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        self.socket.close()
        self._thread.join(timeout=1.0)

    def __enter__(self) -> "ReliableUDP":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


def parse_address(value: str) -> Address:
    try:
        host, port = value.rsplit(":", 1)
        return host, int(port)
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Alamat harus berbentuk host:port, bukan {value!r}") from exc


def format_address(address: Address) -> str:
    return f"{address[0]}:{address[1]}"
