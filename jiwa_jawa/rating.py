from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class RatingBook:
    """Rating Elo. Kurva ekspektasinya logistik, bukan perhitungan linear."""

    def __init__(self, path: str | Path | None = None, initial: float = 1200.0, k: float = 32.0):
        self.path = Path(path) if path else None
        self.initial = float(initial)
        self.k = float(k)
        self.ratings: dict[str, float] = {}
        self.games: dict[str, int] = {}
        self.processed_matches: set[str] = set()
        if self.path and self.path.exists():
            self.load()

    @staticmethod
    def expected(rating: float, opponent_rating: float) -> float:
        return 1.0 / (1.0 + math.pow(10.0, (opponent_rating - rating) / 400.0))

    def get(self, player: str) -> float:
        return self.ratings.get(player, self.initial)

    def record(self, match_id: str, player_a: str, player_b: str, winner: str | None) -> bool:
        if match_id in self.processed_matches:
            return False
        old_a, old_b = self.get(player_a), self.get(player_b)
        expected_a = self.expected(old_a, old_b)
        if winner == "A":
            score_a = 1.0
        elif winner == "B":
            score_a = 0.0
        else:
            score_a = 0.5
        self.ratings[player_a] = old_a + self.k * (score_a - expected_a)
        self.ratings[player_b] = old_b + self.k * ((1.0 - score_a) - (1.0 - expected_a))
        self.games[player_a] = self.games.get(player_a, 0) + 1
        self.games[player_b] = self.games.get(player_b, 0) + 1
        self.processed_matches.add(match_id)
        self.save()
        return True

    def table(self) -> list[dict[str, Any]]:
        players = set(self.ratings) | set(self.games)
        return [
            {"rank": rank, "player": player, "rating": round(self.get(player)), "games": self.games.get(player, 0)}
            for rank, player in enumerate(sorted(players, key=lambda item: (-self.get(item), item)), 1)
        ]

    def load(self) -> None:
        assert self.path is not None
        value = json.loads(self.path.read_text(encoding="utf-8"))
        self.ratings = {str(k): float(v) for k, v in value.get("ratings", {}).items()}
        self.games = {str(k): int(v) for k, v in value.get("games", {}).items()}
        self.processed_matches = set(value.get("processed_matches", []))

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "ratings": self.ratings,
                    "games": self.games,
                    "processed_matches": sorted(self.processed_matches),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(self.path)
