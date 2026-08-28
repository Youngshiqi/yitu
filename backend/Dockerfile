FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PATH=/app/.venv/bin:$PATH \
    UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
    UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/

# 国内镜像源加速：pip 与 uv 均走阿里云 PyPI
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ uv

COPY pyproject.toml uv.lock ./
# 不用 --frozen：让 uv 以阿里云镜像为默认源重新解析并下载 wheel
# （uv.lock 锁定的 wheel URL 指向国外 pythonhosted，frozen 会强制走国外地址导致极慢）
RUN uv sync --no-dev --default-index https://mirrors.aliyun.com/pypi/simple/

COPY alembic.ini ./
COPY migrations ./migrations
COPY data ./data
COPY src ./src

RUN addgroup --system yitu && \
    adduser --system --ingroup yitu yitu && \
    mkdir -p /app/var/knowledge && \
    chown -R yitu:yitu /app

USER yitu

CMD [".venv/bin/uvicorn", "yitu.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
