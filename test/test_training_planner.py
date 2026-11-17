"""Offline coverage for goal-based training workflow selection."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import studio


class TrainingPlannerTest(unittest.TestCase):
    def test_goal_produces_image_plan_without_web_collection(self):
        job = {"prompt": "Generate small images of alpine lakes."}
        response = {
            "recipe": "text_to_image",
            "reason": "The output is an image.",
            "query": "alpine lakes landscape",
        }
        with patch.object(studio, "ask", return_value=response), \
             patch.object(studio, "store_job"), \
             patch.object(studio, "request_json") as network:
            studio.Handler.make_plan(job)
        self.assertEqual(job["status"], "approval")
        self.assertEqual(job["recipe"], "text_to_image")
        self.assertEqual(job["plan"]["queries"], ["alpine lakes landscape"])
        network.assert_not_called()

    def test_unclear_goal_waits_for_an_answer(self):
        job = {"prompt": "Build a model for my team."}
        response = {"recipe": None, "reason": "What should the model predict?"}
        with patch.object(studio, "ask", return_value=response), \
             patch.object(studio, "store_job"):
            studio.Handler.make_plan(job)
        self.assertEqual(job["status"], "clarification")
        self.assertEqual(job["planner_message"], response["reason"])
        self.assertNotIn("plan", job)

    def test_unknown_recipe_cannot_reach_dataset_approval(self):
        job = {"prompt": "Train an unavailable model."}
        with patch.object(studio, "ask", return_value={
            "recipe": "unknown", "reason": "Unsupported workflow",
        }), patch.object(studio, "store_job"), patch.object(studio, "request_json") as network:
            studio.Handler.make_plan(job)
        self.assertEqual(job["status"], "failed")
        self.assertNotIn("plan", job)
        network.assert_not_called()

    def test_classifier_uses_the_classification_dataset_planner(self):
        job = {"prompt": "Classify messages by support category."}
        proposal = {"labels": ["billing", "shipping"], "queries": ["billing", "shipping"]}
        with patch.object(studio, "ask", return_value={
            "recipe": "classifier", "reason": "The output is a label.",
        }), patch.object(studio, "store_job"), patch.object(studio, "plan", return_value=proposal):
            studio.Handler.make_plan(job)
        self.assertEqual(job["recipe"], "classifier")
        self.assertEqual(job["status"], "approval")
        self.assertEqual(job["plan"], proposal)

    def test_web_collection_rejects_empty_or_stale_approval(self):
        for proposed, approved in (([], []), (["updated query"], ["old query"])):
            with self.subTest(proposed=proposed, approved=approved):
                job = {"status": "approval", "recipe": "classifier",
                       "plan": {"queries": proposed}}
                body = json.dumps({"mode": "web", "approved_queries": approved}).encode()
                handler = Mock(path="/jobs/fixture/prepare",
                               headers={"Content-Length": str(len(body))},
                               rfile=io.BytesIO(body))
                with patch.object(studio, "JOBS", {"fixture": job}), \
                     patch.object(studio.threading, "Thread") as worker:
                    studio.Handler.do_POST(handler)
                handler.respond.assert_called_once_with(
                    {"error": "Approve the exact search queries first."}, 400
                )
                self.assertEqual(job["status"], "approval")
                worker.assert_not_called()

    def test_web_search_requires_explicit_provider_approval(self):
        for recipe, action, message in (
            ("classifier", "prepare", "Approve English Wikipedia before searching for text."),
            ("text_to_image", "search-images", "Approve Wikimedia Commons before searching for images."),
        ):
            with self.subTest(recipe=recipe):
                job = {"status": "approval", "recipe": recipe,
                       "plan": {"queries": ["fixture query"]}}
                body = json.dumps({"mode": "web", "approved_queries": ["fixture query"]}).encode()
                handler = Mock(path=f"/jobs/fixture/{action}",
                               headers={"Content-Length": str(len(body))},
                               rfile=io.BytesIO(body))
                with patch.object(studio, "JOBS", {"fixture": job}), patch.object(
                    studio.threading, "Thread"
                ) as worker:
                    studio.Handler.do_POST(handler)
                handler.respond.assert_called_once_with({"error": message}, 400)
                self.assertEqual(job["status"], "approval")
                worker.assert_not_called()

    def test_web_search_requires_explicit_result_limit(self):
        for recipe, action, provider in (
            ("classifier", "prepare", "wikipedia"),
            ("text_to_image", "search-images", "commons"),
        ):
            with self.subTest(recipe=recipe):
                job = {"id": "fixture", "status": "approval", "recipe": recipe,
                       "plan": {"queries": ["fixture query"]}}
                body = json.dumps({"mode": "web", "approved_queries": ["fixture query"],
                                   "approved_provider": provider}).encode()
                handler = Mock(path=f"/jobs/fixture/{action}",
                               headers={"Content-Length": str(len(body))},
                               rfile=io.BytesIO(body))
                with patch.object(studio, "JOBS", {"fixture": job}), patch.object(
                    studio, "store_job"
                ), patch.object(studio.threading, "Thread") as worker:
                    studio.Handler.do_POST(handler)
                self.assertEqual(job["status"], "approval")
                self.assertIn("Review the updated limit", job["error"])
                worker.assert_not_called()

    def test_undersized_classifier_approval_does_not_queue_training(self):
        job = {"id": "fixture", "status": "dataset_ready", "recipe": "classifier",
               "plan": {"labels": ["billing", "shipping"]},
               "usable_counts": {"billing": 1, "shipping": 8}}
        body = b'{"target": 0.8}'
        handler = Mock(path="/jobs/fixture/start",
                       headers={"Content-Length": str(len(body))},
                       rfile=io.BytesIO(body))
        rows = [{"label": "billing", "text": "invoice"}] + [
            {"label": "shipping", "text": f"delivery {i}"} for i in range(8)
        ]
        with patch.object(studio, "JOBS", {"fixture": job}), \
             patch.object(studio, "TRAINING_DATA", {"fixture": rows}), \
             patch.object(studio.threading, "Thread") as worker:
            studio.Handler.do_POST(handler)
        handler.respond.assert_called_once_with(
            {"error": "Training needs at least 8 usable examples per label after exclusions. "
                      "Add examples for billing (1)."}, 400
        )
        self.assertEqual(job["status"], "dataset_ready")
        worker.assert_not_called()

    def test_classifier_group_shortfall_does_not_queue_training(self):
        labels = ["billing", "shipping"]
        job = {"id": "fixture", "status": "dataset_ready", "recipe": "classifier",
               "plan": {"labels": labels}}
        rows = [{"label": label, "group": label, "text": f"{label} example {i}"}
                for label in labels for i in range(8)]
        body = b'{"target": 0.8}'
        handler = Mock(path="/jobs/fixture/start",
                       headers={"Content-Length": str(len(body))},
                       rfile=io.BytesIO(body))
        with patch.object(studio, "JOBS", {"fixture": job}), \
             patch.object(studio, "TRAINING_DATA", {"fixture": rows}), \
             patch.object(studio.threading, "Thread") as worker:
            studio.Handler.do_POST(handler)
        handler.respond.assert_called_once_with(
            {"error": "Training needs at least 5 independent groups for evaluation. "
                      "The usable examples form 2. Add examples from more independent groups."}, 400
        )
        self.assertEqual(job["status"], "dataset_ready")
        worker.assert_not_called()

    def test_classifier_label_group_shortfall_does_not_queue_training(self):
        labels = ["billing", "shipping"]
        job = {"id": "fixture", "status": "dataset_ready", "recipe": "classifier",
               "plan": {"labels": labels}}
        rows = [{"label": label, "group": label if label == "billing" else str(i), "text": f"{label} example {i}"}
                for label in labels for i in range(8)]
        body = b'{"target": 0.8}'
        handler = Mock(path="/jobs/fixture/start",
                       headers={"Content-Length": str(len(body))},
                       rfile=io.BytesIO(body))
        with patch.object(studio, "JOBS", {"fixture": job}), \
             patch.object(studio, "TRAINING_DATA", {"fixture": rows}), \
             patch.object(studio.threading, "Thread") as worker:
            studio.Handler.do_POST(handler)
        handler.respond.assert_called_once_with(
            {"error": "Each label needs at least 3 independent groups to appear in training, "
                      "validation, and test. Add groups for billing (1)."}, 400
        )
        self.assertEqual(job["status"], "dataset_ready")
        worker.assert_not_called()

    def test_invalid_csv_replacement_preserves_ready_dataset(self):
        job = {"status": "dataset_ready", "recipe": "classifier",
               "plan": {"labels": ["billing", "shipping"]}, "examples": 2}
        original_job = job.copy()
        body = json.dumps({"csv": "text,label\nInvoice,\n"}).encode()
        handler = Mock(path="/jobs/fixture/import-csv",
                       headers={"Content-Length": str(len(body))},
                       rfile=io.BytesIO(body))
        with patch.object(studio, "JOBS", {"fixture": job}), \
             patch.object(studio.threading, "Thread") as worker:
            studio.Handler.do_POST(handler)
        handler.respond.assert_called_once_with(
            {"error": "CSV line 2 is missing a label."}, 400
        )
        self.assertEqual(job, original_job)
        worker.assert_not_called()

    def test_classifier_matching_preserves_attached_vowel_marks(self):
        self.assertEqual(studio.classifier_variant_key("\u0301?!"), ())
        self.assertNotEqual(
            studio.classifier_variant_key("का"),
            studio.classifier_variant_key("क"),
        )

    def test_training_keeps_punctuation_variants_in_one_split(self):
        rows = [
            {"text": f"{phrase} case {case}{punctuation}", "label": label,
             "group": f"{label}-{case}-{punctuation}", "source": "local-csv"}
            for label, phrase in (("billing", "Refund invoice charge"),
                                  ("shipping", "Parcel courier delivery"))
            for case in range(12)
            for punctuation in ("?", "!")
        ]
        conflicting_texts = {"Tracking charge?", "Tracking charge!"}
        rows.extend([
            {"text": "Tracking charge?", "label": "billing", "group": "conflict-1"},
            {"text": "Tracking charge!", "label": "shipping", "group": "conflict-2"},
        ])

        _, evaluated, _ = studio.train(rows, ["billing", "shipping"], 0.8)

        assignments = {row["text"]: row["split"] for row in evaluated}
        self.assertTrue(conflicting_texts.isdisjoint(assignments))
        self.assertEqual(len(assignments), 48)
        self.assertEqual(set(assignments.values()), {"train", "validation", "test"})
        for prompt, split in assignments.items():
            if prompt.endswith("?"):
                self.assertEqual(split, assignments[prompt[:-1] + "!"])

    def test_restore_interrupted_classifier_requires_new_approval(self):
        job_id = "a" * 32
        rows = [{"text": "An invoice example", "label": "billing"}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "training-sessions" / job_id / "dataset.json"
            dataset.parent.mkdir(parents=True)
            dataset.write_text(json.dumps(rows), encoding="utf-8")
            with patch.object(studio, "ROOT", root), \
                 patch.object(studio, "JOBS", {}), \
                 patch.object(studio, "TRAINING_DATA", {}), \
                 patch.object(studio.threading, "Thread") as worker:
                studio.store_job({"id": job_id, "status": "training", "recipe": "classifier"})
                studio.restore_jobs()

                self.assertEqual(studio.JOBS[job_id]["status"], "dataset_ready")
                self.assertIn("saved dataset", studio.JOBS[job_id]["error"])
                self.assertEqual(studio.TRAINING_DATA[job_id], rows)
                worker.assert_not_called()


class WikipediaCollectionTest(unittest.TestCase):
    def test_search_excerpt_keeps_approved_query_and_article_url(self):
        query = "invoice & receipt"
        job = {"prompt": "Classify text", "plan": {"labels": ["billing"], "queries": [query]}}
        page = {"key": "Invoice / Receipt", "excerpt":
                "An <span>invoice</span> lists the goods and charges owed by a buyer."}
        malformed = {"key": "Invoice\nReceipt", "excerpt":
                     "This otherwise usable article has a control character in its key."}
        with patch.object(studio, "request_json", return_value={"pages": [malformed, page, page]}) as request, \
             patch.object(studio, "activity"), patch.object(studio.time, "sleep"), \
             patch.object(studio, "ask", return_value={"rows": [{"index": 0, "label": "billing"}]}):
            job["text_candidates"] = studio.discover_text(job)
            rows = studio.collect(job)
        self.assertEqual(len(job["text_candidates"]), 1)
        request.assert_called_once()
        endpoint = studio.urlsplit(request.call_args.args[0])
        self.assertEqual(endpoint.netloc, "en.wikipedia.org")
        self.assertEqual(studio.parse_qs(endpoint.query)["q"], [query])
        self.assertNotIn("X-Subscription-Token", request.call_args.kwargs["headers"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["approved_query"], query)
        self.assertEqual(rows[0]["source"], "https://en.wikipedia.org/wiki/Invoice%20%2F%20Receipt")
        self.assertEqual(rows[0]["label"], "billing")
        self.assertNotIn("<span>", rows[0]["text"])
