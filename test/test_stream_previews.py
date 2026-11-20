import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_previews as previews, decoder_stream_training as training
import test_stream_training as training_tests


class StreamPreviewTests(unittest.TestCase):
    def test_consent_input_limits_and_incomplete_trials_reject_before_inference(self):
        with patch.object(previews.decoder_bundle,'load') as load:
            with self.assertRaises(ValueError):previews.preview('/unused','a'*32,False,'r','banana')
            for prompt,count in [('',12),('x'*4097,12),('banana',True),('banana',33)]:
                with self.assertRaises(ValueError):previews.preview('/unused','a'*32,True,'r',prompt,count)
            with patch.object(training,'read',return_value={'revision':'r','status':'paused','completed_steps':5}):
                with self.assertRaises(ValueError):previews.preview('/unused','a'*32,True,'r','banana')
            load.assert_not_called()

    def complete(self,root):
        windows=training_tests.StreamTrainingTests().setup_stream(root)
        run=training.begin(root,windows['id'],True,training.review(root,windows['id']))
        while run['status']!='complete':run=training.step(root,run['id'],True,run['revision'])
        return run

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires Metal to prepare a genuinely trained fixture')
    def test_exact_prompt_deterministic_restart_history_and_immutable_weights(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);run=self.complete(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            first=previews.preview(root,run['id'],True,run['revision'],' café ',4)
            self.assertEqual(first['prompt'],' café ');self.assertEqual(len(first['generated_token_ids']),4)
            self.assertEqual(first['optimizer_updates'],0);self.assertFalse(first['release_approved'])
            importlib.reload(previews)
            self.assertEqual(previews.list_previews(root,run['id'],True,run['revision']),[first])
            second=previews.preview(root,run['id'],True,run['revision'],' café ',4)
            self.assertEqual(first['generated_token_ids'],second['generated_token_ids']);self.assertEqual(first['text'],second['text'])
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            path=previews._folder(root,run['id'])/(first['id']+'.json')
            altered=json.loads(path.read_text());altered['completion']='changed';path.write_text(json.dumps(altered))
            self.assertEqual(previews.list_previews(root,run['id'],True,run['revision']),[second])
            with self.assertRaises(ValueError):previews.preview(root,run['id'],True,'stale','banana',4)
            with self.assertRaises(ValueError):previews.list_previews(root,run['id'],False,run['revision'])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires Metal to prepare a genuinely trained fixture')
    def test_unsupported_long_prompts_and_source_change_publish_nothing(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);run=self.complete(root)
            for prompt in ('unique '*100,'Ω'):
                with self.assertRaises(ValueError):previews.preview(root,run['id'],True,run['revision'],prompt,4)
            with patch.object(previews,'_validated',side_effect=[run,ValueError('source changed')]):
                with self.assertRaises(ValueError):previews.preview(root,run['id'],True,run['revision'],'café',4)
            self.assertFalse(previews._folder(root,run['id']).exists())
