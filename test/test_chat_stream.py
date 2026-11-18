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

                retry = Mock(wfile=io.BytesIO())
                with patch.object(studio.inference, "reply", return_value="Recovered"):
                    studio.Handler.stream_chat(retry, prompt)

                retry_events = [
                    json.loads(line) for line in retry.wfile.getvalue().splitlines()
                ]
                chat_id = retry_events[-1]["done"]["id"]
                self.assertEqual(len(chat_history.list_chats()), 1)
                self.assertEqual(
                    [message["content"] for message in chat_history.messages(chat_id)],
                    ["Summarize the fixture", "Recovered"],
                )

    def test_persisted_retry_token_recovers_lost_commit_ack_without_duplicate_turn(self):
        class LostAcknowledgement(io.BytesIO):
            def write(self, value):
                if b'"done"' in value:
                    raise BrokenPipeError('Fixture lost completion event')
                return super().write(value)
        payload = {'text': 'Durable retry fixture', 'token': 'abcdef12' * 4}
        with tempfile.TemporaryDirectory() as folder, patch.object(chat_history, 'DATABASE', Path(folder) / 'chat.sqlite3'):
            writer = LostAcknowledgement()
            handler = Mock(wfile=writer)
            def generate(messages, **kwargs):
                kwargs['on_delta']('Partial fixture response')
                return 'Complete fixture response'
            with patch.object(studio.inference, 'reply', side_effect=generate):
                studio.Handler.stream_chat(handler, payload)
            self.assertIn(b'Partial fixture response', writer.getvalue())
            saved_recovery = Path(folder) / 'recovery.json'
            saved_recovery.write_text(json.dumps({'token': payload['token'], 'payload': json.dumps({'text': payload['text']})}))
            restored = json.loads(saved_recovery.read_text())
            retry_payload = {**json.loads(restored['payload']), 'token': restored['token']}
            retry = Mock(wfile=io.BytesIO())
            with patch.object(studio.inference, 'reply') as model:
                studio.Handler.stream_chat(retry, retry_payload)
                model.assert_not_called()
            chats = chat_history.list_chats()
            self.assertEqual(len(chats), 1)
            self.assertEqual([message['content'] for message in chat_history.messages(chats[0]['id'])],
                             ['Durable retry fixture', 'Complete fixture response'])
