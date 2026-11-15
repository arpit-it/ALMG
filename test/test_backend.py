"""Offline regression tests for conversation storage and checkpoint setup."""

import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import chat_history
from backend.model_setup import ModelSetup, Paused


class ChatHistoryTest(unittest.TestCase):
    """Exercise chat and project persistence against a fresh SQLite database."""

    def setUp(self):
        """Redirect database operations to a disposable directory."""
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(chat_history, "DATABASE", Path(directory) / "chat.sqlite3"))

    def test_branch_preserves_attachment_without_modifying_source(self):
        """Verify that branch follow-ups still receive the original file content."""
        project = chat_history.create_project("Demo")["id"]
        attachment = {"name": "notes.txt", "data": base64.b64encode(b"Blue Finch").decode()}
        source = chat_history.send(None, "Read the file", lambda _: "Done",
                                   project_id=project, attachment=attachment)["id"]
        branch = chat_history.branch(source, 2)["id"]

        def reply(messages):
            """Check the file content passed to inference on the branch."""
            self.assertIn("Blue Finch", messages[-1]["content"])
            return "Blue Finch"

        chat_history.send(branch, "What did the file say?", reply)
        self.assertEqual(len(chat_history.messages(source)), 2)
        self.assertEqual(len(chat_history.messages(branch)), 4)
        self.assertEqual({chat["id"] for chat in chat_history.list_chats(project)}, {source, branch})

    def test_failed_generation_does_not_save_a_turn(self):
        """Keep the chat list empty if inference returns an empty reply."""
        with self.assertRaises(ValueError):
            chat_history.send(None, "Hello", lambda _: "")
        self.assertEqual(chat_history.list_chats(), [])

    def test_deleting_project_moves_chat_to_personal(self):
        """Preserve messages when the owning project is deleted."""
        project = chat_history.create_project("Demo")["id"]
        chat = chat_history.send(None, "Hello", lambda _: "Hi", project_id=project)["id"]
        chat_history.delete_project(project)
        self.assertEqual([entry["id"] for entry in chat_history.list_chats()], [chat])
        self.assertEqual(chat_history.messages(chat)[-1]["content"], "Hi")


class ModelSetupTest(unittest.TestCase):
    """Check model readiness and cancellation with tiny local fixtures."""

    def test_verified_file_edit_invalidates_readiness(self):
        """Detect a same-size change after checkpoint verification."""
        with tempfile.TemporaryDirectory() as directory:
            setup = ModelSetup("example/model", Path(directory))
            data = b"weights"
            file = Path(directory) / "model.safetensors"
            file.write_bytes(data)
            files = [[file.name, len(data), hashlib.sha256(data).hexdigest()]]
            setup.write(setup.manifest_path, {"revision": "test", "files": files})
            setup.write(setup.verified_path, {"revision": "test", "files": setup.fingerprints(files)})
            self.assertTrue(setup.status()["ready"])
            file.write_bytes(b"changed")
            self.assertFalse(setup.status()["ready"])

    def test_pause_check_interrupts_active_work(self):
        """Raise the cancellation signal at the next worker checkpoint."""
        with tempfile.TemporaryDirectory() as directory:
            setup = ModelSetup("example/model", Path(directory))
            setup.update(phase="downloading")
            setup.start("pause")
            self.assertEqual(setup.status()["phase"], "pausing")
            with self.assertRaises(Paused):
                setup.check_stop()
