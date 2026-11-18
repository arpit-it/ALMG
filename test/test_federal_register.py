import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from backend.federal_register import document_candidates
from backend import studio


def document(number, title="Fixture document"):
    return {"document_number": number, "title": title,
            "html_url": f"https://www.federalregister.gov/documents/2026/11/18/{number}/fixture-document"}


class FederalRegisterDiscoveryTest(unittest.TestCase):
    def test_source_urls_match_supported_document_identity(self):
        good = document("2026-12345")
        rows = document_candidates({"results": [good, good,
            {**good, "html_url": good["html_url"].replace("www.federalregister.gov", "www.federalregister.gov.evil.example")},
            {**good, "html_url": good["html_url"].replace("2026-12345", "2026-54321")},
            {**good, "title": "Bad\ntext"}, {**good, "document_number": "../other"},
        ]}, "orchard")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], good["html_url"])
        self.assertEqual(rows[0]["reuse_status"], "unverified")

    def test_search_queries_request_metadata_only_and_deduplicate(self):
        job = {"plan": {"queries": ["orchard", "astronomy"]}}
        def response(url, **kwargs):
            parts = urlsplit(url)
            self.assertEqual((parts.hostname, parts.path), ("www.federalregister.gov", "/api/v1/documents.json"))
            params = parse_qs(parts.query)
            self.assertEqual(params["fields[]"], ["title", "document_number", "html_url"])
            self.assertEqual(params["per_page"], ["20"])
            return {"results": [document("2026-12345"),
                document("2026-12346" if params["conditions[term]"] == ["orchard"] else "2026-12347")]}
        with patch.object(studio, "request_json", side_effect=response) as request, patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_notices(job)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(job["status"], "notice_candidates")
        self.assertEqual([row["approved_query"] for row in job["notice_candidates"]], ["orchard", "orchard", "astronomy"])

    def test_total_limit_stops_additional_provider_contacts(self):
        job = {"plan": {"queries": ["one", "two", "unused"]}}
        responses = [{"results": [document(f"2026-{batch * 100 + index:05}") for index in range(25)]} for batch in range(2)]
        with patch.object(studio, "request_json", side_effect=responses) as request, patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_notices(job)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(job["notice_candidates"]), 40)

    def test_invalid_or_empty_results_return_to_approval(self):
        for payload in ({"results": []}, {"results": "bad"}):
            job = {"plan": {"queries": ["orchard"]}}
            with patch.object(studio, "request_json", return_value=payload), patch.object(studio, "store_job"):
                studio.search_notices(job)
            self.assertEqual(job["status"], "approval")
            self.assertIn("Federal Register", job["error"])
