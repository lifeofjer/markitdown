FROM python:3.13-slim-bullseye

ENV DEBIAN_FRONTEND=noninteractive
ENV EXIFTOOL_PATH=/usr/bin/exiftool
ENV FFMPEG_PATH=/usr/bin/ffmpeg
ENV MARKITDOWN_ENABLE_PLUGINS=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    exiftool \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY packages/ /app/packages/
COPY rest_api.py /app/rest_api.py

RUN pip --no-cache-dir install \
    /app/packages/markitdown[all] \
    /app/packages/markitdown-mcp \
    /app/packages/markitdown-ocr \
    /app/packages/markitdown-sample-plugin \
    openai \
    fastapi \
    python-multipart

EXPOSE 8000

CMD ["python", "rest_api.py"]
