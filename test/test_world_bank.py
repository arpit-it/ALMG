import unittest
from unittest.mock import patch
from backend.world_bank import indicator_candidates
from backend import studio


class IndicatorCatalogTest(unittest.TestCase):
    def test_catalog_preserves_source_identity_and_constructs_review_urls(self):
        record = {"id": "NY.GDP.MKTP.CD", "name": "GDP", "source": {"id": "2", "value": "Development indicators"},
                  "sourceNote": "Economic output", "sourceOrganization": "Fixture organization"}
        rows = indicator_candidates([{"page": 1}, [record, record,
            {**record, "id": "../escape"}, {**record, "name": "Bad\nname"},
            {**record, "source": {"id": "other/2"}},
            {**record, "source": {"id": "11", "value": "Another source"}},
        ]])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "https://api.worldbank.org/v2/indicator/NY.GDP.MKTP.CD?source=2&format=json")
        self.assertEqual(rows[1]["source_id"], "11")
        self.assertEqual(rows[0]["reuse_status"], "unverified")

    def test_loading_contacts_only_the_approved_catalog_page(self):
        payload = [{"page": 1}, [{"id": str(index), "name": "Indicator", "source": {"id": "2"}} for index in range(25)]]
        job = {}
        with patch.object(studio, "request_json", return_value=payload) as request, patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.load_indicators(job)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "https://api.worldbank.org/v2/indicator?format=json&per_page=20&page=1")
        self.assertEqual(len(job["indicator_candidates"]), 20)
        self.assertEqual(job["status"], "indicator_candidates")

    def test_invalid_or_empty_catalog_returns_to_approval(self):
        for payload in ([{"page": 2}, []], [{"page": 1}, []], {"message": "error"}):
            job = {}
            with patch.object(studio, "request_json", return_value=payload), patch.object(studio, "store_job"):
                studio.load_indicators(job)
            self.assertEqual(job["status"], "approval")
            self.assertIn("World Bank", job["error"])

    def test_next_page_requires_matching_response_page_and_valid_total(self):
        for header in ({"page": 1, "pages": 2}, {"page": 2, "pages": 1}, {"page": True, "pages": 2}, {"page": 2, "pages": "3"}):
            with self.subTest(header=header), self.assertRaises(ValueError):
                indicator_candidates([header, []], expected_page=2)
        self.assertEqual(indicator_candidates([{"page": 2, "pages": 2}, []], expected_page=2), [])

    def test_next_page_loading_is_one_request_and_failed_refresh_retains_previous_page(self):
        record = {"source": "old"}
        job = {"indicator_candidates": [record], "indicator_page": 1, "indicator_pages": 2}
        with patch.object(studio, "request_json", side_effect=ValueError("unavailable")) as request, patch.object(studio, "store_job"):
            studio.load_indicators(job, 2)
        request.assert_called_once()
        self.assertIn("page=2", request.call_args.args[0])
        self.assertEqual(job["indicator_candidates"], [record])
        self.assertEqual(job["indicator_page"], 1)
        self.assertEqual(job["status"], "indicator_candidates")

    def test_reuse_evidence_is_scoped_to_metadata_and_source_context(self):
        from backend.world_bank import indicator_reuse_evidence, indicator_metadata_checksum
        record = indicator_candidates([{"page": 1}, [{"id": "NY.GDP.MKTP.CD", "name": "GDP",
            "source": {"id": "2", "value": "Development indicators"}, "sourceNote": "Economic output",
            "sourceOrganization": "Fixture organization"}]])[0]
        decision = {"approved_url": record["source"], "approved_scope": "catalog_description",
                    "confirmed": True, "permission_basis": "Local fixture metadata permission reviewed."}
        evidence = indicator_reuse_evidence(record, decision)
        self.assertEqual(evidence["scope"], "catalog_description")
        self.assertEqual(evidence["metadata_sha256"], indicator_metadata_checksum(record))
        self.assertNotEqual(evidence["metadata_sha256"], indicator_metadata_checksum({**record, "organization": "Other source"}))
        for changes in ({"confirmed": False}, {"approved_scope": "observations"}, {"approved_url": "other"}, {"permission_basis": "short"}):
            with self.assertRaises(ValueError):
                indicator_reuse_evidence(record, {**decision, **changes})
