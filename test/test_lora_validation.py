import io
import json
import unittest
from unittest.mock import Mock, patch
from backend import lora_validation, studio


class LoraValidationTest(unittest.TestCase):
    def test_unsupported_host_has_clear_error_without_loading_mlx(self):
        with patch.object(lora_validation.platform, 'system', return_value='Windows'):
            with self.assertRaisesRegex(ValueError, 'Apple silicon'):
                lora_validation.run()

    def test_runtime_route_requires_explicit_confirmation_and_returns_evidence(self):
        for confirmed in (None, False, 1, True):
            body = json.dumps({'confirmed': confirmed}).encode()
            handler = Mock(path='/runtime/lora-fixture', headers={'Content-Length': str(len(body))}, rfile=io.BytesIO(body))
            evidence = {'passed': True, 'rank': 2, 'base_weights_unchanged': True, 'reload_max_error': 0.0}
            with patch.object(lora_validation, 'run', return_value=evidence) as run:
                studio.Handler.do_POST(handler)
            if confirmed is True:
                run.assert_called_once_with()
                self.assertEqual(handler.respond.call_args.args[0], evidence)
            else:
                run.assert_not_called()
                self.assertEqual(handler.respond.call_args.args[1], 400)
