#!/usr/bin/env bash
set -euo pipefail
[[ "${PA_DEBUG:-0}" == "1" ]] && set -x

uid="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime-$uid}"
mkdir -p "$XDG_RUNTIME_DIR/pulse"

# Write ALSA→Pulse mapping once if missing.
: "${HOME:=/home/$(id -un)}"
[[ -f "$HOME/.asoundrc" ]] || cat > "$HOME/.asoundrc" <<'EOF'
pcm.!default { type pulse }
ctl.!default { type pulse }
EOF

if [[ -z "${PULSE_SERVER:-}" ]]; then
  pulseaudio --daemonize=yes \
             --exit-idle-time="${PA_IDLE_TIME:--1}" \
             --realtime=no --high-priority=no \
             --log-level="${PA_LOG_LEVEL:-info}" --log-target=stderr \
             --disallow-exit
  export PULSE_SERVER="unix:$XDG_RUNTIME_DIR/pulse/native"
fi

for _ in {1..50}; do pactl info >/dev/null 2>&1 && break; sleep 0.1; done
pactl info >/dev/null

pactl list short sinks | grep -q ' auto_null\>' && {
  pactl set-default-sink auto_null || true
  pactl set-default-source auto_null.monitor || true
}

exec "$@"
