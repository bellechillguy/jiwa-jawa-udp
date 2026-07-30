#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

candidates=()
if command -v python3 >/dev/null 2>&1; then
  candidates+=("$(command -v python3)")
fi
candidates+=(
  "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3"
  "/opt/homebrew/bin/python3"
  "/usr/local/bin/python3"
  "/usr/bin/python3"
)

for python_bin in "${candidates[@]}"; do
  [[ -x "$python_bin" ]] || continue
  if "$python_bin" -c 'import tkinter, _tkinter' >/dev/null 2>&1; then
    echo "Memakai $("$python_bin" --version) dari $python_bin"
    cd "$project_dir"
    exec env PYTHONPATH="$project_dir" "$python_bin" -m jiwa_jawa.game "$@"
  fi
done

cat >&2 <<'EOF'
Tidak ditemukan instalasi Python yang memiliki Tkinter.

Pilihan perbaikan:
1. Pasang Python dari https://www.python.org/downloads/macos/, atau
2. Jika memakai Homebrew Python 3.14:
   brew install python-tk@3.14

Mode terminal tetap dapat dijalankan langsung dengan opsi --cli.
EOF
exit 1
