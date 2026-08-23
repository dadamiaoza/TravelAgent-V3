FROM python:3.12-slim

WORKDIR /app

# 先复制依赖元数据和源码，安装 Python 包
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY run_server.py ./
COPY start.sh ./

RUN pip install --no-cache-dir . \
    && chmod +x start.sh

EXPOSE 8000

# 启动前先跑数据库迁移，再启动 FastAPI
CMD ["./start.sh"]
