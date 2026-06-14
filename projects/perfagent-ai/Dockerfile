FROM grafana/k6:latest AS k6

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=k6 /usr/bin/k6 /usr/local/bin/k6
COPY pyproject.toml README.md ./
COPY perfagent ./perfagent
COPY examples ./examples

RUN pip install --no-cache-dir .

ENTRYPOINT ["perfagent"]
CMD ["--help"]
