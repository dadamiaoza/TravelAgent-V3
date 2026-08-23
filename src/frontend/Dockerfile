# ---- 构建阶段 ----
FROM node:20-alpine AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite 在构建时会把 VITE_ 开头的变量写进静态资源
ARG VITE_AMAP_KEY
ARG VITE_AMAP_SECURITY_CODE
ENV VITE_AMAP_KEY=$VITE_AMAP_KEY
ENV VITE_AMAP_SECURITY_CODE=$VITE_AMAP_SECURITY_CODE

RUN npm run build

# ---- 运行阶段 ----
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Railway 后端服务默认内部地址；实际部署时可在 Variables 覆盖
ENV BACKEND_URL=http://backend:8000
# Railway 注入的 PORT 会覆盖默认 80，保证监听平台转发端口
ENV PORT=80

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
