import unittest
from unittest.mock import patch
from backend.europe_pmc import publication_candidates
from backend import studio


class PublicationDiscoveryTest(unittest.TestCase):
    def test_supported_identifiers_titles_deduplication_and_unverified_reuse(self):
        good = {"source": "MED", "id": "12345", "title": "Orchard research"}
        records = publication_candidates({"resultList": {"result": [
            good, good, {**good, "source": "PMC", "id": "PMC67890"},
            {**good, "id": "../other"}, {**good, "source": "https://evil.example"},
            {**good, "title": "bad\ntitle"}, {**good, "id": "678", "title": "bad\ud800"},
        ]}}, "orchard")
        self.assertEqual([row["source"] for row in records], [
            "https://europepmc.org/article/MED/12345", "https://europepmc.org/article/PMC/PMC67890"])
        self.assertTrue(all(row["reuse_status"] == "unverified" for row in records))
        self.assertTrue(all(row["approved_query"] == "orchard" for row in records))

    def test_search_contacts_only_discovery_endpoint_and_limits_records(self):
        job = {"plan": {"queries": ["orchard fruit", "unused"]}}
        payload = {"resultList": {"result": [
            {"source": "MED", "id": str(index), "title": "Research"} for index in range(30)]}}
        with patch.object(studio, "request_json", return_value=payload) as request, \
             patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_publications(job)
        request.assert_called_once()
        url = request.call_args.args[0]
        self.assertTrue(url.startswith("https://www.ebi.ac.uk/europepmc/webservices/rest/search?"))
        self.assertIn("query=orchard+fruit", url)
        self.assertIn("resultType=lite", url)
        self.assertEqual(len(job["publication_candidates"]), 20)
        self.assertEqual(job["status"], "publication_candidates")

    def test_empty_or_malformed_response_returns_to_approval(self):
        for payload in ({"resultList": {"result": []}}, {"resultList": []}):
            job = {"plan": {"queries": ["orchard"]}}
            with patch.object(studio, "request_json", return_value=payload), patch.object(studio, "store_job"):
                studio.search_publications(job)
            self.assertEqual(job["status"], "approval")
            self.assertIn("Europe PMC", job["error"])

    def test_abstract_identity_text_and_request_scope(self):
        from backend.europe_pmc import abstract_request_url, publication_abstract
        source = "https://europepmc.org/article/MED/12345"
        url = abstract_request_url(source)
        self.assertIn("resultType=core", url)
        self.assertIn("pageSize=1", url)
        self.assertIn("EXT_ID%3A12345+AND+SRC%3AMED", url)
        payload = {"resultList": {"result": [{"source": "MED", "id": "12345", "abstractText": "<h4>Orchards</h4>Fruit &amp; trees."}]}}
        self.assertEqual(publication_abstract(payload, source), {
            "abstract": "Orchards Fruit & trees.", "abstract_reviewed": True, "reuse_status": "unverified"})
        payload["resultList"]["result"][0]["id"] = "54321"
        with self.assertRaisesRegex(ValueError, "does not match"):
            publication_abstract(payload, source)
        with self.assertRaises(ValueError):
            abstract_request_url(source + "/../other")

    def test_missing_and_invalid_abstracts(self):
        from backend.europe_pmc import publication_abstract
        source = "https://europepmc.org/article/MED/12345"
        record = {"source": "MED", "id": "12345"}
        payload = {"resultList": {"result": [record]}}
        self.assertEqual(publication_abstract(payload, source)["abstract"], "")
        for text in ([], "x" * 50001, "bad\ud800", "bad\x00"):
            with self.subTest(text_type=type(text)), self.assertRaises(ValueError):
                publication_abstract({"resultList": {"result": [{**record, "abstractText": text}]}}, source)

    def test_failed_abstract_refresh_removes_stale_text(self):
        record = {"source": "https://europepmc.org/article/MED/12345", "abstract": "Old abstract", "abstract_reviewed": True}
        job = {"publication_candidates": [record]}
        with patch.object(studio, "request_json", side_effect=ValueError("bad metadata")), patch.object(studio, "store_job"):
            studio.review_publication(job, record["source"])
        self.assertEqual(job["status"], "publication_candidates")
        self.assertNotIn("abstract", record)
        self.assertNotIn("abstract_reviewed", record)
