from __future__ import annotations

import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .board import GameState, InvalidAction
from .log_client import NullLogClient, RaftLogClient
from .protocol import Address, DeliveryError, ReliableUDP


class BaseController:
    def __init__(self, player: str, name: str) -> None:
        self.player = player
        self.name = name
        self._state: GameState | None = None
        self._state_lock = threading.Lock()
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.closed = threading.Event()

    def snapshot(self) -> GameState | None:
        with self._state_lock:
            return self._state.copy() if self._state else None

    def _set_state(self, state: GameState) -> None:
        with self._state_lock:
            self._state = state

    def notify(self, kind: str, message: str) -> None:
        self.events.put((kind, message))

    def submit(self, action: dict[str, Any]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError


class HostController(BaseController):
    def __init__(
        self,
        bind: Address,
        name: str,
        *,
        logger_nodes: list[Address] | None = None,
        data_dir: str | Path = ".jiwa-jawa",
        drop_rate: float = 0.0,
    ) -> None:
        super().__init__("A", name)
        self.endpoint = ReliableUDP(bind, drop_rate=drop_rate)
        self.peer: Address | None = None
        self.match_id = str(uuid.uuid4())
        self.actions: queue.Queue[dict[str, Any]] = queue.Queue()
        data_dir = Path(data_dir)
        self.logger = (
            RaftLogClient(logger_nodes, data_dir / f"outbox-{self.match_id}.jsonl")
            if logger_nodes
            else NullLogClient()
        )
        self._end_logged = False
        self._thread = threading.Thread(target=self._run, name="host-controller", daemon=True)
        self._thread.start()
        self.notify("status", f"Menunggu pemain B di {self.endpoint.address[0]}:{self.endpoint.address[1]}")

    def submit(self, action: dict[str, Any]) -> None:
        self.actions.put(action)

    def _send(self, payload: dict[str, Any]) -> None:
        if not self.peer:
            return
        try:
            self.endpoint.send(payload, self.peer)
        except DeliveryError as exc:
            self.notify("network", str(exc))

    def _broadcast_state(self) -> None:
        state = self.snapshot()
        if state:
            self._send({"type": "state", "match_id": self.match_id, "state": state.to_dict()})

    def _log_action(self, state: GameState, action: dict[str, Any]) -> None:
        self.logger.submit(
            "move_made" if action["type"] == "move" else "dam_taken",
            match_id=self.match_id,
            player=action["player"],
            player_name=state.players[action["player"]],
            action=action,
            board_version=state.version,
            piece_count={"A": state.piece_count("A"), "B": state.piece_count("B")},
        )
        if state.winner and not self._end_logged:
            self._end_logged = True
            self.logger.submit(
                "game_ended",
                match_id=self.match_id,
                player_a=state.players["A"],
                player_b=state.players["B"],
                winner=state.winner,
                winner_name=state.players[state.winner],
                moves=state.version,
            )

    def _apply(self, player: str, action: dict[str, Any], expected_version: int | None = None) -> None:
        state = self.snapshot()
        if state is None:
            self.notify("error", "Pemain B belum tersambung.")
            return
        if expected_version is not None and expected_version != state.version:
            self._send({"type": "error", "message": "Versi papan tertinggal. State terbaru dikirim ulang."})
            self._broadcast_state()
            return
        try:
            recorded = state.apply(player, action)
        except InvalidAction as exc:
            if player == "A":
                self.notify("error", str(exc))
            else:
                self._send({"type": "error", "message": str(exc)})
            return
        self._set_state(state)
        self._log_action(state, recorded)
        self.notify("state", f"Papan diperbarui ke versi {state.version}.")
        self._broadcast_state()

    def _handle_message(self, payload: dict[str, Any], address: Address) -> None:
        message_type = payload.get("type")
        if message_type == "join":
            if self.peer and address != self.peer:
                try:
                    self.endpoint.send({"type": "error", "message": "Meja sudah penuh."}, address)
                except DeliveryError:
                    pass
                return
            requested_name = str(payload.get("name", "Pemain B")).strip()[:32] or "Pemain B"
            self.peer = address
            state = self.snapshot()
            if state is None:
                state = GameState.initial(self.name, requested_name)
                self._set_state(state)
                self.logger.submit(
                    "game_started",
                    match_id=self.match_id,
                    player_a=self.name,
                    player_b=requested_name,
                )
                self.notify("status", f"{requested_name} tersambung. Permainan dimulai.")
            try:
                self.endpoint.send(
                    {
                        "type": "welcome",
                        "player": "B",
                        "match_id": self.match_id,
                        "state": state.to_dict(),
                    },
                    address,
                )
            except DeliveryError as exc:
                self.notify("network", str(exc))
        elif message_type == "action" and address == self.peer:
            self._apply("B", payload.get("action", {}), int(payload.get("expected_version", -1)))
        elif message_type == "resync" and address == self.peer:
            self._broadcast_state()
        elif message_type == "ping" and address == self.peer:
            self._send({"type": "pong", "time": payload.get("time")})

    def _run(self) -> None:
        while not self.closed.is_set():
            try:
                while True:
                    self._apply("A", self.actions.get_nowait())
            except queue.Empty:
                pass
            try:
                received = self.endpoint.receive(timeout=0.05)
            except queue.Empty:
                continue
            self._handle_message(received.payload, received.address)

    def close(self) -> None:
        if self.closed.is_set():
            return
        self.closed.set()
        self.endpoint.close()
        self.logger.close()
        self._thread.join(timeout=1.0)


class JoinController(BaseController):
    def __init__(
        self,
        host: Address,
        name: str,
        *,
        bind: Address = ("0.0.0.0", 0),
        drop_rate: float = 0.0,
    ) -> None:
        super().__init__("B", name)
        self.host = host
        self.endpoint = ReliableUDP(bind, drop_rate=drop_rate)
        self.actions: queue.Queue[dict[str, Any]] = queue.Queue()
        self.match_id: str | None = None
        self.connected = False
        self._thread = threading.Thread(target=self._run, name="join-controller", daemon=True)
        self._thread.start()
        self.notify("status", f"Menghubungi {host[0]}:{host[1]}...")

    def submit(self, action: dict[str, Any]) -> None:
        self.actions.put(action)

    def _send(self, payload: dict[str, Any]) -> bool:
        try:
            self.endpoint.send(payload, self.host)
            return True
        except DeliveryError as exc:
            self.notify("network", str(exc))
            return False

    def _run(self) -> None:
        if not self._send({"type": "join", "name": self.name, "client_version": 1}):
            return
        last_ping = time.monotonic()
        while not self.closed.is_set():
            try:
                action = self.actions.get_nowait()
            except queue.Empty:
                action = None
            if action is not None:
                state = self.snapshot()
                if state:
                    self._send({"type": "action", "expected_version": state.version, "action": action})
            if self.connected and time.monotonic() - last_ping > 2.0:
                self._send({"type": "ping", "time": time.time()})
                last_ping = time.monotonic()
            try:
                received = self.endpoint.receive(timeout=0.05)
            except queue.Empty:
                continue
            if received.address != self.host:
                continue
            payload = received.payload
            if payload.get("type") in {"welcome", "state"}:
                self.match_id = str(payload["match_id"])
                self._set_state(GameState.from_dict(payload["state"]))
                if not self.connected:
                    self.connected = True
                    self.notify("status", "Tersambung sebagai pemain B.")
                self.notify("state", "Papan disinkronkan.")
            elif payload.get("type") == "error":
                self.notify("error", str(payload.get("message", "Aksi ditolak.")))
            elif payload.get("type") == "pong":
                self.notify("network", "Koneksi aktif.")

    def close(self) -> None:
        if self.closed.is_set():
            return
        self.closed.set()
        self.endpoint.close()
        self._thread.join(timeout=1.0)
