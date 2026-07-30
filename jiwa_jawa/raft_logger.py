from __future__ import annotations

import argparse
import json
import random
import socket
import time
from pathlib import Path
from typing import Any

from .protocol import Address, format_address, parse_address
from .rating import RatingBook


class RaftNode:
    """Klaster Raft kecil untuk log permainan.

    Implementasi mencakup pemilihan leader, RequestVote, AppendEntries,
    pencocokan prefix log, commit mayoritas, serta state persisten.
    """

    def __init__(self, node_id: str, bind: Address, peers: dict[str, Address], data_dir: str | Path):
        self.node_id = node_id
        self.bind = bind
        self.peers = dict(peers)
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.data_dir / "raft-state.json"
        self.events_file = self.data_dir / "events.jsonl"
        self.rating = RatingBook(self.data_dir / "ratings.json")

        self.current_term = 0
        self.voted_for: str | None = None
        self.log: list[dict[str, Any]] = []
        self.commit_index = -1
        self.last_applied = -1
        self._load_state()

        self.role = "follower"
        self.leader_id: str | None = None
        self.votes: set[str] = set()
        self.next_index: dict[str, int] = {}
        self.match_index: dict[str, int] = {}
        self.waiting_clients: dict[str, set[Address]] = {}
        self.committed_events = self._load_committed_event_ids()
        self.running = True

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(bind)
        self.sock.settimeout(0.05)
        self.last_heartbeat = 0.0
        self._reset_election_deadline()

    @property
    def majority(self) -> int:
        return (len(self.peers) + 1) // 2 + 1

    def _load_state(self) -> None:
        if not self.state_file.exists():
            return
        value = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.current_term = int(value.get("current_term", 0))
        self.voted_for = value.get("voted_for")
        self.log = list(value.get("log", []))
        self.commit_index = min(int(value.get("commit_index", -1)), len(self.log) - 1)
        self.last_applied = min(int(value.get("last_applied", -1)), self.commit_index)

    def _save_state(self) -> None:
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "current_term": self.current_term,
                    "voted_for": self.voted_for,
                    "log": self.log,
                    "commit_index": self.commit_index,
                    "last_applied": self.last_applied,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.state_file)

    def _load_committed_event_ids(self) -> set[str]:
        result: set[str] = set()
        if not self.events_file.exists():
            return result
        for line in self.events_file.read_text(encoding="utf-8").splitlines():
            try:
                result.add(str(json.loads(line)["event_id"]))
            except (json.JSONDecodeError, KeyError):
                continue
        return result

    def _reset_election_deadline(self) -> None:
        self.election_deadline = time.monotonic() + random.uniform(0.75, 1.35)

    def _send(self, address: Address, message: dict[str, Any]) -> None:
        message = {**message, "sender": self.node_id, "term": self.current_term}
        self.sock.sendto(json.dumps(message, separators=(",", ":")).encode(), address)

    def _broadcast(self, message: dict[str, Any]) -> None:
        for address in self.peers.values():
            self._send(address, message)

    def _become_follower(self, term: int, leader: str | None = None) -> None:
        changed = term != self.current_term or self.role != "follower"
        self.role = "follower"
        self.current_term = term
        self.voted_for = None
        self.leader_id = leader
        self.votes.clear()
        self._reset_election_deadline()
        if changed:
            self._save_state()

    def _start_election(self) -> None:
        self.role = "candidate"
        self.current_term += 1
        self.voted_for = self.node_id
        self.votes = {self.node_id}
        self.leader_id = None
        self._reset_election_deadline()
        self._save_state()
        last_index = len(self.log) - 1
        last_term = self.log[last_index]["term"] if last_index >= 0 else 0
        self._broadcast({"rpc": "request_vote", "last_log_index": last_index, "last_log_term": last_term})
        if self.majority == 1:
            self._become_leader()

    def _become_leader(self) -> None:
        self.role = "leader"
        self.leader_id = self.node_id
        self.next_index = {peer: len(self.log) for peer in self.peers}
        self.match_index = {peer: -1 for peer in self.peers}
        self.last_heartbeat = 0.0
        self._send_append_entries()

    def _send_append_entries(self, only: str | None = None) -> None:
        targets = [only] if only else list(self.peers)
        for peer_id in targets:
            if peer_id not in self.peers:
                continue
            next_index = self.next_index.get(peer_id, len(self.log))
            prev_index = next_index - 1
            prev_term = self.log[prev_index]["term"] if prev_index >= 0 else 0
            self._send(
                self.peers[peer_id],
                {
                    "rpc": "append_entries",
                    "leader_id": self.node_id,
                    "prev_log_index": prev_index,
                    "prev_log_term": prev_term,
                    "entries": self.log[next_index:],
                    "leader_commit": self.commit_index,
                },
            )
        self.last_heartbeat = time.monotonic()

    def _candidate_log_is_current(self, index: int, term: int) -> bool:
        own_index = len(self.log) - 1
        own_term = self.log[own_index]["term"] if own_index >= 0 else 0
        return (term, index) >= (own_term, own_index)

    def _handle_vote_request(self, message: dict[str, Any], address: Address) -> None:
        candidate = str(message.get("sender"))
        grant = (
            (self.voted_for is None or self.voted_for == candidate)
            and self._candidate_log_is_current(
                int(message.get("last_log_index", -1)), int(message.get("last_log_term", 0))
            )
        )
        if grant:
            self.voted_for = candidate
            self._reset_election_deadline()
            self._save_state()
        self._send(address, {"rpc": "vote_response", "granted": grant})

    def _handle_append(self, message: dict[str, Any], address: Address) -> None:
        self.role = "follower"
        self.leader_id = str(message.get("leader_id"))
        self._reset_election_deadline()
        prev_index = int(message.get("prev_log_index", -1))
        prev_term = int(message.get("prev_log_term", 0))
        valid_prefix = prev_index == -1 or (
            prev_index < len(self.log) and int(self.log[prev_index]["term"]) == prev_term
        )
        if not valid_prefix:
            self._send(address, {"rpc": "append_response", "success": False, "match_index": -1})
            return
        entries = list(message.get("entries", []))
        insert_at = prev_index + 1
        changed = False
        for offset, entry in enumerate(entries):
            index = insert_at + offset
            if index < len(self.log) and self.log[index] != entry:
                self.log = self.log[:index]
            if index >= len(self.log):
                self.log.append(entry)
                changed = True
        leader_commit = int(message.get("leader_commit", -1))
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log) - 1)
            changed = True
        if changed:
            self._apply_commits()
            self._save_state()
        self._send(
            address,
            {"rpc": "append_response", "success": True, "match_index": prev_index + len(entries)},
        )

    def _advance_commit(self) -> None:
        for index in range(len(self.log) - 1, self.commit_index, -1):
            if int(self.log[index]["term"]) != self.current_term:
                continue
            replicated = 1 + sum(value >= index for value in self.match_index.values())
            if replicated >= self.majority:
                self.commit_index = index
                self._apply_commits()
                self._save_state()
                self._send_append_entries()
                break

    def _apply_commits(self) -> None:
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            event = self.log[self.last_applied]["event"]
            event_id = str(event["event_id"])
            if event_id not in self.committed_events:
                with self.events_file.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
                    handle.flush()
                self.committed_events.add(event_id)
                if event.get("type") == "game_ended":
                    self.rating.record(
                        str(event["match_id"]),
                        str(event["player_a"]),
                        str(event["player_b"]),
                        event.get("winner"),
                    )
            for client in self.waiting_clients.pop(event_id, set()):
                self._send(client, {"rpc": "log_ack", "event_id": event_id, "commit_index": self.last_applied})

    def _handle_client_append(self, message: dict[str, Any], address: Address) -> None:
        event = message.get("event")
        if not isinstance(event, dict) or not event.get("event_id"):
            return
        event_id = str(event["event_id"])
        if event_id in self.committed_events:
            self._send(address, {"rpc": "log_ack", "event_id": event_id, "commit_index": self.commit_index})
            return
        if self.role != "leader":
            leader = self.peers.get(self.leader_id or "")
            self._send(
                address,
                {"rpc": "redirect", "leader": format_address(leader) if leader else None},
            )
            return
        self.waiting_clients.setdefault(event_id, set()).add(address)
        existing = next((i for i, item in enumerate(self.log) if item["event"]["event_id"] == event_id), None)
        if existing is None:
            self.log.append({"term": self.current_term, "event": event})
            self._save_state()
        self._send_append_entries()
        if self.majority == 1:
            self.commit_index = len(self.log) - 1
            self._apply_commits()

    def _handle_rating_query(self, address: Address) -> None:
        if self.role != "leader":
            leader = self.peers.get(self.leader_id or "")
            self._send(address, {"rpc": "redirect", "leader": format_address(leader) if leader else None})
            return
        self._send(address, {"rpc": "rating_response", "ratings": self.rating.table()})

    def _handle(self, message: dict[str, Any], address: Address) -> None:
        try:
            term = int(message.get("term", 0))
        except (TypeError, ValueError):
            return
        rpc = message.get("rpc")
        if term > self.current_term:
            self._become_follower(term, message.get("leader_id"))
        if term < self.current_term and rpc not in {"client_append", "rating_query"}:
            self._send(address, {"rpc": "stale_term"})
            return
        if rpc == "request_vote":
            self._handle_vote_request(message, address)
        elif rpc == "vote_response" and self.role == "candidate" and message.get("granted"):
            self.votes.add(str(message.get("sender")))
            if len(self.votes) >= self.majority:
                self._become_leader()
        elif rpc == "append_entries":
            self._handle_append(message, address)
        elif rpc == "append_response" and self.role == "leader":
            peer = str(message.get("sender"))
            if message.get("success"):
                match = int(message.get("match_index", -1))
                self.match_index[peer] = match
                self.next_index[peer] = match + 1
                self._advance_commit()
            else:
                self.next_index[peer] = max(0, self.next_index.get(peer, len(self.log)) - 1)
                self._send_append_entries(peer)
        elif rpc == "client_append":
            self._handle_client_append(message, address)
        elif rpc == "rating_query":
            self._handle_rating_query(address)

    def run(self) -> None:
        print(f"Logger {self.node_id} mendengarkan {format_address(self.bind)}", flush=True)
        try:
            while self.running:
                now = time.monotonic()
                if self.role == "leader" and now - self.last_heartbeat >= 0.22:
                    self._send_append_entries()
                elif self.role != "leader" and now >= self.election_deadline:
                    self._start_election()
                try:
                    raw, source = self.sock.recvfrom(60_000)
                except socket.timeout:
                    continue
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if isinstance(message, dict):
                    self._handle(message, (str(source[0]), int(source[1])))
        except KeyboardInterrupt:
            pass
        finally:
            self._save_state()
            self.sock.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Node logger Raft Jiwa Jawa")
    parser.add_argument("--id", required=True, help="ID node, misalnya logger-1")
    parser.add_argument("--bind", required=True, type=parse_address, metavar="HOST:PORT")
    parser.add_argument(
        "--peer",
        action="append",
        default=[],
        metavar="ID=HOST:PORT",
        help="Alamat node lain. Ulangi untuk setiap peer.",
    )
    parser.add_argument("--data-dir", required=True)
    return parser


def parse_peers(values: list[str]) -> dict[str, Address]:
    result = {}
    for value in values:
        try:
            node_id, address = value.split("=", 1)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("Peer harus berbentuk ID=HOST:PORT") from exc
        result[node_id] = parse_address(address)
    return result


def main() -> None:
    args = build_parser().parse_args()
    RaftNode(args.id, args.bind, parse_peers(args.peer), args.data_dir).run()


if __name__ == "__main__":
    main()
