"""Standalone XVideos-only resolver API."""
import logging
import time
from collections import defaultdict, deque

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import config
import xvideos_resolver

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("xvideos_api")

app = FastAPI(
    title="XVideos Resolver API",
    description="Standalone XVideos-only video resolver API.",
    version="1.0.0",
)

_hits: dict[str, deque] = defaultdict(deque)
EXAMPLE_URL = "https://www.xvideos.com/video1234567/example_video_name"


def _check_rate_limit(client_ip: str):
    now = time.time()
    window = _hits[client_ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= config.RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="Rate limit exceeded, try again in a bit.")
    window.append(now)


@app.get("/", include_in_schema=False)
def root():
    return {
        "status": True,
        "creator": "XVideos API",
        "message": "XVideos Resolver API is online",
        "version": "1.0.0",
        "example": {
            "url": EXAMPLE_URL,
            "resolve": f"/api/xvideos?url={EXAMPLE_URL}",
        },
        "endpoints": {
            "resolve": "/api/xvideos?url=<XVIDEOS_VIDEO_URL>",
            "health": "/health",
        },
    }


@app.get("/health")
def health():
    return {"status": True, "service": "xvideos-api", "provider": "XVideos"}


@app.get("/api/xvideos")
async def xvideos(url: str = Query(..., description="XVideos video link")):
    if not xvideos_resolver.is_xvideos_link(url):
        return JSONResponse(
            status_code=400,
            content={"status": False, "error": "Only XVideos links are supported here."},
        )
    try:
        data = await run_in_threadpool(xvideos_resolver.resolve_xvideos, url)
    except Exception as e:
        logger.warning("XVideos resolve failed for %s: %s", url, e)
        return JSONResponse(status_code=502, content={"status": False, "error": str(e)})
    return {"status": True, "data": data, "credit": "Ak"}


@app.middleware("http")
async def rate_limit_mw(request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    try:
        _check_rate_limit(client_ip)
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"status": False, "error": e.detail})
    return await call_next(request)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, reload=False)
