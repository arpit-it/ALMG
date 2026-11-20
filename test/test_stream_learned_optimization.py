import json
import os
import platform
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_learned_optimization as optimization, decoder_stream_learned_batches as batches, decoder_stream_learned_windows as windows
from backend import decoder_stream_permissions as permissions
from test_stream_learned_windows import pipeline, finish


def fixture_batch(split='train'):
    lengths=[16,16,16,4]
    return {'rows':4,'inputs':[[256+(j+i)%4 for j in range(length)]+[0]*(16-length) for i,length in enumerate(lengths)],
            'targets':[[256+(j+i+1)%4 for j in range(length)]+[0]*(16-length) for i,length in enumerate(lengths)],
            'loss_mask':[[1]*length+[0]*(16-length) for length in lengths], 'sequence_lengths':lengths,
            'real_target_tokens':sum(lengths),'split':split,'next_cursor':None,'vocabulary_size':260,'tokenizer_sha256':'f'*64,
            'provenance':[{'group':'a'*64,'token_offset':i*16,'split':split} for i in range(4)]}


def read_fixture(root,window_id,confirmed,reviewed,cursor=None,split='train',batch_size=4):return fixture_batch(split)
REVIEW={'format':'almg-stream-learned-windows-v1','revision':'r','vocabulary_size':260,'window_counts':{'validation':4,'test':4}}
METAL=os.environ.get('ALMG_METAL_TESTS')=='1' and platform.system()=='Darwin' and platform.machine()=='arm64'


class LearnedOptimizationTests(unittest.TestCase):
    def test_consent_stale_batch_and_invalid_scope_never_initialize(self):
        with TemporaryDirectory() as root,patch.object(optimization.core.recipe_contracts,'initialize_recipe') as initialize:
            with self.assertRaises(ValueError):optimization.run(root,'a'*32,False,REVIEW,fixture_batch())
            with patch.object(batches,'read_batch',side_effect=read_fixture):
                with self.assertRaisesRegex(ValueError,'batch changed'):optimization.run(root,'a'*32,True,REVIEW,{})
                if platform.system()=='Darwin' and platform.machine()=='arm64':
                    with self.assertRaisesRegex(ValueError,'vocabulary'):optimization.run(root,'a'*32,True,{**REVIEW,'vocabulary_size':256},fixture_batch())
            initialize.assert_not_called();self.assertEqual(list(Path(root).iterdir()),[])

    @unittest.skipUnless(METAL,'Requires explicit local Metal tests')
    def test_wider_real_masked_sgd_and_report_reload_without_model_artifacts(self):
        with TemporaryDirectory() as root,patch.object(batches,'read_batch',side_effect=read_fixture),patch.object(batches,'iter_batches',side_effect=lambda root,wid,confirmed,reviewed,split,size:iter([fixture_batch(split)])),patch.object(optimization.core.decoder_bundle,'save') as save:
            report=optimization.run(root,'a'*32,True,REVIEW,fixture_batch())
            self.assertEqual(report['model_config']['vocab_size'],260);self.assertEqual(report['model_architecture_version'],2)
            self.assertEqual(report['tokenizer_sha256'],'f'*64);self.assertEqual(report['padded_positions'],12)
            self.assertLess(report['final_batch_loss'],report['initial_batch_loss']);self.assertLess(report['cpu_inference_max_error'],1e-5)
            self.assertLessEqual(report['masked_target_loss_error'],1e-6);self.assertLessEqual(report['masked_target_gradient_error'],1e-6)
            self.assertEqual(len(report['changed_parameter_tensors']),report['parameter_tensors'])
            for key in ('model_saved','training_approved','release_approved','pretrained_weights_loaded'):self.assertFalse(report[key])
            self.assertEqual(report['evaluation']['test']['scope'],'all_saved_split_windows');save.assert_not_called()
            self.assertEqual(optimization.list_reports(root,'a'*32,True),[report])
            self.assertEqual(optimization.core.list_reports(root,'a'*32,True),[])
            files=list(Path(root).rglob('*'));self.assertEqual(len([p for p in files if p.is_file()]),1)

    @unittest.skipUnless(METAL,'Requires explicit local Metal tests')
    def test_source_change_after_gpu_prevents_learned_report_publication(self):
        calls=0
        def changed(*args,**kwargs):
            nonlocal calls
            calls+=1;batch=read_fixture(*args,**kwargs)
            return {**batch,'changed':True} if calls==2 else batch
        with TemporaryDirectory() as root,patch.object(batches,'read_batch',side_effect=changed),patch.object(batches,'iter_batches',side_effect=lambda root,wid,confirmed,reviewed,split,size:iter([fixture_batch(split)])):
            with self.assertRaisesRegex(ValueError,'Source bindings changed'):optimization.run(root,'a'*32,True,REVIEW,fixture_batch())
            self.assertEqual(list(Path(root).iterdir()),[])


class LearnedCompleteSplitTests(unittest.TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        comparison,evidence=pipeline(self.root,[f'record{i} banana café 世界' for i in range(61)])
        review=windows.review(self.root,comparison['id'],evidence['id'])
        self.record=finish(windows,self.root,windows.begin(self.root,comparison['id'],evidence['id'],True,review))

    def test_all_windows_match_reviewed_pages_and_full_hashes_only_at_boundaries(self):
        for split in ('validation','test'):
            with patch.object(batches,'_validated',wraps=batches._validated) as validate:
                actual=list(batches.iter_batches(self.root,self.record['id'],True,self.record,split,3))
            self.assertEqual(validate.call_count,2)
            expected=[];cursor=None
            while True:
                page=windows.read_batch(self.root,self.record['id'],True,self.record,cursor,split,3);expected.append(page);cursor=page['next_cursor']
                if cursor is None:break
            self.assertEqual(actual,expected);self.assertEqual(sum(page['rows'] for page in actual),self.record['window_counts'][split])
            targets=sum(page['real_target_tokens'] for page in actual)
            result=optimization.core.evaluate_split(self.root,self.record['id'],self.record,split,lambda page:(float(page['real_target_tokens']*2),page['real_target_tokens']),batch_worker=batches)
            self.assertEqual(result['target_tokens'],targets);self.assertEqual(result['loss'],2.0);self.assertEqual(result['next_token_accuracy'],1.0)

    def test_changes_between_pages_fail_before_completion_metrics(self):
        scan=batches.iter_batches(self.root,self.record['id'],True,self.record,'train',1);next(scan)
        old=permissions.review(self.root,self.record['index_id']);permissions.declare(self.root,self.record['index_id'],True,old,'user_created','QA')
        with self.assertRaisesRegex(ValueError,'permissions changed'):next(scan)

    def test_window_database_rewrite_detected_between_pages(self):
        scan=batches.iter_batches(self.root,self.record['id'],True,self.record,'test',1);next(scan)
        database=windows._folder(self.root,self.record['id'])/'windows.sqlite3';database.write_bytes(database.read_bytes())
        with self.assertRaisesRegex(ValueError,'source files changed'):next(scan)


class CharacterOptimizationTests(unittest.TestCase):
    @unittest.skipUnless(METAL,'Requires explicit local Metal tests')
    def test_actual_character_profile_updates_and_version2_report_reload(self):
        review={**REVIEW,'format':'almg-stream-learned-windows-v2','schema_version':2,'fit_kind':'character_bpe','vocabulary_size':64}
        def read(root,wid,confirmed,reviewed,cursor=None,split='train',batch_size=4):
            batch=fixture_batch(split)
            return {**batch,'format':'almg-stream-learned-model-batch-v2','schema_version':2,'tokenizer_kind':'character_bpe','vocabulary_size':64,
                    'inputs':[[value%64 for value in row] for row in batch['inputs']],
                    'targets':[[value%64 for value in row] for row in batch['targets']]}
        with TemporaryDirectory() as root,patch.object(batches,'read_batch',side_effect=read),patch.object(batches,'iter_batches',side_effect=lambda root,wid,confirmed,reviewed,split,size:iter([read(root,wid,True,reviewed,split=split)])):
            report=optimization.run(root,'c'*32,True,review,read(root,'c'*32,True,review))
            self.assertEqual(report['format'],'almg-stream-learned-masked-optimizer-check-v2');self.assertEqual(report['schema_version'],2)
            self.assertEqual(report['tokenizer_kind'],'character_bpe');self.assertEqual(report['model_architecture_version'],1)
            self.assertEqual(report['vocabulary_size'],64);self.assertLess(report['final_batch_loss'],report['initial_batch_loss'])
            self.assertEqual(report['padded_positions'],12);self.assertLessEqual(report['masked_target_gradient_error'],1e-6)
            self.assertLess(report['cpu_inference_max_error'],1e-5);self.assertEqual(optimization.list_reports(root,'c'*32,True),[report])
            self.assertFalse(report['model_saved']);self.assertFalse(report['training_approved']);self.assertFalse(report['release_approved'])
            with patch.object(optimization.core.recipe_contracts,'initialize_recipe') as initialize:
                with self.assertRaisesRegex(ValueError,'contract changed'):optimization.run(root,'c'*32,True,{**review,'fit_kind':'iterative'},read(root,'c'*32,True,review))
                initialize.assert_not_called()

    @unittest.skipUnless(METAL,'Requires explicit local Metal tests')
    def test_127_id_character_padding_probe_changes_every_masked_target(self):
        review={**REVIEW,'format':'almg-stream-learned-windows-v2','schema_version':2,'fit_kind':'character_bpe','vocabulary_size':127}
        def read(root,wid,confirmed,reviewed,cursor=None,split='train',batch_size=4):
            batch=fixture_batch(split)
            return {**batch,'schema_version':2,'tokenizer_kind':'character_bpe','vocabulary_size':127,
                    'inputs':[[value%127 for value in row] for row in batch['inputs']],
                    'targets':[[value%127 for value in row] for row in batch['targets']]}
        with TemporaryDirectory() as root,patch.object(batches,'read_batch',side_effect=read),patch.object(batches,'iter_batches',side_effect=lambda root,wid,confirmed,reviewed,split,size:iter([read(root,wid,True,reviewed,split=split)])):
            report=optimization.run(root,'d'*32,True,review,read(root,'d'*32,True,review))
            self.assertEqual(report['padding_targets_changed'],12);self.assertEqual(report['padded_positions'],12)
            self.assertLessEqual(report['masked_target_loss_error'],1e-6);self.assertLessEqual(report['masked_target_gradient_error'],1e-6)
