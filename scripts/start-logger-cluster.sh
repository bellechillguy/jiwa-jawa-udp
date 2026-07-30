#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
run_dir="$project_dir/.run"
data_dir="$project_dir/data"
mkdir -p "$run_dir" "$data_dir"

start_node() {
  local node_id="$1"
  local port="$2"
  local peer_a="$3"
  local peer_b="$4"
  PYTHONPATH="$project_dir" python3 -m jiwa_jawa.raft_logger \
    --id "$node_id" \
    --bind "127.0.0.1:$port" \
    --peer "$peer_a" \
    --peer "$peer_b" \
    --data-dir "$data_dir/$node_id" \
    >"$run_dir/$node_id.log" 2>&1 &
  echo "$!" >"$run_dir/$node_id.pid"
}

start_node logger-1 9101 logger-2=127.0.0.1:9102 logger-3=127.0.0.1:9103
start_node logger-2 9102 logger-1=127.0.0.1:9101 logger-3=127.0.0.1:9103
start_node logger-3 9103 logger-1=127.0.0.1:9101 logger-2=127.0.0.1:9102

sleep 2
echo "Klaster logger aktif. PID tersimpan di $run_dir"
echo "Log: $run_dir/logger-1.log, logger-2.log, logger-3.log"

