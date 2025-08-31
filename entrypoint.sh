#!/usr/bin/env bash
set -euo pipefail
[[ "${PA_DEBUG:-0}" = "1" ]] && set -x

die(){ echo "FATAL: $*" >&2; exit 1; }
have(){ command -v "$1" >/dev/null 2>&1; }

for b in pulseaudio pactl; do have "$b" || die "Missing $b"; done

# Per-user runtime (non-root friendly)
UID_CUR="$(id -u)"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp/xdg-runtime-$UID_CUR}"
export PULSE_RUNTIME_PATH="$XDG_RUNTIME_DIR/pulse"
mkdir -p "$PULSE_RUNTIME_PATH"
chmod 700 "$XDG_RUNTIME_DIR" || true

# Make ALSA 'default' point at Pulse
HOME_DIR="${HOME:-/home/$(id -un)}"
mkdir -p "$HOME_DIR"
cat > "$HOME_DIR/.asoundrc" <<'EOF'
pcm.!default { type pulse }
ctl.!default { type pulse }
EOF

echo "==== ENV ===="
echo "USER=$(id -un) UID=$(id -u) GID=$(id -g)"
echo "XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
echo "PULSE_RUNTIME_PATH=$PULSE_RUNTIME_PATH"
echo "PULSE_SERVER=${PULSE_SERVER:-<unset>}"
echo "=============="

# Start our own server unless PULSE_SERVER is preset (shared server case)
if [[ -z "${PULSE_SERVER:-}" ]]; then
  rm -f "${PULSE_RUNTIME_PATH}/pid" 2>/dev/null || true
  echo "Starting PulseAudio (per-user)…"
  pulseaudio --daemonize=yes \
             --exit-idle-time="${PA_IDLE_TIME:--1}" \
             --realtime=no --high-priority=no \
             --log-level="${PA_LOG_LEVEL:-info}" --log-target=stderr \
             --disallow-exit || die "pulseaudio failed to start"
  export PULSE_SERVER="unix:${PULSE_RUNTIME_PATH}/native"
else
  echo "Using external Pulse server at $PULSE_SERVER"
fi

# Wait for server
for i in {1..50}; do pactl info >/dev/null 2>&1 && break; sleep 0.1; done
pactl info || die "pactl cannot reach PulseAudio"

echo "==== PACTL INFO ===="
pactl info || true
echo "==== SINKS (short) ===="
pactl list short sinks || true
echo "==== SOURCES (short) ===="
pactl list short sources || true

# Prefer an existing null sink (auto_null), else just keep whatever default is
DEFAULT_SINK="$(pactl info | sed -n 's/^Default Sink: //p')"
DEFAULT_SOURCE="$(pactl info | sed -n 's/^Default Source: //p')"

# If there's an auto_null, set it explicitly (idempotent)
if pactl list short sinks | awk '{print $2}' | grep -qx "auto_null"; then
  pactl set-default-sink auto_null || true
  pactl set-default-source auto_null.monitor || true
fi

echo "==== FINAL ===="
echo "Default Sink:   $(pactl info | sed -n 's/^Default Sink: //p')"
echo "Default Source: $(pactl info | sed -n 's/^Default Source: //p')"
pactl list short sinks || true
pactl list short sources || true
echo "================"

echo "[entrypoint] PulseAudio ready. Exec: $*"
exec "$@"
