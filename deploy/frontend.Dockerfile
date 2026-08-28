# 前端镜像：构建上下文为项目根目录（见 docker-compose.prod.yml 的 context: ..）
# 这样才能同时 COPY frontend 源码与 deploy/nginx.conf。

# 构建阶段：编译 Vue 静态产物
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
# 前端通过相对路径 /api/v1 访问后端，构建期无需注入变量；由 Nginx 反向代理转发
RUN npm run build

# 运行阶段：Nginx 托管静态文件并反向代理 API 与 SSE
FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
