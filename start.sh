#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "   Agent Hot News - 启动 / 重启"
echo "=========================================="

# Load .env safely (values may contain shell-special chars like | ; &)
if [ -f ".env" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        case "$line" in
            \#*|"") continue ;;
        esac
        key="${line%%=*}"
        value="${line#*=}"
        [ -n "$key" ] && export "$key=$value"
    done < .env
else
    echo "[WARN] .env file not found, using defaults"
fi

# Start Redis + Frontend in background
echo "[INFO] Starting Redis & Frontend (docker compose up -d)"
if docker compose version &>/dev/null; then
    docker compose up -d --build
elif command -v docker-compose &>/dev/null; then
    docker-compose up -d --build
else
    echo "[ERROR] Neither 'docker compose' nor 'docker-compose' found."
    exit 1
fi

# Wait for Redis
echo "[INFO] Waiting for Redis..."
for i in {1..10}; do
    if redis-cli -p 51179 ping 2>/dev/null | grep -q PONG; then
        echo "[INFO] Redis is ready"
        break
    fi
    sleep 1
done

# Start Backend
FOREGROUND=false
if [ "${1:-}" = "-f" ] || [ "${1:-}" = "--foreground" ]; then
    FOREGROUND=true
fi

cd backend

# Ensure venv exists with dependencies
if [ ! -f "venv/bin/python" ]; then
    echo "[INFO] Creating venv..."
    python3 -m venv venv
    venv/bin/pip install -r requirements.txt -q
fi

export PYTHONPATH="$(pwd)"
echo "[CONFIG] DATABASE_URL=${DATABASE_URL:-<default>}"
echo "[CONFIG] REDIS_URL=${REDIS_URL:-<default>}"
echo "[CONFIG] OPENAI_BASE_URL=${OPENAI_BASE_URL:-<default>}"
echo ""

if [ "$FOREGROUND" = true ]; then
    echo "[INFO] Starting Backend on http://localhost:51180 (Ctrl+C to stop)"
    $PYTHON -m uvicorn app.main:app --host 0.0.0.0 --port 51180 --reload
else
    if systemctl --user is-active hotnews-backend.service &>/dev/null; then
        echo "[INFO] Restarting backend via systemd"
        systemctl --user restart hotnews-backend.service
    else
        echo "[INFO] Starting backend via systemd"
        systemctl --user start hotnews-backend.service
    fi
    sleep 2
    if systemctl --user is-active hotnews-backend.service &>/dev/null; then
        echo "[INFO] Backend is active via systemd"
        echo "[INFO] Logs: journalctl --user -u hotnews-backend.service -f"
        echo "[INFO] API:   http://localhost:51180"
    else
        echo "[ERROR] Backend failed to start. Check: journalctl --user -u hotnews-backend.service"
        exit 1
    fi
fi
