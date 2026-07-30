#!/usr/bin/env bash
set -euo pipefail

action="${1:-status}"
device="${2:-lo}"

case "$action" in
  add)
    sudo tc qdisc replace dev "$device" root netem loss 50%
    tc qdisc show dev "$device"
    ;;
  del)
    sudo tc qdisc del dev "$device" root 2>/dev/null || true
    tc qdisc show dev "$device"
    ;;
  status)
    tc qdisc show dev "$device"
    ;;
  *)
    echo "Pakai: $0 {add|del|status} [device]" >&2
    exit 2
    ;;
esac

