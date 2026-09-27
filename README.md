# 🚀 XVideos Resolver API

Standalone **XVideos-only** REST API built with FastAPI and yt-dlp, following the simple structure of the Ak resolver projects.

## What it supports

- XVideos video URLs only
- Metadata returned by yt-dlp
- Progressive/direct video formats (low/high quality MP4)
- HLS/m3u8 formats when yt-dlp exposes them
- Audio-only formats when available
- Thumbnail information
- Per-IP rate limiting
- `/health` health check
- Docker deployment
- Render / Railway / VPS / Docker-compatible hosting

It does **not** include Diskwala, xHamster, YouTube, Instagram, Telegram sessions, Chromium, Node.js, Cloudflare bypass, or FlareSolverr.

## Project structure

```text
xvideos-api/
├── app.py
├── config.py
├── xvideos_resolver.py
├── requirements.txt
├── Dockerfile
├── entrypoint.sh
├── .env.example
├── .dockerignore
├── .gitignore
└── README.md
```

## API

### Root

```http
GET /
```

### Health

```http
GET /health
```

### Resolve

```http
GET /api/xvideos?url=<XVIDEOS_VIDEO_URL>
```

Example:

```bash
curl --get 'http://localhost:8000/api/xvideos' \
  --data-urlencode 'url=https://www.xvideos.com/video1234567/example_video_name'
```

The response keeps yt-dlp's actual media URLs; the resolver does not invent a custom deep-link scheme.

## Run locally

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

Then open:

```text
http://127.0.0.1:8000/docs
```

## Docker

```bash
docker build -t xvideos-api .
docker run -d --name xvideos-api \
  --restart unless-stopped \
  -p 8000:8000 \
  -e PORT=8000 \
  xvideos-api
```

## Render / Railway

Use the Dockerfile deployment option. The application reads the platform's `PORT` environment variable.

For a VPS, put Nginx/Caddy in front of port `8000` and add HTTPS with your preferred certificate provider.

## Environment variables

```env
PORT=8000
RATE_LIMIT_PER_MINUTE=30
```

Do not commit secrets into Git.

## Notes

A source video can be private, removed, region-restricted, login-gated, rate-limited, or otherwise unavailable to yt-dlp. In those cases the API returns HTTP `502` with the resolver error instead of pretending that a link was resolved.
