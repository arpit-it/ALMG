import importlib
import json
import os
import platform
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_unigram as fits,decoder_stream_unigram_candidates as candidates,decoder_stream_fitted_tokenizer_evaluations as scans,decoder_stream_learned_windows as windows,decoder_stream_learned_batches as batches,decoder_stream_learned_optimization as optimization
from test_stream_character_model_inputs import pipeline as character_pipeline,finish


def pipeline(root,contaminated=False):
    character,_,evidence=character_pipeline(root,contaminated)
    index_id=character['review']['index_id']
    candidate=finish(candidates,root,candidates.begin(root,index_id,True,candidates.review(root,index_id,64)))
    fitted=finish(fits,root,fits.begin(root,candidate['id'],True,fits.review(root,candidate['id'])))
    comparison=finish(scans,root,scans.begin(root,fitted['id'],True,fitted,'unigram'))
    return fitted,comparison,evidence


class UnigramModelInputTests(unittest.TestCase):
    def test_version3_restart_exact_viterbi_ids_masks_provenance_and_complete_splits(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);fitted,comparison,evidence=pipeline(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            review=windows.review(root,comparison['id'],evidence['id'])
            self.assertEqual(review['model_input_profile']['tokenizer_kind'],'unigram');self.assertEqual(review['model_input_profile']['architecture_version'],1)
            record=windows.begin(root,comparison['id'],evidence['id'],True,review)
            with patch.object(windows,'MAX_BATCH_RECORDS',2):record=windows.step(root,record['id'],True)
            self.assertEqual(record['processed_records'],2);importlib.reload(windows);self.assertEqual(windows.read(root,record['id']),record)
            record=finish(windows,root,record);self.assertEqual(record['format'],'almg-stream-learned-windows-v3')
            _,index,codec,_=scans._binding(root,fitted['id'],'unigram',True)
            with windows.indexes._connect(windows.indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                source={group:(text,part,line,sha) for group,text,part,line,sha in db.execute('SELECT group_sha256,text,split,first_line,raw_line_sha256 FROM documents')}
            for split in ('train','validation','test'):
                rows=targets=0
                for batch in batches.iter_batches(root,record['id'],True,record,split,7):
                    self.assertEqual(batch['format'],'almg-stream-learned-model-batch-v3');self.assertEqual(batch['tokenizer_kind'],'unigram')
                    rows+=batch['rows'];targets+=batch['real_target_tokens']
                    for x,y,mask,length,ref in zip(batch['inputs'],batch['targets'],batch['loss_mask'],batch['sequence_lengths'],batch['provenance']):
                        text,part,line,sha=source[ref['group']];ids=codec.encode(text)[ref['token_offset']:ref['token_offset']+17]
                        self.assertEqual(x,ids[:-1]+[0]*(16-length));self.assertEqual(y,ids[1:]+[0]*(16-length));self.assertEqual(mask,[1]*length+[0]*(16-length))
                        self.assertEqual(ref['first_line'],line);self.assertEqual(ref['raw_line_sha256'],sha);self.assertEqual(part,split)
                self.assertEqual(rows,record['window_counts'][split]);self.assertEqual(targets,sum(len(codec.encode(value[0]))-1 for value in source.values() if value[1]==split))
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()));self.assertFalse(record['training_approved'])

    def test_contamination_and_probability_file_rewrite_preserve_progress(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);fitted,comparison,evidence=pipeline(root,True)
            self.assertTrue(comparison['all_records_lossless']);self.assertGreater(evidence['cross_split_pairs'],0)
            with self.assertRaisesRegex(ValueError,'Cross-split'):windows.review(root,comparison['id'],evidence['id'])
            self.assertFalse((root/'decoder-stream-learned-windows').exists())
        with TemporaryDirectory() as temporary:
            root=Path(temporary);fitted,comparison,evidence=pipeline(root)
            record=windows.begin(root,comparison['id'],evidence['id'],True,windows.review(root,comparison['id'],evidence['id']))
            with patch.object(windows,'MAX_BATCH_RECORDS',1):record=windows.step(root,record['id'],True)
            path=fits._folder(root,fitted['id'])/'artifacts'/'tokenizer.json';path.write_bytes(path.read_bytes())
            with self.assertRaisesRegex(ValueError,'bindings changed'):windows.step(root,record['id'],True)
            self.assertEqual(windows.read(root,record['id']),record)

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1' and platform.system()=='Darwin' and platform.machine()=='arm64','Requires explicit local Metal tests')
    def test_real_unigram_inputs_version3_diagnostic_and_saved_report(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);fitted,comparison,evidence=pipeline(root)
            record=windows.begin(root,comparison['id'],evidence['id'],True,windows.review(root,comparison['id'],evidence['id']))
            with patch.object(windows,'_publish',side_effect=OSError('injected v3 publication interruption')):
                with self.assertRaises(OSError):windows.step(root,record['id'],True)
            pending=windows.read(root,record['id'])
            self.assertEqual(pending['schema_version'],3);self.assertEqual(pending['status'],'awaiting_publication')
            record=finish(windows,root,record)
            cursor=None
            while True:
                batch=windows.read_batch(root,record['id'],True,record,cursor)
                if min(batch['sequence_lengths'])<16:break
                cursor=batch['next_cursor'];self.assertIsNotNone(cursor)
            report=optimization.run(root,record['id'],True,record,batch,cursor)
            self.assertEqual(report['format'],'almg-stream-learned-masked-optimizer-check-v3');self.assertEqual(report['schema_version'],3);self.assertEqual(report['tokenizer_kind'],'unigram')
            self.assertGreater(report['padding_targets_changed'],0);self.assertEqual(report['padding_targets_changed'],report['padded_positions'])
            self.assertLess(report['final_batch_loss'],report['initial_batch_loss']);self.assertLessEqual(report['masked_target_gradient_error'],1e-6);self.assertLess(report['cpu_inference_max_error'],1e-5)
            self.assertEqual(optimization.list_reports(root,record['id'],True),[report]);self.assertFalse(report['model_saved']);self.assertFalse(report['training_approved'])
            self.assertEqual(report['evaluation']['test']['windows'],record['window_counts']['test'])
