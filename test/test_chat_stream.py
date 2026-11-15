"""Offline regression coverage for interrupted streaming replies."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend import chat_history, studio


class ChatStreamTest(unittest.TestCase):
    def test_partial_reply_reports_failure_without_committing_turn(self):
        handler = Mock(wfile=io.BytesIO())
        prompt = {"text": "Summarize the fixture", "token": "12345678123456781234567812345678"}

        def interrupted_reply(messages, *, max_tokens, on_delta, stop):
            on_delta("Partial reply")
            raise RuntimeError("Generation interrupted")

        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "chat.sqlite3"
            with patch.object(chat_history, "DATABASE", database):
                with patch.object(studio.inference, "reply", interrupted_reply):
                    studio.Handler.stream_chat(handler, prompt)

                events = [json.loads(line) for line in handler.wfile.getvalue().splitlines()]
                self.assertEqual(events[1:], [
                    {"delta": "Partial reply"},
                    {"error": "Generation interrupted"},
                ])
                self.assertNotIn(events[0]["request_id"], studio.CHAT_STREAMS)
                self.assertEqual(chat_history.list_chats(), [])
