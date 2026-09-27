import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from build_catalog import City, build_m3u, country_code, haversine_km, nearest_city, safe_web_url, slugify

class CatalogTests(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(slugify("São Paulo"), "sao-paulo")

    def test_haversine(self):
        d = haversine_km(-22.9068, -43.1729, -23.5505, -46.6333)
        self.assertGreater(d, 350)
        self.assertLess(d, 380)

    def test_nearest_city(self):
        rio = City("Rio de Janeiro", -22.9068, -43.1729, "BR", "21")
        buckets = {("BR", -23, -44): [rio]}
        city, distance = nearest_city(-22.91, -43.18, "BR", buckets, {"BR": [rio]}, 80)
        self.assertEqual(city.name, "Rio de Janeiro")
        self.assertLess(distance, 2)

    def test_country_code_rejects_path_traversal(self):
        self.assertEqual(country_code("../../pwned"), "ZZ")
        self.assertEqual(country_code("br"), "BR")

    def test_external_url_policy(self):
        self.assertTrue(safe_web_url("https://example.com/radio"))
        self.assertFalse(safe_web_url("javascript:alert(1)"))
        self.assertFalse(safe_web_url("https://user:pass@example.com/"))
        self.assertFalse(safe_web_url("http://example.com/"))
        self.assertTrue(safe_web_url("http://example.com/live", allow_http=True))

    def test_m3u(self):
        text = build_m3u([{"id":"x","name":"Test FM","country":"Brazil","region":"Rio de Janeiro","city":"Rio de Janeiro","stream":"https://example.com/live","favicon":""}])
        self.assertIn("#EXTM3U", text)
        self.assertIn("Brazil | Rio de Janeiro | Rio de Janeiro", text)

if __name__ == "__main__":
    unittest.main()
