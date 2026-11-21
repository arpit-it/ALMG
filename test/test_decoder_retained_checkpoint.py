import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import numpy as np
from backend import decoder_optimizer_fixture as fixture
from test_decoder_optimizer_state import state
from test_planned_decoder_compact import larger


class RetainedCheckpointTest(unittest.TestCase):
    def test_legacy_and_compact_bytes_preserved_under_new_review(self):
        c={**fixture.DEFAULT,'optimizer':'adamw'}
        for legacy in (False,True):
            with self.subTest(legacy=legacy), TemporaryDirectory() as temporary:
                root=Path(temporary);model=larger();original=state(model.parameters)
                source=root/'source';record=fixture.checkpoint(source,model,original,c,'old-review')
                if legacy:
                    (source/'model.json').write_text(json.dumps({'format':'almg-planned-decoder-v1','schema_version':1,'config':model.config,'parameters':{n:v.tolist() for n,v in model.parameters.items()}}))
                    (source/'optimizer.json').write_text(json.dumps(fixture.optimizer_state.encode(original,model.parameters,c,compact=False)))
                    record.update(format='almg-optimizer-fixture-checkpoint-v1',schema_version=1,files={n:fixture.file_digest(source/n) for n in ('model.json','optimizer.json')})
                    record['revision']=fixture.digest({k:v for k,v in record.items() if k!='revision'});(source/'checkpoint.json').write_text(json.dumps(record))
                before={p.name:p.read_bytes() for p in source.iterdir()}
                copied=fixture.copy_checkpoint(source,root/'copy',c,'old-review','new-review')
                self.assertEqual(copied['schema_version'],record['schema_version']);self.assertEqual(copied['review_revision'],'new-review')
                for name in ('model.json','optimizer.json'):self.assertEqual((root/'copy'/name).read_bytes(),before[name])
                restored,loaded=fixture.restore(root/'copy',c,'new-review')
                self.assertTrue(all(np.array_equal(value.view(np.uint32),restored.parameters[name].view(np.uint32)) for name,value in model.parameters.items()))
                self.assertEqual(loaded['step'],5)
                self.assertEqual(before,{p.name:p.read_bytes() for p in source.iterdir()})
                with self.assertRaises(ValueError):fixture.restore(root/'copy',c,'old-review')

    def test_stale_source_rejected_before_destination_creation(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);model=larger();c={**fixture.DEFAULT,'optimizer':'adamw'}
            fixture.checkpoint(root/'source',model,state(model.parameters),c,'old')
            with self.assertRaises(ValueError):fixture.copy_checkpoint(root/'source',root/'copy',c,'stale','new')
            self.assertFalse((root/'copy').exists())

    def test_copy_corruption_does_not_publish_checkpoint_header(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);model=larger();c={**fixture.DEFAULT,'optimizer':'adamw'}
            fixture.checkpoint(root/'source',model,state(model.parameters),c,'old')
            original=fixture.shutil.copyfile
            def corrupt(source,destination):
                original(source,destination);Path(destination).write_bytes(b'corrupt')
            with patch.object(fixture.shutil,'copyfile',side_effect=corrupt):
                with self.assertRaises(ValueError):fixture.copy_checkpoint(root/'source',root/'copy',c,'old','new')
            self.assertFalse((root/'copy/checkpoint.json').exists())
            fixture.restore(root/'source',c,'old')
