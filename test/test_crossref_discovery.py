import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from backend.crossref_discovery import bibliographic_candidates
from backend import studio


def item(doi, title="Fixture publication"):
    return {"DOI": doi, "title": [title], "publisher": "Fixture publisher", "type": "journal-article"}


class BibliographicDiscoveryTest(unittest.TestCase):
    def test_doi_validation_safe_url_and_case_insensitive_deduplication(self):
        rows = bibliographic_candidates({"status": "ok", "message": {"items": [
            item("10.1234/Orchard"), item("10.1234/orchard"), item("10.1234/../escape"),
            item("https://evil.example/doi"), item("10.1234/bad", "bad\ud800"),
        ]}}, "orchard")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "https://doi.org/10.1234%2FOrchard")
        self.assertEqual(rows[0]["approved_query"], "orchard")
        self.assertEqual(rows[0]["reuse_status"], "unverified")

    def test_queries_request_only_bibliographic_fields_and_do_not_follow_dois(self):
        job = {"plan": {"queries": ["orchard", "astronomy"]}}
        def response(url, **kwargs):
            parts = urlsplit(url)
            self.assertEqual((parts.hostname, parts.path), ("api.crossref.org", "/works"))
            params = parse_qs(parts.query)
            self.assertEqual(params["select"], ["DOI,title,publisher,type"])
            self.assertEqual(params["rows"], ["20"])
            return {"status": "ok", "message": {"items": [item("10.1234/shared"), item("10.1234/" + params["query"][0])]}}
        with patch.object(studio, "request_json", side_effect=response) as request, patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_bibliography(job)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(job["status"], "bibliographic_candidates")
        self.assertEqual([row["approved_query"] for row in job["bibliographic_candidates"]], ["orchard", "orchard", "astronomy"])

    def test_total_limit_stops_contacts(self):
        job = {"plan": {"queries": ["one", "two", "unused"]}}
        responses = [{"status": "ok", "message": {"items": [item(f"10.1234/{batch}-{index}") for index in range(25)]}} for batch in range(2)]
        with patch.object(studio, "request_json", side_effect=responses) as request, patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_bibliography(job)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(job["bibliographic_candidates"]), 40)

    def test_empty_and_invalid_results_return_to_approval(self):
        for payload in ({"status": "ok", "message": {"items": []}}, {"status": "error"}):
            job = {"plan": {"queries": ["orchard"]}}
            with patch.object(studio, "request_json", return_value=payload), patch.object(studio, "store_job"):
                studio.search_bibliography(job)
            self.assertEqual(job["status"], "approval")
            self.assertIn("Crossref", job["error"])
