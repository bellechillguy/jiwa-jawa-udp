from __future__ import annotations

import argparse
import os
from pathlib import Path

from .controller import HostController, JoinController
from .protocol import parse_address


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Jiwa Jawa, dam-daman multiplayer lewat UDP")
    mode = result.add_mutually_exclusive_group(required=True)
    mode.add_argument("--host", metavar="HOST:PORT", help="Buka meja pada alamat UDP ini")
    mode.add_argument("--join", metavar="HOST:PORT", help="Gabung ke alamat host")
    result.add_argument("--name", required=True, help="Nama pemain, maksimal 32 karakter")
    result.add_argument("--bind", default="0.0.0.0:0", help="Alamat lokal untuk mode join")
    result.add_argument("--cli", action="store_true", help="Gunakan terminal, bukan GUI")
    result.add_argument("--no-logger", action="store_true", help="Jalankan host tanpa klaster logger")
    result.add_argument(
        "--logger",
        action="append",
        default=None,
        help="Node logger HOST:PORT. Opsi dapat diulang.",
    )
    result.add_argument("--data-dir", default=".jiwa-jawa", help="Lokasi outbox log lokal")
    result.add_argument(
        "--simulate-loss",
        type=float,
        default=0.0,
        metavar="RATE",
        help="Drop datagram keluar untuk tes lokal, contoh 0.5. Demo resmi tetap memakai tc-netem.",
    )
    return result


def main() -> None:
    args = parser().parse_args()
    name = args.name.strip()[:32]
    if not name:
        raise SystemExit("Nama tidak boleh kosong.")
    if not 0.0 <= args.simulate_loss < 1.0:
        raise SystemExit("--simulate-loss harus berada pada rentang 0 sampai kurang dari 1.")
    if args.host:
        logger_values = args.logger or ["127.0.0.1:9101", "127.0.0.1:9102", "127.0.0.1:9103"]
        logger_nodes = None if args.no_logger else [parse_address(value) for value in logger_values]
        controller = HostController(
            parse_address(args.host),
            name,
            logger_nodes=logger_nodes,
            data_dir=Path(args.data_dir),
            drop_rate=args.simulate_loss,
        )
    else:
        controller = JoinController(
            parse_address(args.join),
            name,
            bind=parse_address(args.bind),
            drop_rate=args.simulate_loss,
        )
    if args.cli:
        from .cli import run_cli

        run_cli(controller)
        return
    if not os.environ.get("DISPLAY") and os.name != "nt" and os.uname().sysname != "Darwin":
        controller.close()
        raise SystemExit("DISPLAY tidak tersedia. Jalankan ulang dengan --cli.")
    try:
        from .ui import GameWindow

        GameWindow(controller).run()
    except ModuleNotFoundError as exc:
        controller.close()
        if exc.name == "_tkinter":
            raise SystemExit(
                "Python ini tidak memiliki Tkinter. Jalankan game melalui "
                "./scripts/run-game.sh atau tambahkan --cli."
            ) from exc
        raise
    except Exception:
        controller.close()
        raise


if __name__ == "__main__":
    main()
