#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image_name="jiwa-jawa-netem:local"

docker build -t "$image_name" "$project_dir"
docker run --rm --cap-add=NET_ADMIN "$image_name" sh -ceu '
  cleanup() {
    tc qdisc del dev lo root 2>/dev/null || true
  }
  trap cleanup EXIT INT TERM
  tc qdisc add dev lo root netem loss 50%
  echo "Rule aktif:"
  tc qdisc show dev lo
  python -m unittest tests.test_protocol_netem -v
  cleanup
  trap - EXIT INT TERM
  echo "Rule setelah tes:"
  tc qdisc show dev lo
'

