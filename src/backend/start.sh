#!/bin/sh
set -e

# 部署时自动执行数据库迁移，确保表结构存在
alembic upgrade head

# Railway 会注入 PORT，本地默认 8000
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
