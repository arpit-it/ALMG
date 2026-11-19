"""Stage contracts and stored reproducibility snapshots, including legacy artifacts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from backend import decoder_trials, decoder_bundle, decoder_recipe, recipe_contracts
from backend.decoder_tokenizer import Tokenizer


class DecoderPipelineTest(unittest.TestCase):
    def setUp(self):
        for name in ('_ACTIVE','_CANCEL','_READINESS'):
            patcher=patch.object(decoder_trials,name,set() if name=='_ACTIVE' else {})
            patcher.start();self.addCleanup(patcher.stop)

    def fixture(self,root,legacy=False):
        record=decoder_trials.start(root,True,Mock())
        record.update(status='complete',result={'weight_origin':'newly_initialized'})
        path=decoder_trials.folder(root,record['id'])/'artifacts/bundle'
        path.parent.mkdir(parents=True)
        decoder_bundle.save(path,decoder_recipe.Decoder({'vocab_size':4}),Tokenizer.fit(['amber birch cedar dune']),{'seed':7,'steps':0,'weight_origin':'newly_initialized'})
        if legacy:
            record['specification']['recipe_contract'].pop('pipeline')
            record['specification'].pop('post_training')
            record['approval']['revision']=decoder_trials.approval_revision(record)
            manifest=json.loads((path/'manifest.json').read_text());manifest.pop('pipeline');manifest.pop('post_training')
            (path/'manifest.json').write_text(json.dumps(manifest))
        decoder_trials.write(root,record)
        return record,path

    def test_complete_stage_versions_are_saved_in_bundle_and_approval_bound_spec(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);record,path=self.fixture(root)
            before=(decoder_trials.folder(root,record['id'])/'record.json').read_bytes()
            result=decoder_trials.pipeline_record(root,record['id'],True)
            self.assertEqual(result['contract_origin'],'saved')
            self.assertEqual(len(result['stage_interfaces']['stages']),8)
            self.assertEqual(result['post_training'],{'version':1,'mode':'none'})
            self.assertEqual(result['verified_artifacts']['bundle']['manifest']['pipeline'],result['stage_interfaces'])
            snapshot=decoder_trials.folder(root,record['id'])/'pipeline-record.json'
            self.assertEqual(json.loads(snapshot.read_text()),result)
            self.assertEqual(decoder_trials.pipeline_record(root,record['id'],True)['revision'],result['revision'])
            self.assertEqual((snapshot.parent/'record.json').read_bytes(),before)
            self.assertEqual(decoder_bundle.load(path)[2]['post_training'],{'version':1,'mode':'none'})

    def test_legacy_manifest_snapshot_is_explicitly_derived_and_does_not_rewrite_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);record,path=self.fixture(root,True)
            original={p.name:p.read_bytes() for p in path.iterdir()}
            result=decoder_trials.pipeline_record(root,record['id'],True)
            self.assertEqual(result['contract_origin'],'legacy_derived')
            self.assertEqual({p.name:p.read_bytes() for p in path.iterdir()},original)
            with self.assertRaises(ValueError):decoder_trials.pipeline_record(root,record['id'],False)
            legacy=json.loads((path/'manifest.json').read_text())
            (path/'manifest.json').write_text(json.dumps({**legacy,'post_training':{'version':1,'mode':'sft'}}))
            with self.assertRaises(ValueError):decoder_bundle.load(path)
            (path/'manifest.json').write_bytes(original['manifest.json'])
            (path/'decoder.json').write_text('{}')
            with self.assertRaises(ValueError):decoder_trials.pipeline_record(root,record['id'],True)

    def test_invalid_contracts_and_unsupported_post_training_fail_before_queue(self):
        contract=recipe_contracts.recipe_contract('decoder_from_scratch')
        for change in ('missing','bool_version','post_mode'):
            pipeline=json.loads(json.dumps(contract['pipeline']))
            if change=='missing':pipeline['stages'].pop('inference')
            if change=='bool_version':pipeline['stages']['pretraining']['version']=True
            if change=='post_mode':pipeline['stages']['post_training']['modes']=['sft']
            registry=recipe_contracts.RecipeRegistry()
            with self.assertRaises(ValueError):registry.register({**contract,'pipeline':pipeline})
        with tempfile.TemporaryDirectory() as temporary:
            submit=Mock()
            for policy in ({'version':1,'mode':'sft'},{'version':True,'mode':'none'},'none',{'version':1,'mode':'none','weights':'external'}):
                with self.assertRaises(ValueError):decoder_trials.start(Path(temporary),True,submit,post_training=policy)
            submit.assert_not_called()
            self.assertEqual(decoder_trials.list_trials(Path(temporary)),[])
