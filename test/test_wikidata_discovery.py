import unittest
from unittest.mock import patch
from backend.wikidata_discovery import entity_candidates
from backend import studio


class EntityDiscoveryTest(unittest.TestCase):
    def test_only_supported_items_and_clean_text_enter_source_review(self):
        good = {"id": "Q42", "label": "Orchard", "description": "Cultivated fruit trees", "url": "https://evil.example/"}
        rows = entity_candidates({"search": [good, good,
            {**good, "id": "P42"}, {**good, "id": "Q42/../other"},
            {**good, "id": "Q43", "label": "Bad\nlabel"},
            {**good, "id": "Q44", "description": "bad\ud800"},
        ]}, "orchard")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "https://www.wikidata.org/wiki/Q42")
        self.assertEqual(rows[0]["approved_query"], "orchard")
        self.assertEqual(rows[0]["reuse_status"], "unverified")

    def test_query_list_uses_only_search_endpoint_and_deduplicates_entities(self):
        from urllib.parse import parse_qs, urlsplit
        job = {"plan": {"queries": ["orchard", "astronomy"]}}
        def response(url, **kwargs):
            parts = urlsplit(url)
            self.assertEqual((parts.hostname, parts.path), ("www.wikidata.org", "/w/api.php"))
            params = parse_qs(parts.query)
            self.assertEqual(params["action"], ["wbsearchentities"])
            self.assertEqual(params["language"], ["en"])
            self.assertEqual(params["maxlag"], ["5"])
            return {"search": [{"id": "Q42", "label": "Shared"},
                {"id": "Q43" if params["search"] == ["orchard"] else "Q44", "label": "Topic"}]}
        with patch.object(studio, "request_json", side_effect=response) as request, patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_entities(job)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(job["status"], "entity_candidates")
        self.assertEqual([row["approved_query"] for row in job["entity_candidates"]], ["orchard", "orchard", "astronomy"])

    def test_error_and_empty_responses_return_to_approval(self):
        for payload in ({"search": []}, {"error": {"code": "maxlag"}}, {"search": "bad"}):
            job = {"plan": {"queries": ["orchard"]}}
            with patch.object(studio, "request_json", return_value=payload), patch.object(studio, "store_job"):
                studio.search_entities(job)
            self.assertEqual(job["status"], "approval")
            self.assertIn("Wikidata", job["error"])

    def test_entity_limit_stops_further_contacts(self):
        job = {"plan": {"queries": ["one", "two", "unused"]}}
        responses = [{"search": [{"id": f"Q{batch * 100 + index + 1}", "label": "Entity"} for index in range(25)]} for batch in range(2)]
        with patch.object(studio, "request_json", side_effect=responses) as request, patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_entities(job)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(job["entity_candidates"]), 40)

    def test_reuse_permission_is_explicit_and_tied_to_reviewed_entity_text(self):
        import hashlib
        from backend.wikidata_discovery import entity_reuse_evidence
        record = {"entity_id": "Q42", "title": "Orchard", "description": "Cultivated fruit trees",
                  "source": "https://www.wikidata.org/wiki/Q42"}
        decision = {"approved_url": record["source"], "confirmed": True, "permission_basis": "CC0 fixture metadata reviewed."}
        evidence = entity_reuse_evidence(record, decision)
        self.assertEqual(evidence["entity_text_sha256"], hashlib.sha256(b"Orchard\nCultivated fruit trees").hexdigest())
        self.assertEqual(evidence["terms_source"], "https://www.wikidata.org/wiki/Wikidata:Copyright")
        for changes in ({"confirmed": False}, {"approved_url": "other"}, {"permission_basis": "short"}):
            with self.assertRaises(ValueError):
                entity_reuse_evidence(record, {**decision, **changes})
        with self.assertRaises(ValueError):
            entity_reuse_evidence({**record, "source": "https://evil.example/Q42"}, decision)

    def test_collection_checks_selection_and_permission_text_checksum(self):
        from backend.wikidata_discovery import entity_reuse_evidence, approved_entity_rows
        record = {"entity_id": "Q42", "title": "Orchard", "description": "Cultivated fruit trees grown for seasonal harvests.",
                  "source": "https://www.wikidata.org/wiki/Q42", "reuse_status": "user_approved"}
        record["reuse_approval"] = entity_reuse_evidence(record, {
            "approved_url": record["source"], "confirmed": True, "permission_basis": "Local fixture permission reviewed.",
        })
        row = approved_entity_rows([record], [record["source"]])[0]
        self.assertEqual(row["text"], record["title"] + "\n" + record["description"])
        self.assertEqual(row["reuse_approval"], record["reuse_approval"])
        self.assertEqual(row["provider"], "wikidata")
        for urls in ([], ["other"], [record["source"], record["source"]]):
            with self.assertRaises(ValueError):
                approved_entity_rows([record], urls)
        for changes in ({"description": "Changed description that is long enough for classifier collection."}, {"reuse_status": "unverified"}, {"reuse_approval": {}}):
            with self.assertRaises(ValueError):
                approved_entity_rows([{**record, **changes}], [record["source"]])
