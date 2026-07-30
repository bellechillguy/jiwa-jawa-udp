from __future__ import annotations

import queue
from typing import Any

from .controller import BaseController


def history_text(action: dict[str, Any], players: dict[str, str]) -> str:
    actor = players.get(action.get("player"), action.get("player", "?"))
    if action.get("type") == "dam":
        return f"{action['version']:02d}. {actor} ambil DAM: {', '.join(action['targets'])}"
    extra = " x" if action.get("capture") else ""
    if action.get("promoted"):
        extra += " jadi raja"
    if action.get("missed_capture"):
        extra += " (kena DAM)"
    return f"{action['version']:02d}. {actor}: {action['src']} -> {action['dst']}{extra}"


def run_cli(controller: BaseController) -> None:
    print("Jiwa Jawa mode terminal. Ketik 'help' untuk daftar perintah.")
    last_version = -2
    try:
        while True:
            state = controller.snapshot()
            if state and state.version != last_version:
                last_version = state.version
                print(
                    f"\nVersi {state.version} | giliran {state.turn} | "
                    f"A={state.piece_count('A')} B={state.piece_count('B')}"
                )
                if state.last_action:
                    print(history_text(state.last_action, state.players))
                if state.winner:
                    print(f"Pemenang: {state.players[state.winner]}")
            try:
                while True:
                    kind, message = controller.events.get_nowait()
                    print(f"[{kind}] {message}")
            except queue.Empty:
                pass
            command = input("jiwa-jawa> ").strip()
            if command in {"quit", "exit"}:
                break
            if command == "help":
                print("move X,Y X,Y | dam X,Y X,Y X,Y | state | quit")
            elif command == "state":
                state = controller.snapshot()
                print(state.to_dict() if state else "Belum tersambung.")
            elif command.startswith("move "):
                parts = command.split()
                if len(parts) == 3:
                    controller.submit({"type": "move", "src": parts[1], "dst": parts[2]})
                else:
                    print("Format: move X,Y X,Y")
            elif command.startswith("dam "):
                controller.submit({"type": "dam", "targets": command.split()[1:]})
            elif command:
                print("Perintah tidak dikenal.")
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        controller.close()
