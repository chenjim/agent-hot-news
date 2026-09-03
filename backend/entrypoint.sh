#!/bin/sh
set -e

# 宿主机 export 的 127.0.0.1/localhost 代理在容器内不可达，重写到 host 网关
# （compose 已映射 host.docker.internal；要求宿主机代理监听 0.0.0.0 而非仅 127.0.0.1）
for v in HTTP_PROXY HTTPS_PROXY http_proxy https_proxy; do
  eval "val=\$$v"
  case "$val" in
    *127.0.0.1*|*://localhost:*)
      newval=$(printf '%s' "$val" | sed -e 's/127\.0\.0\.1/host.docker.internal/g' -e 's/:\/\/localhost:/:\/\/host.docker.internal:/g')
      export "$v=$newval"
      echo "[entrypoint] $v loopback rewritten -> $newval"
      ;;
  esac
done

# 等待 postgres/redis 就绪（slim 镜像无 pg_isready，用 python socket 探测）
echo "[entrypoint] Waiting for postgres:5432 and redis:6379..."
python - <<'EOF'
import socket, sys, time

def wait(host, port, timeout=60):
    for _ in range(timeout):
        try:
            with socket.create_connection((host, port), timeout=2):
                print(f"[entrypoint] {host}:{port} reachable")
                return True
        except OSError:
            time.sleep(1)
    return False

ok = wait("postgres", 5432) and wait("redis", 6379)
sys.exit(0 if ok else 1)
EOF

# 执行迁移，带 3 次重试（首启 DB 刚 ready 时偶发连接拒绝）
echo "[entrypoint] Running alembic upgrade head..."
for i in 1 2 3; do
  if alembic upgrade head; then
    break
  fi
  if [ "$i" -eq 3 ]; then
    echo "[entrypoint] alembic upgrade failed after 3 attempts, aborting."
    exit 1
  fi
  echo "[entrypoint] alembic upgrade failed, retrying in 5s ($i/3)..."
  sleep 5
done

echo "[entrypoint] Starting: $*"
exec "$@"
