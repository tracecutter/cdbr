FROM python:3.13-slim-bookworm

ARG NPKGLIB_VERSION=1.2.0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

RUN apt-get update \
    && apt-get install --no-install-recommends --yes \
        fonts-dejavu-core \
        fonts-comic-neue \
        imagemagick \
        libheif1 \
        tesseract-ocr \
    && ln -s /usr/bin/convert /usr/local/bin/magick \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY cdbr ./cdbr
COPY solutions/playable ./solutions/playable

RUN pip install --no-cache-dir \
        "https://github.com/tracecutter/npkglib/archive/refs/tags/v${NPKGLIB_VERSION}.tar.gz" \
    && pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 cdbr

USER cdbr

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["cdbrd"]
