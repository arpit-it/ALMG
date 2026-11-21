import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import numpy as np
from backend import decoder_corpus_continuations as continuation, decoder_optimizer_state as codec, decoder_optimizer_fixture as fixture
from test_decoder_optimizer_state import state
from test_planned_decoder_compact import larger


class CompactContinuationStateTest(unittest.TestCase):
    def test_completed_counter_requires_explicit_state_scope(self):
        model=larger();original=state(model.parameters);original['step']=10
        config={**fixture.DEFAULT,'optimizer':'adamw'}
        with self.assertRaises(ValueError):codec.encode(original,model.parameters,config,compact=True)
        saved=codec.encode(original,model.parameters,config,compact=True,allow_completed=True)
        with self.assertRaises(ValueError):codec.decode(saved,model.parameters,config,version=2)
        decoded=codec.decode(saved,model.parameters,config,version=2,allow_completed=True)
        self.assertEqual(decoded['step'],10)
        for bad in (0,11,True):
            with self.subTest(step=bad):
                saved['step']=bad
                with self.assertRaises(ValueError):codec.decode(saved,model.parameters,config,version=2,allow_completed=True)

    def test_partial_and_final_legacy_or_compact_state_restore_exactly(self):
        model=larger();config={**fixture.DEFAULT,'optimizer':'adamw'}
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            for step in (5,10):
                original=state(model.parameters);original['step']=step
                for compact in (False,True):
                    saved=codec.encode(original,model.parameters,config,compact=compact,allow_completed=True)
                    (root/'optimizer.json').write_text(json.dumps(saved))
                    restored=continuation._load_state(root,model,config)
                    self.assertEqual(restored['step'],step)
                    for kind in ('m','v'):
                        for name,value in original[kind].items():np.testing.assert_array_equal(restored[kind][name].view(np.uint32),value.view(np.uint32))
                    if step<config['steps']:
                        gradients={name:np.full_like(value,.01) for name,value in model.parameters.items()}
                        expected,_,_=fixture.update(model.parameters,gradients,original,config)
                        actual,_,_=fixture.update(model.parameters,gradients,restored,config)
                        self.assertTrue(all(np.array_equal(actual[name],value) for name,value in expected.items()))

    def test_unknown_state_format_and_negative_variance_rejected(self):
        model=larger();config={**fixture.DEFAULT,'optimizer':'adamw'}
        with TemporaryDirectory() as temporary:
            root=Path(temporary);saved=codec.encode(state(model.parameters),model.parameters,config,compact=True)
            saved['format']='unknown';(root/'optimizer.json').write_text(json.dumps(saved))
            with self.assertRaises(ValueError):continuation._load_state(root,model,config)
            original=state(model.parameters);original['v']['head'][0,0]=-1
            with self.assertRaises(ValueError):codec.encode(original,model.parameters,config,compact=True,allow_completed=True)
