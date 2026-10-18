"""Bounded public-URL video acquisition."""
from __future__ import annotations

import ipaddress
import json
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from .types import FetchResult, Limits


class BlockedURLError(ValueError):
    pass


def check_public_url(url: str) -> None:
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
            raise ValueError("invalid_scheme_or_host")
        addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not addresses:
            raise ValueError("unresolved_host")
        for record in addresses:
            ip = ipaddress.ip_address(record[4][0])
            if not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip, "ipv4_mapped", None):
                raise ValueError("non_public_ip")
    except (ValueError, OSError) as exc:
        raise BlockedURLError(str(exc)) from exc


def fetch_video(url: str, dest_dir: Path, limits: Limits = Limits()) -> FetchResult:
    deadline = time.monotonic() + limits.download_timeout_s
    try:
        check_public_url(url)
        dest_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="fetch-", dir=dest_dir) as temp:
            staging = Path(temp)
            current = url
            with httpx.Client(follow_redirects=False, trust_env=False) as client:
                for hop in range(6):
                    check_public_url(current)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError
                    with client.stream("GET", current, timeout=remaining) as response:
                        if response.status_code in {301, 302, 303, 307, 308}:
                            if hop == 5:
                                return FetchResult("failed", error="too_many_redirects")
                            current = urljoin(current, response.headers["location"])
                            continue
                        response.raise_for_status()
                        if response.headers.get("content-type", "").lower().startswith("video/"):
                            size = 0
                            target = staging / "video.mp4"
                            with target.open("wb") as output:
                                for chunk in response.iter_bytes():
                                    if time.monotonic() >= deadline:
                                        raise TimeoutError
                                    size += len(chunk)
                                    if size > limits.max_video_bytes:
                                        return FetchResult("failed", error="too_large")
                                    output.write(chunk)
                            final = dest_dir / "video.mp4"
                            target.replace(final)
                            return FetchResult("fetched", final, "direct")
                        break
            check_public_url(current)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            result = subprocess.run(
                ["yt-dlp", "--no-playlist", "--max-filesize", str(limits.max_video_bytes),
                 "--write-info-json", "-o", str(staging / "video.%(ext)s"), "--", current],
                shell=False, timeout=min(remaining, limits.download_timeout_s), capture_output=True, text=True,
            )
            if result.returncode:
                lines = (result.stderr or "").strip().splitlines()
                return FetchResult("failed", error="ytdlp_failed:" + (lines[-1] if lines else "unknown"))
            files = [p for p in staging.iterdir() if p.is_file() and p.suffix not in {".json", ".part", ".ytdl"}]
            if len(files) != 1:
                return FetchResult("failed", error="ytdlp_failed:no_video")
            if files[0].stat().st_size > limits.max_video_bytes:
                return FetchResult("failed", error="too_large")
            caption = None
            for metadata in staging.glob("*.info.json"):
                caption = json.loads(metadata.read_text()).get("description")
            final = dest_dir / files[0].name
            files[0].replace(final)
            return FetchResult("fetched", final, "yt-dlp", caption=caption)
    except BlockedURLError as exc:
        return FetchResult("failed", error=f"blocked_url:{exc}")
    except (TimeoutError, httpx.TimeoutException, subprocess.TimeoutExpired):
        return FetchResult("failed", error="timeout")
    except (OSError, ValueError, httpx.HTTPError, KeyError) as exc:
        return FetchResult("failed", error=f"download_failed:{type(exc).__name__}")
