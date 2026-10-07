#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import re
import shutil
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

USER_AGENT = "Landell-Wave/2.1 (+https://github.com/limapablo/Landell-Wave)"
DISCOVERY = "https://all.api.radio-browser.info/json/servers"
FALLBACKS = [
    "https://de1.api.radio-browser.info",
    "https://nl1.api.radio-browser.info",
]
CITIES_URL = "https://download.geonames.org/export/dump/cities1000.zip"
ADMIN1_URL = "https://download.geonames.org/export/dump/admin1CodesASCII.txt"

UNKNOWN_REGION = "Unknown region"
UNKNOWN_CITY = "Unknown city"

MAX_HTTP_BYTES = 150 * 1024 * 1024
MAX_GEONAMES_UNCOMPRESSED_BYTES = 250 * 1024 * 1024
MAX_STATIONS = 500_000
DEFAULT_MAX_CHECK_AGE_HOURS = 48
MAX_URL_LENGTH = 4_096

COUNTRY_CODE_RE = re.compile(r"^[A-Z]{2}$")
ADMIN1_KEY_RE = re.compile(r"^[A-Z]{2}\.[A-Z0-9.-]{1,16}$")
RADIO_BROWSER_HOST_RE = re.compile(
    r"^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.api\.radio-browser\.info$",
    re.IGNORECASE,
)
IANA_TIMEZONE_RE = re.compile(r"^[A-Za-z0-9._+-]+(?:/[A-Za-z0-9._+-]+)*$")
LOCAL_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home.arpa",
)


@dataclass(frozen=True)
class City:
    name: str
    lat: float
    lon: float
    country_code: str
    admin1_code: str
    timezone: str = ""


def sanitize_text(value: Any, fallback: str = "", max_len: int = 512) -> str:
    """Normalize untrusted text and strip invisible/control characters."""
    raw = str(value or "")
    safe = "".join(
        " " if unicodedata.category(ch) in {"Cc", "Cf", "Cs"} else ch
        for ch in raw
    )
    safe = " ".join(safe.split()).strip()
    if max_len > 0:
        safe = safe[:max_len]
    return safe or fallback[:max_len]


# Backward-compatible helper name used by older tests/callers.
def clean(value: Any, fallback: str = "", max_len: int = 512) -> str:
    return sanitize_text(value, fallback, max_len)


def safe_int(value: Any, default: int = 0, minimum: int = 0, maximum: int = 1_000_000_000) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return max(minimum, min(parsed, maximum))


def parse_float(
    value: Any,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(parsed):
        return None
    if minimum is not None and parsed < minimum:
        return None
    if maximum is not None and parsed > maximum:
        return None
    return parsed


def country_code(value: Any) -> str:
    code = sanitize_text(value, max_len=8).upper()
    return code if COUNTRY_CODE_RE.fullmatch(code) else "ZZ"


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9._-]+", "-", normalized).strip("-._").lower() or "unknown"


def is_public_host(host: str | None) -> bool:
    """Reject obvious loopback/private/link-local/internal destinations."""
    if not host:
        return False
    normalized = host.lower().rstrip(".")
    if (
        normalized == "localhost"
        or normalized.endswith(LOCAL_HOST_SUFFIXES)
        or len(normalized) > 253
    ):
        return False

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        # Public DNS names must not be single-label names in this project.
        return "." in normalized

    return address.is_global


def normalize_web_url(value: Any, allow_http: bool = False) -> str:
    url = sanitize_text(value, max_len=MAX_URL_LENGTH)
    if not url:
        return ""

    try:
        parsed = urllib.parse.urlsplit(url)
        allowed = {"https"} | ({"http"} if allow_http else set())
        if parsed.scheme.lower() not in allowed:
            return ""
        if not parsed.hostname or parsed.username or parsed.password:
            return ""
        if not is_public_host(parsed.hostname):
            return ""
        # Accessing .port also validates malformed/out-of-range ports.
        _ = parsed.port
    except (TypeError, ValueError):
        return ""

    return url


def safe_web_url(value: Any, allow_http: bool = False) -> bool:
    return bool(normalize_web_url(value, allow_http=allow_http))


def valid_stream(value: Any) -> bool:
    return safe_web_url(value, allow_http=True)


def haversine_km(a: float, b: float, c: float, d: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(a), math.radians(c)
    dp = math.radians(c - a)
    dl = math.radians(d - b)
    x = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(x))


def get(
    url: str,
    timeout: int = 120,
    retries: int = 3,
    max_bytes: int = MAX_HTTP_BYTES,
) -> bytes:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Build-time downloads require HTTPS")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json,text/plain,application/zip,*/*",
        },
    )
    error: Exception | None = None

    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                final = urllib.parse.urlsplit(response.geturl())
                if final.scheme != "https":
                    raise RuntimeError("Refusing HTTPS downgrade redirect")

                content_length = response.headers.get("Content-Length")
                if content_length and safe_int(content_length, maximum=10**12) > max_bytes:
                    raise RuntimeError("Remote payload exceeds size limit")

                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise RuntimeError("Remote payload exceeds size limit")
                return data
        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
            RuntimeError,
            ValueError,
        ) as exc:
            error = exc
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))

    raise RuntimeError(f"Failed to fetch {url}: {error}")


def download(url: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.stat().st_size == 0:
        temp = path.with_suffix(path.suffix + ".part")
        temp.write_bytes(get(url))
        temp.replace(path)
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_admin1(path: Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if len(fields) < 2:
            continue
        key = sanitize_text(fields[0], max_len=24).upper()
        value = sanitize_text(fields[1], max_len=160)
        if ADMIN1_KEY_RE.fullmatch(key) and value:
            output[key] = value
    return output


def load_cities(path: Path) -> tuple[dict[tuple[str, int, int], list[City]], dict[str, list[City]]]:
    buckets: dict[tuple[str, int, int], list[City]] = defaultdict(list)
    by_country: dict[str, list[City]] = defaultdict(list)

    with zipfile.ZipFile(path) as archive:
        candidates = [
            info
            for info in archive.infolist()
            if not info.is_dir() and info.filename.endswith(".txt")
        ]
        if len(candidates) != 1:
            raise RuntimeError("Unexpected GeoNames archive layout")

        info = candidates[0]
        if info.file_size > MAX_GEONAMES_UNCOMPRESSED_BYTES:
            raise RuntimeError("GeoNames archive exceeds uncompressed size limit")

        with archive.open(info) as handle:
            for raw in handle:
                fields = raw.decode("utf-8", "replace").rstrip("\n").split("\t")
                if len(fields) < 11:
                    continue

                cc = country_code(fields[8])
                lat = parse_float(fields[4], -90, 90)
                lon = parse_float(fields[5], -180, 180)
                name = sanitize_text(fields[1], max_len=160)
                admin1 = sanitize_text(fields[10], max_len=16)
                timezone_name = sanitize_text(
                    fields[17] if len(fields) > 17 else "",
                    max_len=64,
                )
                if timezone_name and not IANA_TIMEZONE_RE.fullmatch(timezone_name):
                    timezone_name = ""

                if cc == "ZZ" or lat is None or lon is None or not name:
                    continue

                city = City(name, lat, lon, cc, admin1, timezone_name)
                buckets[(cc, math.floor(lat), math.floor(lon))].append(city)
                by_country[cc].append(city)

    return buckets, by_country


def nearest_city(
    lat: float,
    lon: float,
    cc: str,
    buckets: dict[tuple[str, int, int], list[City]],
    by_country: dict[str, list[City]],
    max_km: float,
) -> tuple[City | None, float | None]:
    candidates: list[City] = []
    for delta_lat in range(-2, 3):
        for delta_lon in range(-2, 3):
            candidates.extend(
                buckets.get(
                    (cc, math.floor(lat) + delta_lat, math.floor(lon) + delta_lon),
                    (),
                )
            )

    if not candidates and len(by_country.get(cc, ())) <= 1000:
        candidates = by_country.get(cc, [])

    best: City | None = None
    distance = float("inf")
    for city in candidates:
        candidate_distance = haversine_km(lat, lon, city.lat, city.lon)
        if candidate_distance < distance:
            best, distance = city, candidate_distance

    if best is None or distance > max_km:
        return None, None
    return best, round(distance, 1)


def servers() -> list[str]:
    output: list[str] = []
    try:
        payload = json.loads(get(DISCOVERY, 20, 2, max_bytes=1024 * 1024))
        if isinstance(payload, list):
            for item in payload:
                if not isinstance(item, dict):
                    continue
                host = sanitize_text(item.get("name"), max_len=253).lower().rstrip(".")
                if host and RADIO_BROWSER_HOST_RE.fullmatch(host):
                    output.append("https://" + host)
    except (json.JSONDecodeError, RuntimeError, ValueError, TypeError) as exc:
        print(f"[warn] discovery failed: {exc}", file=sys.stderr)

    for fallback in FALLBACKS:
        if fallback not in output:
            output.append(fallback)

    # Preserve discovery order while removing duplicates.
    return list(dict.fromkeys(output))


def fetch_stations(limit: int, max_check_age_hours: int | None = None) -> tuple[list[dict[str, Any]], str, str]:
    """Fetch the catalog in bounded pages.

    A single 100k-row response is large enough to trigger gateway failures on
    some Radio Browser mirrors. Pagination also bounds per-request memory and
    gives us a clean failover boundary: if any page fails, retry the complete
    snapshot on the next mirror rather than mixing mirrors in one build.
    """
    page_size = min(5000, limit)
    errors: list[str] = []
    minimum_expected = min(1000, limit)

    for server in servers():
        rows: list[dict[str, Any]] = []
        digest = hashlib.sha256()
        offset = 0

        try:
            while offset < limit:
                requested = min(page_size, limit - offset)
                query = urllib.parse.urlencode(
                    {
                        "hidebroken": "true",
                        "order": "country",
                        "reverse": "false",
                        "offset": str(offset),
                        "limit": str(requested),
                    }
                )
                raw = get(
                    f"{server}/json/stations/search?{query}",
                    120,
                    3,
                    max_bytes=32 * 1024 * 1024,
                )
                page = json.loads(raw)

                if not isinstance(page, list) or not all(
                    isinstance(item, dict) for item in page
                ):
                    raise RuntimeError("unexpected catalog page shape")

                digest.update(offset.to_bytes(8, "big"))
                digest.update(raw)
                rows.extend(page)

                print(
                    f"[info] {server}: page offset={offset:,} "
                    f"rows={len(page):,} total={len(rows):,}"
                )

                if len(page) < requested:
                    break
                offset += len(page)

            if len(rows) < minimum_expected:
                raise RuntimeError(
                    f"catalog unexpectedly small ({len(rows)} rows)"
                )

            if max_check_age_hours is not None:
                validated = dedupe(rows, max_check_age_hours, diagnostics=True)
                if not validated:
                    raise RuntimeError("No valid public station streams survived validation")

            print(f"[info] fetched {len(rows):,} stations from {server}")
            return rows, digest.hexdigest(), server

        except (
            json.JSONDecodeError,
            RuntimeError,
            ValueError,
            TypeError,
            urllib.error.URLError,
        ) as exc:
            errors.append(f"{server}: {exc}")
            print(
                f"[warn] abandoning mirror after {len(rows):,} rows: "
                f"{server}: {exc}",
                file=sys.stderr,
            )

    raise RuntimeError("Radio Browser mirrors failed: " + "; ".join(errors))


def parse_utc_timestamp(value: Any) -> datetime | None:
    text = sanitize_text(value, max_len=64)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def station_check_rejection(
    station: dict[str, Any],
    max_age_hours: int = DEFAULT_MAX_CHECK_AGE_HOURS,
    now: datetime | None = None,
) -> str:
    if safe_int(station.get("lastcheckok"), maximum=1) != 1:
        return "failed_check"

    checked_at = parse_utc_timestamp(
        station.get("lastchecktime_iso8601")
        or station.get("lastcheckoktime_iso8601")
    )
    if checked_at is None:
        return "missing_or_invalid_timestamp"

    reference = now or datetime.now(timezone.utc)
    age_seconds = (reference - checked_at).total_seconds()
    if age_seconds < 0:
        return "future_timestamp"
    return "stale_check" if age_seconds > max_age_hours * 3600 else ""


def recently_verified(
    station: dict[str, Any],
    max_age_hours: int = DEFAULT_MAX_CHECK_AGE_HOURS,
    now: datetime | None = None,
) -> bool:
    return not station_check_rejection(station, max_age_hours, now)


def score(station: dict[str, Any]) -> int:
    return (
        1000 * safe_int(station.get("lastcheckok"), maximum=1)
        + min(safe_int(station.get("bitrate"), maximum=10_000), 512)
        + min(safe_int(station.get("votes"), maximum=1_000_000_000), 500)
    )


def dedupe(rows: list[dict[str, Any]], max_check_age_hours: int = DEFAULT_MAX_CHECK_AGE_HOURS, diagnostics: bool = False) -> list[dict[str, Any]]:
    chosen: dict[str, dict[str, Any]] = {}
    rejected: dict[str, int] = defaultdict(int)

    reference_time = datetime.now(timezone.utc)

    for station in rows:
        reason = station_check_rejection(station, max_check_age_hours, reference_time)
        if reason:
            rejected[reason] += 1
            continue

        stream = normalize_web_url(
            station.get("url_resolved") or station.get("url"),
            allow_http=True,
        )
        if not stream:
            rejected["invalid_stream"] += 1
            continue

        station_id = sanitize_text(station.get("stationuuid"), max_len=128)
        key = station_id or stream
        candidate = dict(station)
        candidate["_stream"] = stream

        if key not in chosen or score(candidate) > score(chosen[key]):
            chosen[key] = candidate

    if diagnostics:
        print(
            f"[info] validation: now={reference_time.isoformat()} "
            f"max_check_age_hours={max_check_age_hours} input={len(rows)} "
            f"accepted={len(chosen)} rejected={json.dumps(dict(rejected), sort_keys=True)}"
        )
    return list(chosen.values())


def _split_metadata(value: Any, max_items: int, item_max_len: int) -> list[str]:
    output: list[str] = []
    for item in sanitize_text(value, max_len=4096).split(","):
        normalized = sanitize_text(item, max_len=item_max_len)
        if normalized and normalized not in output:
            output.append(normalized)
        if len(output) >= max_items:
            break
    return output


def make_record(
    station: dict[str, Any],
    buckets: dict[tuple[str, int, int], list[City]],
    by_country: dict[str, list[City]],
    admin: dict[str, str],
    max_km: float,
) -> dict[str, Any]:
    cc = country_code(station.get("countrycode"))
    country = sanitize_text(station.get("country"), cc, 128)
    region = sanitize_text(station.get("state"), max_len=160)

    lat = parse_float(station.get("geo_lat"), -90, 90)
    lon = parse_float(station.get("geo_long"), -180, 180)

    city: City | None = None
    city_distance: float | None = None
    if lat is not None and lon is not None and cc != "ZZ":
        city, city_distance = nearest_city(lat, lon, cc, buckets, by_country, max_km)

    if city and not region:
        region = admin.get(f"{cc}.{city.admin1_code}", "")
    region = (
        region
        or sanitize_text(station.get("iso_3166_2"), max_len=32)
        or UNKNOWN_REGION
    )

    homepage = normalize_web_url(station.get("homepage"), allow_http=False)
    favicon = normalize_web_url(station.get("favicon"), allow_http=False)

    return {
        "id": sanitize_text(station.get("stationuuid"), max_len=128),
        "name": sanitize_text(station.get("name"), "Unnamed station", 256),
        "country": country,
        "country_code": cc,
        "region": sanitize_text(region, UNKNOWN_REGION, 160),
        "city": sanitize_text(city.name if city else UNKNOWN_CITY, UNKNOWN_CITY, 160),
        "city_distance_km": city_distance,
        "timezone": city.timezone if city else "",
        "stream": station["_stream"],
        "homepage": homepage,
        "favicon": favicon,
        "tags": _split_metadata(station.get("tags"), 20, 64),
        "languages": _split_metadata(station.get("language"), 10, 64),
        "codec": sanitize_text(station.get("codec"), max_len=32),
        "bitrate": safe_int(station.get("bitrate"), maximum=10_000),
        "votes": safe_int(station.get("votes"), maximum=1_000_000_000),
        "lat": lat,
        "lon": lon,
    }


def esc(value: Any) -> str:
    return (
        sanitize_text(value, max_len=MAX_URL_LENGTH)
        .replace('"', "'")
        .replace("\r", " ")
        .replace("\n", " ")
    )


def build_m3u(rows: list[dict[str, Any]]) -> str:
    lines = ["#EXTM3U"]
    for row in rows:
        group = " | ".join([row["country"], row["region"], row["city"]])
        attrs = [
            f'tvg-id="{esc(row["id"])}"',
            f'group-title="{esc(group)}"',
        ]
        if row.get("favicon"):
            attrs.insert(1, f'tvg-logo="{esc(row["favicon"])}"')
        lines.extend(
            [
                f'#EXTINF:-1 {" ".join(attrs)},{esc(row["name"])}',
                row["stream"],
            ]
        )
    return "\n".join(lines) + "\n"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def build(output: Path, cache: Path, limit: int, max_km: float, max_check_age_hours: int) -> None:
    if not 1 <= limit <= MAX_STATIONS:
        raise ValueError(f"station limit must be between 1 and {MAX_STATIONS}")
    if not 1 <= max_km <= 500:
        raise ValueError("max city distance must be between 1 and 500 km")
    if not 1 <= max_check_age_hours <= 168:
        raise ValueError("max check age must be between 1 and 168 hours")

    cities_path = download(CITIES_URL, cache / "cities1000.zip")
    admin_path = download(ADMIN1_URL, cache / "admin1CodesASCII.txt")
    buckets, by_country = load_cities(cities_path)
    admin = load_admin1(admin_path)

    raw, radio_digest, radio_server = fetch_stations(limit, max_check_age_hours)
    stations = dedupe(raw, max_check_age_hours)
    if not stations:
        raise RuntimeError("No valid public station streams survived validation")

    records = [
        make_record(station, buckets, by_country, admin, max_km)
        for station in stations
    ]
    records.sort(
        key=lambda row: (
            row["country"].casefold(),
            row["region"].casefold(),
            row["city"].casefold(),
            row["name"].casefold(),
        )
    )

    data = output / "data"
    playlists = output / "playlists"
    countries = data / "countries"
    country_playlists = playlists / "countries"

    for directory in (data, playlists, countries, country_playlists):
        directory.mkdir(parents=True, exist_ok=True)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["country_code"]].append(record)

    metadata: list[dict[str, Any]] = []
    matched = 0

    for code, rows in sorted(
        grouped.items(),
        key=lambda item: item[1][0]["country"].casefold(),
    ):
        # country_code() guarantees this cannot escape the target directory.
        if not COUNTRY_CODE_RE.fullmatch(code) and code != "ZZ":
            raise RuntimeError("Unsafe country code reached output layer")

        matched += sum(row["city"] != UNKNOWN_CITY for row in rows)
        item = {
            "code": code,
            "name": rows[0]["country"],
            "stations": len(rows),
            "regions": len({row["region"] for row in rows}),
            "cities": len(
                {
                    (row["region"], row["city"])
                    for row in rows
                    if row["city"] != UNKNOWN_CITY
                }
            ),
            "file": f"data/countries/{code}.json",
            "playlist": f"playlists/countries/{code}.m3u",
        }
        metadata.append(item)

        write_json(countries / f"{code}.json", {"country": item, "stations": rows})
        (country_playlists / f"{code}.m3u").write_text(
            build_m3u(rows),
            encoding="utf-8",
        )

    generated = (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )

    index = {
        "project": "Landell-Wave",
        "schema_version": 2,
        "generated_at": generated,
        "station_count": len(records),
        "country_count": len(metadata),
        "city_matched_count": matched,
        "city_match_rate": round(matched / len(records), 4),
        "max_city_distance_km": max_km,
        "quality_policy": {
            "hidebroken": True,
            "lastcheckok_required": True,
            "max_check_age_hours": max_check_age_hours,
        },
        "countries": metadata,
        "sources": {
            "radio_browser": {
                "server": radio_server,
                "payload_sha256": radio_digest,
            },
            "geonames": {
                "cities1000_sha256": sha256_file(cities_path),
                "admin1_sha256": sha256_file(admin_path),
            },
        },
    }

    search_records = [
        {
            "id": row["id"],
            "name": row["name"],
            "country": row["country"],
            "country_code": row["country_code"],
            "region": row["region"],
            "city": row["city"],
            "timezone": row["timezone"],
            "stream": row["stream"],
            "homepage": row["homepage"],
            "tags": row["tags"],
            "languages": row["languages"],
            "codec": row["codec"],
            "bitrate": row["bitrate"],
        }
        for row in records
    ]

    write_json(data / "index.json", index)
    write_json(data / "search.json", {"stations": search_records})
    write_json(data / "sample.json", records[:100])
    (playlists / "world.m3u").write_text(build_m3u(records), encoding="utf-8")

    print(
        f"[done] {len(records):,} stations / {len(metadata)} countries / "
        f"{matched:,} city matches"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("public"))
    parser.add_argument("--cache", type=Path, default=Path(".cache"))
    parser.add_argument("--station-limit", type=int, default=MAX_STATIONS)
    parser.add_argument("--max-city-distance-km", type=float, default=80)
    parser.add_argument(
        "--max-check-age-hours",
        type=int,
        default=DEFAULT_MAX_CHECK_AGE_HOURS,
        help="Only include stations with a successful Radio Browser check this recent.",
    )
    parser.add_argument("--clean-generated", action="store_true")
    args = parser.parse_args()

    if args.clean_generated:
        for generated_dir in (args.output / "data", args.output / "playlists"):
            if generated_dir.exists():
                shutil.rmtree(generated_dir)

    build(args.output, args.cache, args.station_limit, args.max_city_distance_km, args.max_check_age_hours)


if __name__ == "__main__":
    main()
