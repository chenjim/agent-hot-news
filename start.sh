#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "   Agent Hot News - 启动 / 重启"
echo "=========================================="

# 兼容旧 systemd 后端：若仍存在则停用，避免端口冲突
if systemctl --user is-active hotnews-backend.service &>/dev/null; then
    echo "[INFO] Stopping legacy systemd backend (hotnews-backend.service)..."
    systemctl --user stop hotnews-backend.service || true
fi
if [ -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/hotnews-backend.service" ]; then
    echo "[INFO] Disabling legacy systemd service..."
    systemctl --user disable hotnews-backend.service || true
    rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/hotnews-backend.service"
    systemctl --user daemon-reload || true
fi
# 清理可能残留的宿主机 51180 进程
if command -v fuser &>/dev/null; then
    if fuser 51180/tcp &>/dev/null; then
        echo "[INFO] Killing stray process on port 51180..."
        fuser -k 51180/tcp 2>/dev/null || true
        sleep 1
    fi
fi

# 容器内无法访问宿主机回环代理：若宿主机 export 了 127.0.0.1/localhost，
# 重写为局域网地址，否则构建（pip）和运行时（采集器/LLM）都会连上拒绝
for _pv in HTTP_PROXY HTTPS_PROXY http_proxy https_proxy; do
    _val="${!_pv:-}"
    case "$_val" in
        *127.0.0.1*|*://localhost:*)
            export "$_pv=http://192.168.31.165:7890"
            echo "[INFO] $_pv loopback rewritten -> http://192.168.31.165:7890"
            ;;
    esac
done
unset _pv _val

# 选择 compose 命令
if docker compose version &>/dev/null; then
    COMPOSE="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE="docker-compose"
else
    echo "[ERROR] Neither 'docker compose' nor 'docker-compose' found."
    exit 1
fi

# 前台模式：直接前台拉起，Ctrl+C 停止
if [ "${1:-}" = "-f" ] || [ "${1:-}" = "--foreground" ]; then
    echo "[INFO] Starting all services in foreground (Ctrl+C to stop)..."
    $COMPOSE up --build
    exit 0
fi

echo "[INFO] Starting Redis, PostgreSQL, Backend & Frontend (docker compose up -d --build)"
$COMPOSE up -d --build

# 等待 PostgreSQL
echo "[INFO] Waiting for PostgreSQL..."
PG_READY=false
for i in {1..15}; do
    if $COMPOSE exec -T postgres pg_isready -U hotnews -d hotnews 2>/dev/null; then
        echo "[INFO] PostgreSQL is ready"
        PG_READY=true
        break
    fi
    sleep 2
done
[ "$PG_READY" = true ] || echo "[WARN] PostgreSQL not ready after 30s, check: docker compose logs postgres --tail 20"

# 等待 Redis
echo "[INFO] Waiting for Redis..."
REDIS_READY=false
for i in {1..10}; do
    if $COMPOSE exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
        echo "[INFO] Redis is ready"
        REDIS_READY=true
        break
    fi
    # fallback: host redis-cli if container exec not ready
    if redis-cli -p 51179 ping 2>/dev/null | grep -q PONG; then
        echo "[INFO] Redis is ready (via host port)"
        REDIS_READY=true
        break
    fi
    sleep 1
done
[ "$REDIS_READY" = true ] || echo "[WARN] Redis not ready after 10s, check: docker compose logs redis --tail 20"

# 健康检查：curl / wget / python 三选一（宿主机不一定有 curl）
health_ok() {
    if command -v curl &>/dev/null; then
        curl -sf http://localhost:51180/health >/dev/null 2>&1
    elif command -v wget &>/dev/null; then
        wget -q -O /dev/null http://localhost:51180/health >/dev/null 2>&1
    else
        python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:51180/health')" >/dev/null 2>&1
    fi
}

# 等待 Backend
echo "[INFO] Waiting for Backend (http://localhost:51180/health)..."
for i in {1..30}; do
    if health_ok; then
        echo "[INFO] Backend is ready"
        break
    fi
    sleep 2
    if [ "$i" -eq 30 ]; then
        echo "[WARN] Backend not ready after 60s, check logs:"
        echo "       docker compose logs backend --tail 50"
    fi
done

echo ""
echo "[INFO] All services started"
echo "[INFO] Frontend: http://localhost:51131"
echo "[INFO] Backend:  http://localhost:51180  (health: /health, docs: /docs)"
echo "[INFO] Logs:     docker compose logs -f backend"
echo "[INFO] Stop:     docker compose down"
