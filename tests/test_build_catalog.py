import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from build_catalog import (
    City,
    build_m3u,
    country_code,
    haversine_km,
    is_public_host,
    nearest_city,
    normalize_web_url,
    recently_verified,
    safe_int,
    safe_web_url,
    sanitize_text,
    slugify,
)


class CatalogTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("São Paulo"), "sao-paulo")

    def test_haversine(self):
        distance = haversine_km(-22.9068, -43.1729, -23.5505, -46.6333)
        self.assertGreater(distance, 350)
        self.assertLess(distance, 380)

    def test_nearest_city(self):
        rio = City("Rio de Janeiro", -22.9068, -43.1729, "BR", "21", "America/Sao_Paulo")
        buckets = {("BR", -23, -44): [rio]}
        city, distance = nearest_city(
            -22.91,
            -43.18,
            "BR",
            buckets,
            {"BR": [rio]},
            80,
        )
        self.assertEqual(city.name, "Rio de Janeiro")
        self.assertEqual(city.timezone, "America/Sao_Paulo")
        self.assertLess(distance, 2)

    def test_country_code_rejects_path_traversal(self):
        self.assertEqual(country_code("../../pwned"), "ZZ")
        self.assertEqual(country_code("BR/../../x"), "ZZ")
        self.assertEqual(country_code("br"), "BR")

    def test_external_url_policy(self):
        self.assertTrue(safe_web_url("https://example.com/radio"))
        self.assertFalse(safe_web_url("javascript:alert(1)"))
        self.assertFalse(safe_web_url("data:text/html,pwned"))
        self.assertFalse(safe_web_url("https://user:pass@example.com/"))
        self.assertFalse(safe_web_url("http://example.com/"))
        self.assertTrue(
            safe_web_url("http://example.com/live", allow_http=True)
        )

    def test_private_and_local_destinations_are_rejected(self):
        blocked = [
            "localhost",
            "localhost.",
            "127.0.0.1",
            "10.0.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "172.16.0.1",
            "::1",
            "fe80::1",
            "printer.local",
            "service.internal",
            "gateway.lan",
        ]
        for host in blocked:
            with self.subTest(host=host):
                self.assertFalse(is_public_host(host))

        self.assertTrue(is_public_host("8.8.8.8"))
        self.assertTrue(is_public_host("example.com"))

    def test_stream_cannot_target_local_network(self):
        self.assertEqual(
            normalize_web_url("http://127.0.0.1:8080/admin", allow_http=True),
            "",
        )
        self.assertEqual(
            normalize_web_url(
                "http://169.254.169.254/latest/meta-data/",
                allow_http=True,
            ),
            "",
        )
        self.assertEqual(
            normalize_web_url("http://radio.example.com/live", allow_http=True),
            "http://radio.example.com/live",
        )

    def test_control_characters_and_bidi_controls_are_removed(self):
        value = "Safe\nName\u202eexe.js\x00"
        cleaned = sanitize_text(value)
        self.assertNotIn("\n", cleaned)
        self.assertNotIn("\x00", cleaned)
        self.assertNotIn("\u202e", cleaned)
        self.assertIn("Safe", cleaned)

    def test_text_and_integer_bounds(self):
        self.assertEqual(len(sanitize_text("x" * 10_000, max_len=64)), 64)
        self.assertEqual(safe_int("999999", maximum=100), 100)
        self.assertEqual(safe_int("-50", minimum=0), 0)
        self.assertEqual(safe_int("not-an-int"), 0)

    def test_recent_station_check_policy(self):
        from datetime import datetime, timedelta, timezone

        now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
        recent = {
            "lastcheckok": 1,
            "lastchecktime_iso8601": (now - timedelta(hours=2)).isoformat(),
        }
        stale = {
            "lastcheckok": 1,
            "lastchecktime_iso8601": (now - timedelta(hours=72)).isoformat(),
        }
        failed = {
            "lastcheckok": 0,
            "lastchecktime_iso8601": now.isoformat(),
        }
        self.assertTrue(recently_verified(recent, 48, now))
        self.assertFalse(recently_verified(stale, 48, now))
        self.assertFalse(recently_verified(failed, 48, now))

    def test_m3u_escapes_control_characters(self):
        text = build_m3u(
            [
                {
                    "id": 'x"\n#EXTINF:-1,Injected',
                    "name": "Test\nFM",
                    "country": "Brazil",
                    "region": "Rio de Janeiro",
                    "city": "Rio de Janeiro",
                    "stream": "https://example.com/live",
                    "favicon": "",
                }
            ]
        )
        self.assertTrue(text.startswith("#EXTM3U\n"))
        self.assertIn("Brazil | Rio de Janeiro | Rio de Janeiro", text)
        self.assertNotIn("\n#EXTINF:-1,Injected", text)


if __name__ == "__main__":
    unittest.main()
