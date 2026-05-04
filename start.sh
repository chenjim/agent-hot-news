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

# Start Redis + PostgreSQL + Frontend in background
echo "[INFO] Starting Redis, PostgreSQL & Frontend (docker compose up -d)"
if docker compose version &>/dev/null; then
    docker compose up -d --build
elif command -v docker-compose &>/dev/null; then
    docker-compose up -d --build
else
    echo "[ERROR] Neither 'docker compose' nor 'docker-compose' found."
    exit 1
fi

# Wait for PostgreSQL
echo "[INFO] Waiting for PostgreSQL..."
for i in {1..15}; do
    if docker compose exec -T postgres pg_isready -U hotnews -d hotnews 2>/dev/null; then
        echo "[INFO] PostgreSQL is ready"
        break
    fi
    sleep 2
done

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

# Kill existing process on port 51180
PORT=51180
if PID=$(fuser $PORT/tcp 2>/dev/null); then
    echo "[INFO] Killing existing process on port $PORT (PID: $PID)"
    fuser -k $PORT/tcp 2>/dev/null
    sleep 1
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

# Run database migrations
if [ "${DATABASE_URL:-}" != "${DATABASE_URL#postgresql}" ]; then
    echo "[INFO] Running Alembic migrations..."
    venv/bin/alembic upgrade head
fi

if [ "$FOREGROUND" = true ]; then
    echo "[INFO] Starting Backend on http://localhost:51180 (Ctrl+C to stop)"
    venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 51180 --reload
else
    # Auto-create systemd service file
    SERVICE_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    SERVICE_FILE="$SERVICE_DIR/hotnews-backend.service"
    BACKEND_DIR="$(pwd)"

    mkdir -p "$SERVICE_DIR"
    cat > "$SERVICE_FILE" << SERVICEOF
[Unit]
Description=Agent Hot News Backend
After=network.target

[Service]
Type=simple
WorkingDirectory=$BACKEND_DIR
Environment=PATH=$BACKEND_DIR/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONPATH=$BACKEND_DIR
EnvironmentFile=-${BACKEND_DIR}/../.env
ExecStartPre=$BACKEND_DIR/venv/bin/alembic upgrade head
ExecStart=$BACKEND_DIR/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 51180
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
SERVICEOF

    systemctl --user daemon-reload
    systemctl --user enable hotnews-backend.service

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
