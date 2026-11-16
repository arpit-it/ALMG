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
