FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
ENV PYTHONPATH=/app

CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]

