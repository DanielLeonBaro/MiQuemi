FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DENO_INSTALL=/opt/deno
RUN apt-get update -qq \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl unzip \
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL https://deno.land/install.sh -o /tmp/install-deno.sh \
    && CI=1 sh /tmp/install-deno.sh \
    && rm /tmp/install-deno.sh
ENV PATH="/opt/deno/bin:${PATH}" HOST=0.0.0.0 PORT=10000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --create-home --uid 1000 app
COPY server.py local_tools.py .
COPY web ./web
USER app
EXPOSE 10000
CMD ["python", "server.py"]
