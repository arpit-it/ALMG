"""Offline tests for the macOS runtime stop endpoint."""

import io
import signal
import unittest
from unittest.mock import Mock, call, patch

from backend import studio


class RuntimeStopTest(unittest.TestCase):
    def test_registered_backend_acknowledges_stop_before_terminating(self):
        handler = Mock(path="/backend/stop", headers={"Content-Length": "2"},
                       rfile=io.BytesIO(b"{}"))
        calls = Mock()
        calls.attach_mock(handler.respond, "respond")
        calls.attach_mock(handler.wfile.flush, "flush")
        with patch.object(studio.sys, "argv", ["studio.py", "--launchd"]):
            with patch.object(studio.os, "kill", calls.kill):
                studio.Handler.do_POST(handler)
        self.assertEqual(calls.mock_calls, [
            call.respond({"stopped": True}),
            call.flush(),
            call.kill(studio.os.getpid(), signal.SIGTERM),
        ])

    def test_manual_backend_cannot_be_stopped_from_settings(self):
        handler = Mock(path="/backend/stop", headers={"Content-Length": "2"},
                       rfile=io.BytesIO(b"{}"))
        with patch.object(studio.sys, "argv", ["studio.py"]):
            with patch.object(studio.os, "kill") as kill:
                studio.Handler.do_POST(handler)
        self.assertEqual(handler.respond.call_args.args[1], 409)
        kill.assert_not_called()
