from copy import deepcopy
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import uuid
from backend import decoder_corpus_evaluations as evaluations, decoder_corpus_isolated as isolated
from backend.run_manifest import digest
from test_decoder_corpus_optimizer import corpus


class SavedEvaluationTest(unittest.TestCase):
    def test_unconfirmed_save_and_invalid_ids_do_not_write(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            with self.assertRaises(ValueError):evaluations.save(root,'a'*32,False,{})
            for identifier in ('bad',None,0):
                with self.assertRaises(ValueError):evaluations.review(root,identifier)
                with self.assertRaises(ValueError):evaluations.read(root,identifier)
                with self.assertRaises(ValueError):evaluations.history(root,identifier)
            self.assertEqual(list(root.iterdir()),[])

    def test_missing_or_malformed_evaluation_reports_rejected(self):
        with self.assertRaises(ValueError):evaluations._validate_report({})
        with self.assertRaises(ValueError):evaluations._validate_report([])
        with self.assertRaises(ValueError):evaluations._validate_report(None)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires actual completed model and immutable evaluation evidence')
    def test_real_save_reopen_history_stale_review_and_tamper_rejection(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);source,saved,base=corpus(root)
            config={**base,'steps':10}
            model=isolated.run(root,True,source,saved,config,isolated.review(root,source,saved,config),uuid.uuid4().hex)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            reviewed=evaluations.review(root,model['id'])
            self.assertEqual(reviewed,evaluations.review(root,model['id']))
            self.assertEqual(evaluations.history(root,model['id']),[])
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            stale=deepcopy(reviewed);stale['scope']='changed';stale['revision']=digest({k:v for k,v in stale.items() if k!='revision'})
            with self.assertRaises(ValueError):evaluations.save(root,model['id'],True,stale)
            self.assertEqual(before,{p:p.read_bytes() for p in root.rglob('*') if p.is_file()})
            changed=deepcopy(reviewed);changed['generation']['source']['record_id']='a'*32
            changed['generation']['revision']=digest({k:v for k,v in changed['generation'].items() if k!='revision'})
            changed['revision']=digest({k:v for k,v in changed.items() if k!='revision'})
            with self.assertRaises(ValueError):evaluations._validate_report(changed)
            first=evaluations.save(root,model['id'],True,reviewed);second=evaluations.save(root,model['id'],True,reviewed)
            self.assertNotEqual(first['record']['id'],second['record']['id'])
            self.assertEqual(first['report'],reviewed)
            with patch.object(evaluations,'review',side_effect=AssertionError('Historical evidence must not be recomputed.')):
                self.assertEqual(evaluations.read(root,first['record']['id']),first)
            history=evaluations.history(root,model['id']);self.assertEqual({r['id'] for r in history},{first['record']['id'],second['record']['id']})
            self.assertEqual(evaluations.history(root,'b'*32),[])
            for field in ('training_approved','release_approved'):self.assertFalse(first['record'][field])
            self.assertFalse(first['report']['language_quality_validated'])
            folder=root/'decoder-corpus-evaluations'/first['record']['id'];path=folder/'report.json';original=path.read_bytes()
            try:
                path.write_bytes(original+b' ')
                with self.assertRaises(ValueError):evaluations.read(root,first['record']['id'])
                self.assertEqual([r['id'] for r in evaluations.history(root,model['id'])],[second['record']['id']])
            finally:path.write_bytes(original)
            path=folder/'record.json';original=path.read_bytes()
            try:
                manifest=json.loads(original);manifest['source']['record_id']='c'*32
                manifest['revision']=digest({k:v for k,v in manifest.items() if k!='revision'});path.write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):evaluations.read(root,first['record']['id'])
            finally:path.write_bytes(original)
            self.assertEqual(evaluations.read(root,first['record']['id']),first)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
