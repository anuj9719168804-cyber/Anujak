"""xvideos_resolver.py — resolves an XVideos video URL to every playable
format yt-dlp can find for it, shaped into the same response envelope as
xhamster_resolver.py in this project ("links"/"m3u8_links"/"videoDetails"/
"entitlement", credited "Ak"), so a caller already coded against the
xHamster endpoint gets an identical shape from this one.

Unlike xHamster, XVideos' own yt-dlp extractor (XVideosIE) hands back
genuinely distinct progressive (direct MP4) formats — a "low" and a
"high" quality file — alongside its HLS (.m3u8) master playlist
qualities, so both "links" (progressive) and "m3u8_links" (HLS) are
populated here, not just one of them.

Two things from the original sample response this envelope matches are
deliberately NOT replicated, same as in xhamster_resolver.py:
  - Any proprietary deep-link/app-open URI scheme — this returns
    yt-dlp's actual format URL (a real .mp4/.m3u8 link) instead.
  - Any login/subscription paywall fields ("entitlement"/"isPro"/
    "gatedHd"/"lockReason") — this service has no such gating, so
    every quality yt-dlp finds is included, but the envelope fields are
    kept (with "allowed": true, no lock reasons) purely for
    shape-compatibility with anything coded against that original shape.
"""
import logging
import re
from urllib.parse import urlparse

import yt_dlp

logger = logging.getLogger("xvideos_api")


def _format_duration(seconds) -> str | None:
    """seconds -> "MM:SS", or "H:MM:SS" once it's an hour or longer.
    Identical helper to the one in xhamster_resolver.py — duplicated
    rather than imported so this file has no dependency on that one and
    can be dropped into another project on its own."""
    if seconds is None:
        return None
    try:
        total = int(seconds)
    except (TypeError, ValueError):
        return None
    if total < 0:
        return None
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# Mirrors yt-dlp's own yt_dlp.extractor.xvideos.XVideosIE._VALID_URL —
# not reproduced as a raw copy-paste, but checked against it directly
# (https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/extractor/xvideos.py,
# and its youtube-dl-era ancestor which is where this project confirmed
# the exact host list): xvideos.com, the numbered mirrors xvideos2.com
# and xvideos3.com, and the xvideos.es alt-domain — all with any number
# of subdomain labels in front (www., a two-letter locale like de./es.,
# etc.), same anchoring style as _XHAMSTER_YTDLP_NATIVE_RE in
# xhamster_resolver.py. yt-dlp occasionally adds another numbered mirror
# (xvideos4.com and similar get requested in yt-dlp's own issue tracker
# from time to time) — if one of those starts actually being served by
# yt-dlp's extractor, it needs adding here too; until then, an
# unrecognized numbered mirror is deliberately left OUT of this set
# rather than guessed at, and instead handled by the mirror-rewrite path
# below (same as any other unconfirmed clone).
_XVIDEOS_YTDLP_NATIVE_RE = re.compile(
    r"^(?:[\w-]+\.)*(?:xvideos[23]?\.com|xvideos\.es)$",
    re.IGNORECASE,
)

# A second, WIDER set: xvideos clone/mirror domains confirmed to be the
# same site under a different host but NOT matched by yt-dlp's own
# extractor regex above, so resolve_xvideos() below has to actively
# rewrite these to xvideos.com before handing off to yt-dlp (mirrors the
# _XHAMSTER_MIRROR_ONLY_RE pattern in xhamster_resolver.py exactly).
# xvideos.red specifically is confirmed live in yt-dlp's own issue
# tracker as serving the identical /video<id>/<slug> page shape while
# NOT being picked up by XVideosIE (yt-dlp/yt-dlp#16216) — same
# "clone page, not a different site" situation as the xHamster mirrors.
# Kept to just that one confirmed case rather than guessing at further
# xvideos-branded domains that haven't been verified the same way.
_XVIDEOS_MIRROR_ONLY_RE = re.compile(
    r"^(?:[\w-]+\.)*xvideos\.red$",
    re.IGNORECASE,
)

_XVIDEOS_HOST_RE = re.compile(
    r"^(?:[\w-]+\.)*(?:xvideos[23]?\.com|xvideos\.es|xvideos\.red)$",
    re.IGNORECASE,
)


def is_xvideos_link(url: str) -> bool:
    """Same approach as is_xhamster_link() in xhamster_resolver.py:
    checks the URL's actual hostname (not a crude "xvideos" in url
    substring check, which both under-matches real mirrors that don't
    contain that substring and over-matches unrelated URLs that merely
    mention the word) against the combined yt-dlp-native + confirmed-
    mirror host sets above."""
    try:
        host = urlparse(url).hostname or ""
    except Exception:
        return False
    return bool(_XVIDEOS_HOST_RE.match(host))


def _dedupe_by_height(formats):
    """Shared by both the progressive (MP4) and HLS passes below. Keeps
    ONE entry per actual quality tier (yt-dlp can hand back redundant
    CDN-edge mirrors of the same height, exactly as documented in
    xhamster_resolver.py's 2nd/3rd-pass notes), and — same fix as that
    file's 4th pass, applied here from the start rather than needing a
    live bug report first — picks the WIDEST candidate at each height
    rather than just whichever one happened to come first, so a
    same-height-but-narrower/cropped anomalous variant never wins over
    the correctly-proportioned one. Formats with no height at all (rare,
    but XVideos does occasionally omit it from a format dict) each keep
    their own slot since they can't collide with one another on height.
    Returns (ordered_list_of_best_formats, heightless_formats) — caller
    turns both into the response shape it needs."""
    best_by_height = {}
    height_order = []
    heightless = []
    for f in formats:
        height = f.get("height")
        if not height:
            heightless.append(f)
            continue
        width = f.get("width") or 0
        current = best_by_height.get(height)
        if current is None:
            height_order.append(height)
            best_by_height[height] = f
        elif width > (current.get("width") or 0):
            best_by_height[height] = f
    return [best_by_height[h] for h in height_order], heightless


def resolve_xvideos(url: str) -> dict:
    """Runs yt-dlp's extract_info (metadata only, skip_download) and
    buckets every format it finds into "links" (progressive MP4),
    "m3u8_links" (HLS manifests), or "audio_links" (audio-only). Every
    entry keeps yt-dlp's own URL as-is — no re-wrapping, no proprietary
    scheme, no gating. Raises on any yt-dlp failure (private/removed
    video, network error, etc.) — the /api/xvideos route in app.py turns
    that into a 502 with the error message, same pattern as /api/xhamster.

    Mirror-host rewrite: a link on a confirmed-mirror-but-not-yt-dlp-
    native domain (_XVIDEOS_MIRROR_ONLY_RE above — xvideos.red) is
    rewritten to xvideos.com before being handed to yt-dlp, for the same
    reason as xhamster_resolver.py's equivalent rewrite: yt-dlp's own
    XVideosIE regex doesn't include that host, so passing it straight
    through would pass is_xvideos_link() here and then fail one step
    later with a yt-dlp "Unsupported URL" that has nothing to do with
    the video itself. Same URL/ID shape throughout (/video<id>/<slug>),
    so rewriting just the host is safe and keeps the actual video ID
    untouched."""
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if host and not _XVIDEOS_YTDLP_NATIVE_RE.match(host):
        url = parsed._replace(netloc="xvideos.com").geturl()
        logger.info(f"[xvideos] mirror host {host!r} not recognized by yt-dlp natively, rewritten to xvideos.com")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        # Same reasoning as xhamster_resolver.py: "all" (not yt-dlp's
        # default best-match subset) is what makes "every quality
        # yt-dlp gets" mean every one it finds, not just the one it
        # would pick to actually play.
        "format": "all",
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = info.get("formats") or []
    progressive, hls, audio_links = [], [], []

    for f in formats:
        f_url = f.get("url")
        if not f_url:
            continue
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        is_hls = (f.get("protocol") or "").startswith("m3u8") or ".m3u8" in f_url.lower()
        is_audio_only = vcodec in (None, "none") and acodec not in (None, "none")

        if is_audio_only:
            audio_links.append({
                "title": f.get("format_note") or f.get("format_id") or "Audio",
                "url": f_url,
            })
            continue

        (hls if is_hls else progressive).append(f)

    links = []
    best_progressive, heightless_progressive = _dedupe_by_height(progressive)
    for f in best_progressive:
        links.append({"title": f"Video {f['height']}p", "url": f.get("url")})
    for f in heightless_progressive:
        label = f.get("format_note") or f.get("format_id") or "Video"
        links.append({"title": label, "url": f.get("url")})

    m3u8_links = []
    best_hls, heightless_hls = _dedupe_by_height(hls)
    for f in best_hls:
        m3u8_links.append({"title": f"Video {f['height']}p (HLS)", "url": f.get("url")})
    for f in heightless_hls:
        label = f.get("format_note") or f.get("format_id") or "Video"
        m3u8_links.append({"title": f"{label} (HLS)", "url": f.get("url")})

    # NOTE on quality ceiling: nothing here caps resolution — every
    # height yt-dlp's extractor finds is kept. Whether a given video
    # actually has a high-resolution HLS rendition, or only the
    # low/high progressive pair, depends entirely on what XVideos itself
    # encoded for THIS specific upload.

    thumbnails = []
    seen = set()
    for t_url in [info.get("thumbnail")] + [t.get("url") for t in (info.get("thumbnails") or [])]:
        if t_url and t_url not in seen:
            thumbnails.append({"url": t_url})
            seen.add(t_url)

    # Key order matches xhamster_resolver.py's response shape exactly:
    # title -> duration -> thumbnail (all inside videoDetails), then
    # m3u8_links (quality links) right after, before the less-used
    # envelope fields.
    return {
        "videoDetails": {
            "title": info.get("title"),
            "duration": _format_duration(info.get("duration")),
            "lengthSeconds": info.get("duration"),
            "thumbnails": thumbnails,
        },
        "m3u8_links": m3u8_links,
        "audio_links": audio_links,
        "entitlement": {
            "adsAllowed": True,
            "countdownSeconds": 0,
            "hd": {"allowed": True, "limit": 0, "remaining": 0, "resetsAt": None},
            "tier": "anon",
        },
        "isAuthenticated": False,
        "isPro": False,
        "links": links,
        "tier": "anon",
    }
