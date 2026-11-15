"""Offline coverage for goal-based training workflow selection."""

import unittest
from unittest.mock import patch

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
