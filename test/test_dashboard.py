"""Regression coverage for Dashboard data persistence and project context."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import chat_history, studio


class DashboardTest(unittest.TestCase):
    def setUp(self):
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(
            patch.object(chat_history, "DATABASE", self.directory / "chat.sqlite3")
        )

    def test_project_folder_persists_and_invalid_folder_is_rejected(self):
        project = chat_history.create_project("  Lake models  ", str(self.directory))
        self.assertEqual(chat_history.list_projects()[0]["directory"], str(self.directory))
        self.assertEqual(project["name"], "Lake models")
        with self.assertRaisesRegex(ValueError, "existing local folder"):
            chat_history.create_project("Invalid", str(self.directory / "missing"))
        self.assertEqual(len(chat_history.list_projects()), 1)

    def test_dashboard_returns_latest_model_and_exact_chat_context(self):
        project = chat_history.create_project("Lake models")
        saved = chat_history.send(None, "A lake question", lambda _: "Answer",
                                  project_id=project["id"])
        jobs = {
            "new": {"project_id": project["id"], "prompt": "Latest model",
                    "status": "preview_ready", "activity": [{"timestamp": 20}]},
            "old": {"project_id": project["id"], "prompt": "Older model",
                    "status": "passed", "activity": [{"timestamp": 10}]},
        }
        handler = Mock(path="/dashboard")
        with patch.object(studio, "JOBS", jobs):
            studio.Handler.do_GET(handler)
        data = handler.respond.call_args.args[0]
        self.assertEqual(data["projects"][0]["model"],
                         {"name": "Latest model", "status": "preview_ready"})
        chat = data["chats"][0]
        self.assertEqual((chat["id"], chat["project_id"], chat["project_name"]),
                         (saved["id"], project["id"], "Lake models"))
