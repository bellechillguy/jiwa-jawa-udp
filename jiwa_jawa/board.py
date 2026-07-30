from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

Coord = tuple[int, int]


def coord_name(coord: Coord) -> str:
    return f"{coord[0]},{coord[1]}"


def parse_coord(value: str | Iterable[int]) -> Coord:
    if isinstance(value, str):
        x, y = value.split(",", 1)
        return int(x), int(y)
    x, y = value
    return int(x), int(y)


def _make_nodes() -> set[Coord]:
    square = {(x, y) for x in range(5) for y in range(5)}
    left = {(-2, 0), (-2, 2), (-2, 4), (-1, 1), (-1, 2), (-1, 3)}
    right = {(6, 0), (6, 2), (6, 4), (5, 1), (5, 2), (5, 3)}
    return square | left | right


NODES = frozenset(_make_nodes())


def _make_edges() -> frozenset[tuple[Coord, Coord]]:
    edges: set[tuple[Coord, Coord]] = set()

    def add(a: Coord, b: Coord) -> None:
        edges.add(tuple(sorted((a, b))))

    # Kisi tengah. Setiap simpul terhubung secara horizontal, vertikal,
    # dan diagonal seperti papan dam-daman 16 batu.
    for x in range(5):
        for y in range(5):
            for dx, dy in ((1, 0), (0, 1), (1, 1), (1, -1)):
                other = (x + dx, y + dy)
                if other in NODES:
                    add((x, y), other)

    def triangle(apex_x: int, mid_x: int, base_x: int) -> None:
        apex = (apex_x, 2)
        for mid, base in (
            ((mid_x, 1), (base_x, 0)),
            ((mid_x, 2), (base_x, 2)),
            ((mid_x, 3), (base_x, 4)),
        ):
            add(apex, mid)
            add(mid, base)
        add((mid_x, 1), (mid_x, 2))
        add((mid_x, 2), (mid_x, 3))
        add((base_x, 0), (base_x, 2))
        add((base_x, 2), (base_x, 4))
        add((mid_x, 1), (base_x, 2))
        add((mid_x, 3), (base_x, 2))

    triangle(0, -1, -2)
    triangle(4, 5, 6)
    return frozenset(edges)


EDGES = _make_edges()
NEIGHBORS: dict[Coord, set[Coord]] = {node: set() for node in NODES}
for first, second in EDGES:
    NEIGHBORS[first].add(second)
    NEIGHBORS[second].add(first)


@dataclass(frozen=True)
class Piece:
    owner: str
    king: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"owner": self.owner, "king": self.king}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Piece":
        return cls(str(value["owner"]), bool(value.get("king", False)))


class InvalidAction(ValueError):
    pass


@dataclass
class GameState:
    players: dict[str, str]
    pieces: dict[Coord, Piece]
    turn: str = "A"
    version: int = 0
    winner: str | None = None
    dam_player: str | None = None
    dam_remaining: int = 0
    last_action: dict[str, Any] | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def initial(cls, player_a: str, player_b: str) -> "GameState":
        pieces: dict[Coord, Piece] = {}
        for coord in NODES:
            if coord[0] <= 1:
                pieces[coord] = Piece("A")
            elif coord[0] >= 3:
                pieces[coord] = Piece("B")
        return cls(players={"A": player_a, "B": player_b}, pieces=pieces)

    def copy(self) -> "GameState":
        return GameState.from_dict(self.to_dict())

    @staticmethod
    def opponent(player: str) -> str:
        return "B" if player == "A" else "A"

    def piece_count(self, player: str) -> int:
        return sum(piece.owner == player for piece in self.pieces.values())

    def _direction_ok(self, piece: Piece, src: Coord, dst: Coord) -> bool:
        if piece.king:
            return True
        dx = dst[0] - src[0]
        return dx >= 0 if piece.owner == "A" else dx <= 0

    def simple_moves_from(self, src: Coord) -> list[Coord]:
        piece = self.pieces.get(src)
        if piece is None:
            return []
        return sorted(
            dst
            for dst in NEIGHBORS[src]
            if dst not in self.pieces and self._direction_ok(piece, src, dst)
        )

    def captures_from(self, src: Coord) -> list[tuple[Coord, Coord]]:
        piece = self.pieces.get(src)
        if piece is None:
            return []
        result: list[tuple[Coord, Coord]] = []
        for middle in NEIGHBORS[src]:
            victim = self.pieces.get(middle)
            if victim is None or victim.owner == piece.owner:
                continue
            vx, vy = middle[0] - src[0], middle[1] - src[1]
            dst = middle[0] + vx, middle[1] + vy
            if (
                dst in NEIGHBORS[middle]
                and dst not in self.pieces
                and self._direction_ok(piece, src, dst)
            ):
                result.append((dst, middle))
        return sorted(result)

    def captures_for(self, player: str) -> list[tuple[Coord, Coord, Coord]]:
        result = []
        for src, piece in self.pieces.items():
            if piece.owner == player:
                result.extend((src, dst, victim) for dst, victim in self.captures_from(src))
        return sorted(result)

    def has_move(self, player: str) -> bool:
        return any(
            self.simple_moves_from(coord) or self.captures_from(coord)
            for coord, piece in self.pieces.items()
            if piece.owner == player
        )

    def legal_destinations(self, src: Coord) -> dict[Coord, str]:
        result = {dst: "move" for dst in self.simple_moves_from(src)}
        result.update({dst: "capture" for dst, _ in self.captures_from(src)})
        return result

    def _promote(self, coord: Coord, piece: Piece) -> Piece:
        far_edge = 6 if piece.owner == "A" else -2
        if coord[0] == far_edge:
            return Piece(piece.owner, True)
        return piece

    def _record(self, action: dict[str, Any]) -> dict[str, Any]:
        self.version += 1
        action = {**action, "version": self.version}
        self.last_action = action
        self.history.append(action)
        return action

    def _finish_if_needed(self, player_who_moved: str) -> None:
        opponent = self.opponent(player_who_moved)
        if self.piece_count(opponent) == 0 or not self.has_move(opponent):
            self.winner = player_who_moved

    def apply(self, player: str, action: dict[str, Any]) -> dict[str, Any]:
        if self.winner:
            raise InvalidAction("Permainan sudah selesai.")
        if player != self.turn:
            raise InvalidAction("Belum giliran pemain ini.")

        action_type = action.get("type")
        if self.dam_player:
            if action_type != "dam":
                raise InvalidAction("Ambil hukuman DAM lebih dulu.")
            return self._apply_dam(player, action)
        if action_type != "move":
            raise InvalidAction("Aksi yang diterima hanya move.")
        return self._apply_move(player, action)

    def _apply_move(self, player: str, action: dict[str, Any]) -> dict[str, Any]:
        try:
            src, dst = parse_coord(action["src"]), parse_coord(action["dst"])
        except (KeyError, TypeError, ValueError) as exc:
            raise InvalidAction("Koordinat langkah tidak valid.") from exc
        piece = self.pieces.get(src)
        if piece is None or piece.owner != player:
            raise InvalidAction("Pilih pion milik sendiri.")
        captures_before = self.captures_for(player)
        capture = next((victim for target, victim in self.captures_from(src) if target == dst), None)
        is_simple = dst in self.simple_moves_from(src)
        if capture is None and not is_simple:
            raise InvalidAction("Tujuan tidak terhubung atau sudah ditempati.")

        del self.pieces[src]
        if capture is not None:
            del self.pieces[capture]
        moved_piece = self._promote(dst, piece)
        self.pieces[dst] = moved_piece

        opponent = self.opponent(player)
        missed_capture = bool(captures_before) and capture is None
        if missed_capture:
            self.dam_player = opponent
            self.dam_remaining = min(3, self.piece_count(player))
        self.turn = opponent
        recorded = self._record(
            {
                "type": "move",
                "player": player,
                "src": coord_name(src),
                "dst": coord_name(dst),
                "capture": coord_name(capture) if capture else None,
                "promoted": moved_piece.king and not piece.king,
                "missed_capture": missed_capture,
            }
        )
        self._finish_if_needed(player)
        return recorded

    def _apply_dam(self, player: str, action: dict[str, Any]) -> dict[str, Any]:
        if player != self.dam_player:
            raise InvalidAction("Hanya lawan yang berhak mengambil pion DAM.")
        raw_targets = action.get("targets")
        if not isinstance(raw_targets, list):
            raise InvalidAction("targets harus berupa daftar koordinat.")
        targets = [parse_coord(value) for value in raw_targets]
        if len(targets) != len(set(targets)):
            raise InvalidAction("Pion DAM tidak boleh dipilih dua kali.")
        required = min(self.dam_remaining, self.piece_count(self.opponent(player)))
        if len(targets) != required:
            raise InvalidAction(f"Pilih tepat {required} pion untuk hukuman DAM.")
        victim_owner = self.opponent(player)
        if any(self.pieces.get(target, Piece("?")).owner != victim_owner for target in targets):
            raise InvalidAction("Hukuman DAM hanya boleh mengambil pion lawan.")
        for target in targets:
            del self.pieces[target]
        self.dam_player = None
        self.dam_remaining = 0
        recorded = self._record(
            {
                "type": "dam",
                "player": player,
                "targets": [coord_name(value) for value in targets],
            }
        )
        if self.piece_count(victim_owner) == 0:
            self.winner = player
        return recorded

    def to_dict(self) -> dict[str, Any]:
        return {
            "players": self.players,
            "pieces": {coord_name(coord): piece.to_dict() for coord, piece in self.pieces.items()},
            "turn": self.turn,
            "version": self.version,
            "winner": self.winner,
            "dam_player": self.dam_player,
            "dam_remaining": self.dam_remaining,
            "last_action": self.last_action,
            "history": self.history,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GameState":
        return cls(
            players={str(k): str(v) for k, v in value["players"].items()},
            pieces={parse_coord(k): Piece.from_dict(v) for k, v in value["pieces"].items()},
            turn=str(value["turn"]),
            version=int(value.get("version", 0)),
            winner=value.get("winner"),
            dam_player=value.get("dam_player"),
            dam_remaining=int(value.get("dam_remaining", 0)),
            last_action=value.get("last_action"),
            history=list(value.get("history", [])),
        )

