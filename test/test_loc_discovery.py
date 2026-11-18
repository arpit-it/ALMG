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

    def test_item_advisories_preserve_rights_without_granting_reuse(self):
        from backend.loc_discovery import item_advisories
        self.assertEqual(item_advisories({"item": {
            "rights_advisory": ["Permission required."],
            "rights": ["Contact the rights holder."],
        }}), {
            "advisories": {
                "rights_advisory": ["Permission required."],
                "rights": ["Contact the rights holder."],
            },
            "reuse_status": "unverified",
            "description": "",
        })
        with self.assertRaises(ValueError):
            item_advisories({"item": {"rights": "unreadable"}})

    def test_failed_refresh_clears_previous_advisory_review(self):
        from unittest.mock import patch
        from backend import studio

        source = "https://www.loc.gov/item/12345/"
        record = {"source": source, "metadata_reviewed": True,
                  "advisories": {"rights": ["Earlier statement"]},
                  "reuse_approval": {"permission_basis": "Earlier permission"}}
        job = {"status": "reviewing_catalog_item", "catalog_candidates": [record]}
        with patch.object(studio, "request_json", side_effect=ValueError("invalid metadata")), \
             patch.object(studio, "store_job"):
            studio.review_catalog_item(job, source)
        self.assertEqual(job["status"], "catalog_candidates")
        self.assertNotIn("metadata_reviewed", record)
        self.assertNotIn("reuse_approval", record)
        self.assertNotIn("advisories", record)
        self.assertEqual(record["reuse_status"], "unverified")

    def test_interrupted_item_review_restores_catalog_without_network(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from backend import studio

        job_id = "a" * 32
        job = {"id": job_id, "status": "reviewing_catalog_item",
               "catalog_candidates": [{"source": "https://www.loc.gov/item/12345/",
                                       "metadata_reviewed": True, "advisories": {"rights": ["Old"]}}]}
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "training-sessions").mkdir()
            (root / "training-sessions" / (job_id + ".json")).write_text(json.dumps(job))
            with patch.object(studio, "ROOT", root), patch.object(studio, "JOBS", {}), \
                 patch.object(studio, "request_json") as request:
                studio.restore_jobs()
                restored = studio.JOBS[job_id]
                self.assertEqual(restored["status"], "catalog_candidates")
                self.assertNotIn("advisories", restored["catalog_candidates"][0])
                request.assert_not_called()

    def test_description_labeling_preserves_permission_and_provenance(self):
        from unittest.mock import patch
        from backend import studio
        row = {"source": "https://www.loc.gov/item/12345/", "provider": "loc",
               "text": "An orchard description approved for use in a local test dataset.",
               "reuse_approval": {"permission_basis": "Local fixture permission"},
               "approved_query": "orchard"}
        job = {"text_candidates": [row], "plan": {"labels": ["fruit"]}, "prompt": "Classify text"}
        with patch.object(studio, "activity"), patch.object(studio, "ask", return_value={
            "rows": [{"index": 0, "label": "fruit"}],
        }):
            self.assertEqual(studio.collect(job), [{**row, "label": "fruit"}])


    def test_newspaper_issue_paths_keep_segments_and_reject_traversal(self):
        base = {"title": "Orchard Gazette", "access-restricted": False}
        payload = {"results": [
            {**base, "id": "http://www.loc.gov/item/sn85033000/1911-08-10/ed-1/"},
            {**base, "id": "https://www.loc.gov/item/sn85033000/../outside/"},
            {**base, "id": "https://www.loc.gov/item/sn85033000/%2e%2e/outside/"},
        ]}
        records = catalog_candidates(payload, "orchard", limit=20)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source"],
                         "https://www.loc.gov/item/sn85033000/1911-08-10/ed-1/")

    def test_dataset_preview_retains_catalog_permission_evidence(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest.mock import patch
        from backend import studio

        permission = {"permission_basis": "Local fixture permission granted.",
                      "source": "https://www.loc.gov/item/12345/",
                      "advisories": {"rights": ["Permission required."]}}
        row = {"text": "Orchard fruit grows on cultivated trees.", "label": "fruit",
               "provider": "loc", "title": "Orchard archive", "reuse_approval": permission}
        job = {"id": "preview-fixture", "recipe": "classifier", "plan": {"labels": ["fruit"]}}
        with TemporaryDirectory() as directory, patch.object(studio, "ROOT", Path(directory)), \
             patch.object(studio, "TRAINING_DATA", {}), patch.object(studio, "store_job"):
            studio.prepare_dataset(job, imported_rows=[row])
        self.assertEqual(job["status"], "dataset_ready")
        self.assertEqual(job["preview"][0]["reuse_approval"], permission)
        self.assertEqual(job["preview"][0]["title"], "Orchard archive")

    def test_catalog_queries_deduplicate_sources_and_retain_query(self):
        from unittest.mock import patch
        from urllib.parse import parse_qs, urlsplit
        from backend import studio

        queries = ["orchard", "astronomy"]
        job = {"plan": {"queries": queries}}
        def response(url, **kwargs):
            query = parse_qs(urlsplit(url).query)["q"][0]
            return {"results": [
                {"id": "https://www.loc.gov/item/shared/", "title": "Shared", "access-restricted": False},
                {"id": f"https://www.loc.gov/item/{query}/", "title": query, "access-restricted": False},
            ]}
        with patch.object(studio, "request_json", side_effect=response) as request, \
             patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_catalog(job)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(job["status"], "catalog_candidates")
        self.assertEqual([row["approved_query"] for row in job["catalog_candidates"]],
                         ["orchard", "orchard", "astronomy"])

    def test_catalog_stops_before_contacting_queries_beyond_total_limit(self):
        from unittest.mock import patch
        from backend import studio

        job = {"plan": {"queries": ["orchard", "astronomy", "unused"]}}
        responses = [{"results": [
            {"id": f"https://www.loc.gov/item/{batch}-{index}/", "title": "Archive", "access-restricted": False}
            for index in range(25)
        ]} for batch in range(2)]
        with patch.object(studio, "request_json", side_effect=responses) as request, \
             patch.object(studio, "activity"), patch.object(studio, "store_job"):
            studio.search_catalog(job)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(len(job["catalog_candidates"]), 40)

    def test_item_metadata_identity_matches_approved_url(self):
        from backend.loc_discovery import item_advisories
        source = "https://www.loc.gov/item/sn85033000/1911-08-10/ed-1/"
        item = {"id": source.replace("https:", "http:"), "rights": ["Fixture rights"]}
        self.assertEqual(item_advisories({"item": item}, expected_source=source)["advisories"],
                         {"rights": ["Fixture rights"]})
        for identity in (None, "https://www.loc.gov/item/other/", source + "?redirect=1",
                         "https://www.loc.gov.evil.example/item/sn85033000/1911-08-10/ed-1/"):
            with self.subTest(identity=identity), self.assertRaisesRegex(ValueError, "does not match"):
                item_advisories({"item": {**item, "id": identity}}, expected_source=source)

    def test_wrong_item_identity_clears_previous_permission(self):
        from unittest.mock import patch
        from backend import studio
        record = {"source": "https://www.loc.gov/item/12345/", "metadata_reviewed": True,
                  "reuse_approval": {"permission_basis": "Old permission"}, "advisories": {"rights": ["Old"]}}
        job = {"catalog_candidates": [record]}
        with patch.object(studio, "request_json", return_value={"item": {
            "id": "https://www.loc.gov/item/other/", "rights": ["Wrong item rights"],
        }}), patch.object(studio, "store_job"):
            studio.review_catalog_item(job, record["source"])
        self.assertEqual(job["status"], "catalog_candidates")
        self.assertNotIn("reuse_approval", record)
        self.assertNotIn("advisories", record)
        self.assertNotIn("metadata_reviewed", record)
