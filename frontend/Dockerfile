# ---- 构建阶段：tsc + vite build，产出带指纹的静态资源 ----
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

# 构建期注入：vite 只在 build 时读取 VITE_ 前缀变量（运行时设置无效）
ARG VITE_READ_TOKEN
ARG VITE_API_URL=/api/v1
ENV VITE_READ_TOKEN=${VITE_READ_TOKEN} \
    VITE_API_URL=${VITE_API_URL}

RUN npm run build


# ---- 运行阶段：nginx 托管静态资源 + 反代 /api ----
FROM nginx:1.30-alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

# public/ 下的文件从源码 COPY 进来会带上宿主的 700 权限（Tools 目录规范），
# 而 nginx worker 以非 root 运行，读不到就 403 —— 统一收敛成 644/755
RUN find /usr/share/nginx/html -type f -exec chmod 644 {} + && \
    find /usr/share/nginx/html -type d -exec chmod 755 {} +

EXPOSE 3000

# nginx 前台运行（容器 PID 1）
CMD ["nginx", "-g", "daemon off;"]
