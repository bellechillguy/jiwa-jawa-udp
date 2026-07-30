#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_dir="$project_dir/.run"

for pid_file in "$run_dir"/logger-*.pid; do
  [[ -e "$pid_file" ]] || continue
  pid="$(tr -dc '0-9' < "$pid_file")"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid"
  fi
  rm -f "$pid_file"
done
echo "Klaster logger dihentikan. Data log tetap tersimpan."
