#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import json
import sys
import urllib.parse
from pathlib import Path

MAX_INDEX_BYTES = 5 * 1024 * 1024
MAX_SEARCH_INDEX_BYTES = 40 * 1024 * 1024
MAX_COUNTRY_JSON_BYTES = 80 * 1024 * 1024
MAX_M3U_BYTES = 200 * 1024 * 1024
ALLOWED_STATIC_EXTENSIONS = {".html", ".css", ".js", ".json", ".m3u", ".txt"}
LOCAL_SUFFIXES = (".localhost", ".local", ".internal", ".lan", ".home.arpa")


def fail(message: str) -> None:
    raise SystemExit(f"validation failed: {message}")


def public_host(host: str | None) -> bool:
    if not host:
        return False
    host = host.lower().rstrip(".")
    if host == "localhost" or host.endswith(LOCAL_SUFFIXES):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return "." in host


def valid_url(value: str, allow_http: bool = False) -> bool:
    try:
        u = urllib.parse.urlsplit(value)
        if u.scheme not in ({"https", "http"} if allow_http else {"https"}):
            return False
        if not u.hostname or u.username or u.password or not public_host(u.hostname):
            return False
        _ = u.port
        return True
    except (TypeError, ValueError):
        return False


def validate_site(root: Path) -> None:
    if not root.is_dir():
        fail("output root is missing")

    required = [
        root / "index.html",
        root / "assets" / "app.js",
        root / "assets" / "styles.css",
        root / "data" / "index.json",
        root / "data" / "search.json",
        root / "playlists" / "world.m3u",
    ]
    for path in required:
        if not path.is_file():
            fail(f"required artifact missing: {path.relative_to(root)}")

    for path in root.rglob("*"):
        if path.is_symlink():
            fail(f"symlink forbidden: {path.relative_to(root)}")
        if path.is_file() and path.suffix.lower() not in ALLOWED_STATIC_EXTENSIONS:
            fail(f"unexpected file type: {path.relative_to(root)}")

    index_path = root / "data" / "index.json"
    if index_path.stat().st_size > MAX_INDEX_BYTES:
        fail("index.json exceeds size policy")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("schema_version") != 2:
        fail("unexpected catalog schema version")
    if not isinstance(index.get("station_count"), int) or index["station_count"] <= 0:
        fail("invalid station_count")
    if not isinstance(index.get("countries"), list) or not index["countries"]:
        fail("country index is empty")

    seen = set()
    counted = 0
    for country in index["countries"]:
        code = country.get("code")
        if not isinstance(code, str) or len(code) != 2 or not code.isalpha() or not code.isupper():
            if code != "ZZ":
                fail(f"unsafe country code: {code!r}")
        if code in seen:
            fail(f"duplicate country code: {code}")
        seen.add(code)

        path = root / "data" / "countries" / f"{code}.json"
        if not path.is_file():
            fail(f"missing country payload: {code}")
        if path.stat().st_size > MAX_COUNTRY_JSON_BYTES:
            fail(f"country payload too large: {code}")

        payload = json.loads(path.read_text(encoding="utf-8"))
        stations = payload.get("stations")
        if not isinstance(stations, list):
            fail(f"invalid station list: {code}")

        counted += len(stations)
        for station in stations:
            stream = station.get("stream", "")
            if not valid_url(stream, allow_http=True):
                fail(f"unsafe stream URL in {code}")
            homepage = station.get("homepage", "")
            if homepage and not valid_url(homepage):
                fail(f"unsafe homepage URL in {code}")
            favicon = station.get("favicon", "")
            if favicon and not valid_url(favicon):
                fail(f"unsafe favicon URL in {code}")

    if counted != index["station_count"]:
        fail(f"station count mismatch: index={index['station_count']} files={counted}")

    search_path = root / "data" / "search.json"
    if search_path.stat().st_size > MAX_SEARCH_INDEX_BYTES:
        fail("search.json exceeds size policy")
    search_payload = json.loads(search_path.read_text(encoding="utf-8"))
    search_stations = search_payload.get("stations")
    if not isinstance(search_stations, list) or len(search_stations) != counted:
        fail("global search index count mismatch")
    for station in search_stations:
        if not valid_url(station.get("stream", ""), allow_http=True):
            fail("unsafe stream URL in global search index")
        homepage = station.get("homepage", "")
        if homepage and not valid_url(homepage):
            fail("unsafe homepage URL in global search index")

    world = root / "playlists" / "world.m3u"
    if world.stat().st_size > MAX_M3U_BYTES:
        fail("world playlist exceeds size policy")
    if not world.read_text(encoding="utf-8", errors="strict").startswith("#EXTM3U\n"):
        fail("world playlist header invalid")

    print(f"[ok] validated {counted:,} stations across {len(seen)} countries")


def main() -> None:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "public")
    validate_site(root)


if __name__ == "__main__":
    main()
