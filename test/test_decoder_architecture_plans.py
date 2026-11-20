from copy import deepcopy
import importlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_architecture_plans as plans
from backend.decoder_recipe import Decoder


class ArchitecturePlanTests(unittest.TestCase):
    def test_legacy_compatible_layout_matches_actual_shapes_count_and_bytes(self):
        review=plans.review(dict(plans.DEFAULT));model=Decoder({'vocab_size':64,'width':8,'context_length':16,'seed':7})
        self.assertEqual(review['calculated_parameter_count'],sum(value.size for value in model.parameters.values()))
        self.assertEqual(review['estimates']['weight_bytes'],sum(value.nbytes for value in model.parameters.values()))
        for name,value in model.parameters.items():
            key=name if name in ('token_embedding','position_embedding','head') else 'layers.0.'+name
            self.assertEqual(review['parameter_shapes'][key],list(value.shape))
        self.assertFalse(review['estimates']['measured']);self.assertFalse(review['execution_available'])

    def test_multilayer_multihead_arithmetic_and_invalid_relationships_without_allocation(self):
        config={**plans.DEFAULT,'layers':2,'hidden_size':16,'attention_heads':2,'head_dim':8,'feed_forward_size':32,'context_length':32,'vocab_size':128}
        with patch.object(Decoder,'__init__',side_effect=AssertionError('Planning must not allocate weights')):
            review=plans.review(config)
            self.assertEqual(review['calculated_parameter_count'],8704);self.assertEqual(len(review['parameter_shapes']),15)
            for changes in ({'attention_heads':3},{'head_dim':True},{'layers':0},{'hidden_size':129},{'feed_forward_size':8},{'vocab_size':513},{'activation':'gelu'},{'unexpected':1}):
                with self.assertRaises(ValueError):plans.review({**config,**changes})

    def test_consent_stale_review_restart_and_tamper_preserve_prior_plans(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);review=plans.review(dict(plans.DEFAULT))
            with self.assertRaises(ValueError):plans.save(root,False,review)
            altered=deepcopy(review);altered['config']['layers']=2
            with self.assertRaises(ValueError):plans.save(root,True,altered)
            self.assertFalse((root/'decoder-architecture-plans').exists())
            record=plans.save(root,True,review);path=root/'decoder-architecture-plans'/record['id']/'plan.json';before=path.read_bytes()
            importlib.reload(plans);self.assertEqual(plans.read(root,record['id']),record)
            self.assertEqual(plans.list_plans(root,True),[record]);self.assertEqual(path.read_bytes(),before)
            path.write_text('{}')
            self.assertEqual(plans.list_plans(root,True),[])

    def test_failed_atomic_publication_leaves_no_saved_plan(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with patch.object(Path,'rename',side_effect=OSError('publication failed')):
                with self.assertRaises(OSError):plans.save(root,True,plans.review(dict(plans.DEFAULT)))
            self.assertEqual(plans.list_plans(root,True),[])
