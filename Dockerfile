FROM node:20-slim AS nodebase

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

FROM base AS build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --upgrade pip \
 && pip install setuptools wheel \
 && pip wheel --no-deps --wheel-dir /wheels .

FROM base AS runtime
COPY --from=build /wheels /wheels
RUN pip install /wheels/*.whl \
 && find /wheels -name '*.whl' -delete

COPY --from=nodebase /usr/local/bin/node /usr/local/bin/node
COPY --from=nodebase /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
 && npm install -g supergateway

RUN useradd --create-home --uid 1000 vtop \
 && mkdir -p /app/.vtop-session \
 && chown vtop:vtop /app/.vtop-session
USER vtop
WORKDIR /app
VOLUME ["/app/.vtop-session"]
EXPOSE 3000
ENTRYPOINT ["supergateway"]
CMD ["--stdio", "vtop-mcp serve", "--port", "3000"]