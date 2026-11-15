"""Offline tests for the macOS runtime lifecycle."""

import ctypes
import io
import signal
import socket
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


class RuntimeActivationTest(unittest.TestCase):
    def test_restarted_backend_accepts_queued_local_connection(self):
        """A connection queued on launchd's socket reaches the replacement server."""
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            with socket.create_connection(listener.getsockname(), timeout=2) as client:
                descriptors = (ctypes.c_int * 1)()

                def activate(name, result, count):
                    self.assertEqual(name, b"Backend")
                    descriptors[0] = listener.dup().detach()
                    ctypes.cast(result, ctypes.POINTER(ctypes.POINTER(ctypes.c_int)))[0] = (
                        ctypes.cast(descriptors, ctypes.POINTER(ctypes.c_int))
                    )
                    ctypes.cast(count, ctypes.POINTER(ctypes.c_size_t))[0] = 1
                    return 0

                library = Mock()
                library.launch_activate_socket.side_effect = activate
                with patch.object(studio.sys, "argv", ["studio.py", "--launchd"]):
                    with patch.object(studio.ctypes, "CDLL", return_value=library):
                        server = studio.backend_server()
                with server:
                    server.socket.settimeout(2)
                    accepted, address = server.get_request()
                    with accepted:
                        self.assertEqual(address, client.getsockname())
                        self.assertEqual(server.server_address, listener.getsockname())
