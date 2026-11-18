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

    def test_search_and_recall_respect_project_scope(self):
        project = chat_history.create_project("Work")["id"]
        source = chat_history.send(None, "Garden orchid notes", lambda _: "Blue Finch", project_id=project)["id"]
        self.assertEqual([chat["id"] for chat in chat_history.list_chats(project, "BLUE FINCH")], [source])
        self.assertEqual(chat_history.list_chats(None, "Blue Finch"), [])

        def reply(messages):
            self.assertTrue(all(message["role"] != "system" for message in messages))
            return "No recalled context"

        chat_history.send(None, "Garden orchid question", reply, project_id=project, recall=False)

    def test_recall_switch_only_controls_related_chats_in_current_project(self):
        project = chat_history.create_project("Work")["id"]
        other = chat_history.create_project("Other")["id"]
        chat_history.send(None, "Violet lantern SAME_PROJECT_CONTEXT", lambda _: "Source reply", project_id=project)
        chat_history.send(None, "Violet lantern OTHER_PROJECT_CONTEXT", lambda _: "Private reply", project_id=other)
        observed = []
        def reply(messages):
            observed.append(messages)
            return "Current reply"
        current = chat_history.send(None, "Violet lantern location", reply, project_id=project, recall=True)["id"]
        enabled = str(observed[-1])
        self.assertIn("SAME_PROJECT_CONTEXT", enabled)
        self.assertNotIn("OTHER_PROJECT_CONTEXT", enabled)
        chat_history.send(current, "Violet lantern followup", reply, project_id=project, recall=False)
        disabled = str(observed[-1])
        self.assertNotIn("SAME_PROJECT_CONTEXT", disabled)
        self.assertNotIn("OTHER_PROJECT_CONTEXT", disabled)
        self.assertIn("Current reply", disabled)
        self.assertIn("Violet lantern location", disabled)

    def test_retried_message_returns_committed_turn_once(self):
        token = "a" * 32
        first = chat_history.send(None, "Hello", lambda _: "Hi", token=token)
        second = chat_history.send(None, "Hello", lambda _: self.fail("Generated twice"), token=token)
        self.assertEqual(first, second)
        self.assertEqual(len(chat_history.messages(first["id"])), 2)

    def test_pdf_excerpt_survives_branch(self):
        project = chat_history.create_project("Work")["id"]
        chat_history.update_project(project, "Cite sources.")
        chat_history.add_project_file(project, "manual.txt", "Orchid care instructions")
        attachment = {"name": "guide.pdf", "data": "/w==", "extracted": "Page 2\nWater weekly"}
        source = chat_history.send(None, "Read this", lambda _: "Done", attachment=attachment, project_id=project)["id"]
        branch = chat_history.branch(source, 2)["id"]

        def reply(messages):
            self.assertIn("Page 2", messages[-1]["content"])
            self.assertIn("Cite sources.", messages[0]["content"])
            self.assertIn("Orchid care instructions", messages[0]["content"])
            return "Water weekly"

        chat_history.send(branch, "Orchid care instructions", reply)
        self.assertEqual(len(chat_history.messages(source)), 2)

    def test_branch_keeps_project_instructions_references_and_original_unchanged(self):
        project = chat_history.create_project("Branch fixture project")["id"]
        other = chat_history.create_project("Other project")["id"]
        chat_history.update_project(project, "Use ORCHARD_APPROVED and cite project references.")
        chat_history.add_project_file(project, "orchard-notes.txt", "Pear trees need water on Tuesday.")
        chat_history.add_project_file(other, "private.txt", "OTHER_PROJECT_NOLEAK")
        attachment = {"name": "guide.pdf", "data": "/w==", "extracted": "Page 2\nPear trees grow in orchards."}
        source = chat_history.send(None, "Pear watering question", lambda _: "Original answer", project_id=project, attachment=attachment)["id"]
        before = chat_history.messages(source)
        branch = chat_history.branch(source, 2)
        self.assertEqual(branch['project_id'], project)
        self.assertEqual(branch['project_name'], 'Branch fixture project')
        self.assertEqual(branch['source_id'], source)
        self.assertEqual(branch['message_count'], 2)
        def generate(messages):
            text = str(messages)
            self.assertIn('ORCHARD_APPROVED', text)
            self.assertIn('orchard-notes.txt', text)
            self.assertIn('Tuesday', text)
            self.assertIn('Page 2', text)
            self.assertIn('guide.pdf', text)
            self.assertNotIn('OTHER_PROJECT_NOLEAK', text)
            return 'ORCHARD_APPROVED: Tuesday (orchard-notes.txt).'
        chat_history.send(branch['id'], 'When should pear trees receive water?', generate, project_id=project, recall=False)
        self.assertEqual(chat_history.messages(source), before)
        self.assertEqual(len(chat_history.messages(branch['id'])), 4)
        self.assertEqual({chat['id'] for chat in chat_history.list_chats(project)}, {source, branch['id']})

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

    def test_resume_after_restart_verifies_partial_checkpoint(self):
        """Resume a partial checkpoint from disk and verify the completed file."""
        import httpx2 as httpx

        with tempfile.TemporaryDirectory() as directory:
            setup = ModelSetup("example/model", Path(directory))
            name = "model.safetensors"
            data = b"weights"
            digest = hashlib.sha256(data).hexdigest()
            manifest = {"revision": "test", "files": [[name, len(data), digest]]}
            setup.write(setup.manifest_path, manifest)
            setup.partial(name, digest).write_bytes(data[:3])

            restarted = ModelSetup("example/model", Path(directory))
            self.assertEqual(restarted.status()["phase"], "paused")
            self.assertEqual(restarted.status()["downloaded_bytes"], 3)

            def serve_range(request):
                self.assertEqual(request.headers["Range"], "bytes=3-")
                return httpx.Response(
                    206, headers={"Content-Range": "bytes 3-6/7"}, content=data[3:]
                )

            with httpx.Client(transport=httpx.MockTransport(serve_range)) as client:
                with patch("huggingface_hub.utils.get_session", return_value=client):
                    with patch.object(restarted, "manifest", return_value=manifest):
                        restarted.run("resume")

            self.assertEqual(restarted.status()["phase"], "ready", restarted.status())
            self.assertEqual((Path(directory) / name).read_bytes(), data)
            self.assertFalse(restarted.partial(name, digest).exists())
