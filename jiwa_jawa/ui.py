from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from .board import EDGES, NODES, Coord, GameState, coord_name
from .controller import BaseController


class GameWindow:
    BG = "#f5efe2"
    INK = "#342d27"
    LINE = "#6d5b4b"
    A = "#1f6f8b"
    B = "#b44343"
    GOLD = "#e0a928"

    def __init__(self, controller: BaseController) -> None:
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("Jiwa Jawa - Dam-daman Multiplayer")
        self.root.geometry("1120x720")
        self.root.minsize(900, 620)
        self.root.configure(bg=self.BG)
        self.selected: Coord | None = None
        self.dam_targets: list[Coord] = []
        self.last_version = -1
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(80, self._poll)

    def _build(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG)
        style.configure("Title.TLabel", background=self.BG, foreground=self.INK, font=("Helvetica", 23, "bold"))
        style.configure("TLabel", background=self.BG, foreground=self.INK, font=("Helvetica", 11))
        style.configure("Accent.TButton", font=("Helvetica", 11, "bold"), padding=8)

        wrapper = ttk.Frame(self.root, padding=18)
        wrapper.pack(fill="both", expand=True)
        header = ttk.Frame(wrapper)
        header.pack(fill="x", pady=(0, 12))
        ttk.Label(header, text="JIWA JAWA", style="Title.TLabel").pack(side="left")
        self.connection = ttk.Label(header, text="Menyiapkan koneksi...")
        self.connection.pack(side="right")

        body = ttk.Frame(wrapper)
        body.pack(fill="both", expand=True)
        board_frame = ttk.Frame(body)
        board_frame.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(board_frame, bg="#e8d5ad", highlightthickness=0, cursor="hand2")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self._draw())
        self.canvas.bind("<Button-1>", self._click)

        sidebar = ttk.Frame(body, width=310, padding=(16, 0, 0, 0))
        sidebar.pack(side="right", fill="y")
        sidebar.pack_propagate(False)
        self.turn_label = ttk.Label(sidebar, text="Menunggu lawan", font=("Helvetica", 16, "bold"), wraplength=285)
        self.turn_label.pack(fill="x", pady=(4, 10))
        self.score_label = ttk.Label(sidebar, text="A: 16 pion\nB: 16 pion", font=("Helvetica", 12))
        self.score_label.pack(fill="x", pady=(0, 14))
        ttk.Label(sidebar, text="Riwayat langkah", font=("Helvetica", 12, "bold")).pack(anchor="w")
        self.history = tk.Listbox(
            sidebar,
            bg="#fffaf0",
            fg=self.INK,
            bd=0,
            highlightthickness=1,
            highlightbackground="#c9b995",
            font=("Menlo", 10),
            activestyle="none",
        )
        self.history.pack(fill="both", expand=True, pady=(6, 12))
        self.dam_button = ttk.Button(sidebar, text="Ambil pion DAM", style="Accent.TButton", command=self._submit_dam)
        self.dam_button.pack(fill="x", pady=(0, 8))
        self.dam_button.state(["disabled"])
        ttk.Button(sidebar, text="Cara singkat", command=self._show_help).pack(fill="x")
        self.notice = ttk.Label(sidebar, text="", wraplength=285, foreground="#8b2d2d")
        self.notice.pack(fill="x", pady=(10, 0))

    def _point(self, coord: Coord) -> tuple[float, float]:
        width = max(self.canvas.winfo_width(), 600)
        height = max(self.canvas.winfo_height(), 500)
        pad_x, pad_y = 55, 55
        x = pad_x + (coord[0] + 2) * (width - 2 * pad_x) / 8
        y = pad_y + coord[1] * (height - 2 * pad_y) / 4
        return x, y

    def _draw(self) -> None:
        self.canvas.delete("all")
        state = self.controller.snapshot()
        for first, second in EDGES:
            self.canvas.create_line(*self._point(first), *self._point(second), fill=self.LINE, width=2)
        legal: dict[Coord, str] = {}
        if state and self.selected:
            legal = state.legal_destinations(self.selected)
        for node in sorted(NODES):
            x, y = self._point(node)
            radius = 5
            fill = self.INK
            if node in legal:
                radius = 10
                fill = self.GOLD if legal[node] == "capture" else "#4e9f6f"
            self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill=fill, outline="")
        if not state:
            self.canvas.create_text(
                self.canvas.winfo_width() / 2,
                28,
                text="Papan akan aktif setelah kedua pemain tersambung",
                fill=self.INK,
                font=("Helvetica", 12, "bold"),
            )
            return
        for coord, piece in state.pieces.items():
            x, y = self._point(coord)
            radius = 22
            selected = coord == self.selected or coord in self.dam_targets
            outline = self.GOLD if selected else "#f7ead0"
            width = 5 if selected else 2
            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=self.A if piece.owner == "A" else self.B,
                outline=outline,
                width=width,
            )
            self.canvas.create_text(
                x,
                y,
                text="R" if piece.king else piece.owner,
                fill="white",
                font=("Helvetica", 11, "bold"),
            )

    def _nearest(self, x: float, y: float) -> Coord | None:
        nearest = min(NODES, key=lambda node: (self._point(node)[0] - x) ** 2 + (self._point(node)[1] - y) ** 2)
        px, py = self._point(nearest)
        return nearest if (px - x) ** 2 + (py - y) ** 2 <= 34**2 else None

    def _click(self, event: tk.Event[Any]) -> None:
        state = self.controller.snapshot()
        node = self._nearest(event.x, event.y)
        if state is None or node is None or state.winner:
            return
        if state.turn != self.controller.player:
            self.notice.configure(text="Tunggu langkah lawan.")
            return
        if state.dam_player:
            victim = state.pieces.get(node)
            if victim and victim.owner != self.controller.player:
                if node in self.dam_targets:
                    self.dam_targets.remove(node)
                elif len(self.dam_targets) < state.dam_remaining:
                    self.dam_targets.append(node)
                self._refresh_dam_button(state)
                self._draw()
            return
        piece = state.pieces.get(node)
        if piece and piece.owner == self.controller.player:
            self.selected = node
            self.notice.configure(text="Pilih titik tujuan. Titik emas berarti memakan pion.")
            self._draw()
            return
        if self.selected and node in state.legal_destinations(self.selected):
            self.controller.submit({"type": "move", "src": coord_name(self.selected), "dst": coord_name(node)})
            self.selected = None
            self.notice.configure(text="Langkah dikirim. Menunggu konfirmasi host.")
            self._draw()

    def _refresh_dam_button(self, state: GameState) -> None:
        required = min(state.dam_remaining, state.piece_count(GameState.opponent(self.controller.player)))
        self.dam_button.configure(text=f"Ambil DAM ({len(self.dam_targets)}/{required})")
        if len(self.dam_targets) == required and required > 0:
            self.dam_button.state(["!disabled"])
        else:
            self.dam_button.state(["disabled"])

    def _submit_dam(self) -> None:
        if not self.dam_targets:
            return
        self.controller.submit({"type": "dam", "targets": [coord_name(item) for item in self.dam_targets]})
        self.dam_targets.clear()
        self.dam_button.state(["disabled"])

    @staticmethod
    def _history_text(action: dict[str, Any], players: dict[str, str]) -> str:
        actor = players.get(action.get("player"), action.get("player", "?"))
        if action.get("type") == "dam":
            return f"{action['version']:02d}. {actor} ambil DAM: {', '.join(action['targets'])}"
        extra = " x" if action.get("capture") else ""
        if action.get("promoted"):
            extra += " jadi raja"
        if action.get("missed_capture"):
            extra += " (kena DAM)"
        return f"{action['version']:02d}. {actor}: {action['src']} -> {action['dst']}{extra}"

    def _sync_state(self, state: GameState) -> None:
        if state.version != self.last_version:
            self.selected = None
            self.dam_targets.clear()
            self.last_version = state.version
        self.score_label.configure(
            text=(
                f"A  {state.players['A']}: {state.piece_count('A')} pion\n"
                f"B  {state.players['B']}: {state.piece_count('B')} pion"
            )
        )
        if state.winner:
            self.turn_label.configure(text=f"{state.players[state.winner]} menang")
        elif state.dam_player:
            self.turn_label.configure(text=f"{state.players[state.turn]} memilih {state.dam_remaining} pion DAM")
        elif state.turn == self.controller.player:
            self.turn_label.configure(text="Giliranmu")
        else:
            self.turn_label.configure(text=f"Giliran {state.players[state.turn]}")
        self.history.delete(0, "end")
        for action in state.history[-40:]:
            self.history.insert("end", self._history_text(action, state.players))
        self.history.yview_moveto(1)
        if state.dam_player == self.controller.player:
            self._refresh_dam_button(state)
            self.notice.configure(text="Lawan melewatkan kesempatan makan. Pilih pion lawan untuk hukuman DAM.")
        else:
            self.dam_button.configure(text="Ambil pion DAM")
            self.dam_button.state(["disabled"])
        self._draw()

    def _poll(self) -> None:
        try:
            while True:
                kind, message = self.controller.events.get_nowait()
                if kind == "status":
                    self.connection.configure(text=message)
                elif kind == "error":
                    self.notice.configure(text=message)
                elif kind == "network":
                    self.connection.configure(text=message)
        except queue.Empty:
            pass
        state = self.controller.snapshot()
        if state:
            self._sync_state(state)
        if not self.controller.closed.is_set():
            self.root.after(100, self._poll)

    def _show_help(self) -> None:
        messagebox.showinfo(
            "Cara bermain",
            "Klik pionmu, lalu klik titik tujuan. Pion biasa bergerak ke depan, samping, "
            "atau diagonal satu ruas. Lompati satu pion lawan untuk memakannya. Pion yang "
            "sampai garis terluar segitiga lawan menjadi raja dan boleh mundur. Jika ada "
            "kesempatan makan tetapi kamu memilih langkah biasa, lawan boleh mengambil tiga pionmu.",
        )

    def close(self) -> None:
        self.controller.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def run_cli(controller: BaseController) -> None:
    print("Jiwa Jawa mode terminal. Ketik 'help' untuk daftar perintah.")
    last_version = -2
    try:
        while True:
            state = controller.snapshot()
            if state and state.version != last_version:
                last_version = state.version
                print(f"\nVersi {state.version} | giliran {state.turn} | A={state.piece_count('A')} B={state.piece_count('B')}")
                if state.last_action:
                    print(GameWindow._history_text(state.last_action, state.players))
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
