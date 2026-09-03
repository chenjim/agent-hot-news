# syntax=docker/dockerfile:1.4
FROM python:3.12-slim

WORKDIR /app

ARG HTTP_PROXY=""
ARG HTTPS_PROXY=""
ARG PIP_INDEX_URL="https://pypi.tuna.tsinghua.edu.cn/simple"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 构建期代理仅通过单次 RUN 的环境变量生效，不写 pip.conf，不污染运行时
# （历史教训：pip config set 会把代理固化进镜像层）
# 本地局域网构建可在 docker-compose build.args 或 --build-arg 传入代理

# 宿主机常 export 127.0.0.1/localhost:7890（本机回环），容器内不可达：
# 回环代理则 pip 直连国内镜像，非回环代理正常使用
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    if printf '%s' "$HTTP_PROXY $HTTPS_PROXY" | grep -Eq '127\.0\.0\.1|://localhost'; then \
      echo '[build] loopback proxy detected, pip goes direct'; \
      env -u HTTP_PROXY -u HTTPS_PROXY -u http_proxy -u https_proxy \
      pip install --index-url "$PIP_INDEX_URL" -r requirements.txt; \
    else \
      HTTP_PROXY="$HTTP_PROXY" HTTPS_PROXY="$HTTPS_PROXY" \
      pip install --index-url "$PIP_INDEX_URL" -r requirements.txt; \
    fi

COPY . .

RUN chmod +x /app/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
# 生产默认不带 --reload（省 CPU/内存、单进程）；本地热更新调试时覆盖 CMD 追加 --reload
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
