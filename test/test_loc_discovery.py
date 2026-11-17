import unittest

from backend.loc_discovery import catalog_candidates


class CatalogCandidatesTest(unittest.TestCase):
    def test_only_unrestricted_catalog_links_enter_review(self):
        valid = {
            "id": "https://www.loc.gov/item/12345/",
            "title": "Orchard records",
            "access-restricted": False,
        }
        results = [
            {**valid, "id": "http://www.loc.gov/item/12345/"},
            {**valid, "id": "https://www.loc.gov/item/12345"},
            {**valid, "id": "https://www.loc.gov/item/restricted/", "access-restricted": True},
            {**valid, "id": "https://www.loc.gov.evil.example/item/external/"},
            {"id": "https://www.loc.gov/item/missing/", "title": "Unknown access"},
        ]
        self.assertEqual(catalog_candidates({"results": results}, "orchard", limit=20), [{
            "source": valid["id"],
            "title": valid["title"],
            "provider": "loc",
            "approved_query": "orchard",
            "reuse_status": "unverified",
        }])

    def test_rejects_missing_results(self):
        with self.assertRaisesRegex(ValueError, "invalid search response"):
            catalog_candidates({"results": None}, "orchard", limit=20)

    def test_empty_search_returns_to_approval(self):
        from unittest.mock import patch
        from backend import studio

        job = {"status": "searching_catalog", "plan": {"queries": ["orchard"]}}
        with patch.object(studio, "request_json", return_value={"results": []}), \
             patch.object(studio, "store_job"):
            studio.search_catalog(job)
        self.assertEqual(job["status"], "approval")
        self.assertIn("No Library of Congress records", job["error"])
        self.assertNotIn("catalog_candidates", job)

    def test_rate_limit_does_not_retry_without_approval(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        from backend import studio

        job = {"status": "searching_catalog", "plan": {"queries": ["orchard"]}}
        rate_limit = HTTPError("https://www.loc.gov/search/", 429, "Too Many Requests", {}, None)
        with patch.object(studio, "request_json", side_effect=rate_limit) as request, \
             patch.object(studio, "store_job"):
            studio.search_catalog(job)
        request.assert_called_once()
        self.assertEqual(job["status"], "approval")
        self.assertIn("Try again later", job["error"])
