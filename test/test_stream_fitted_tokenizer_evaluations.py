import base64
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import decoder_stream_fitted_tokenizer_evaluations as scans,decoder_stream_iterative_bpe as iterative,decoder_stream_bpe as one
from backend import decoder_stream_indexes as indexes,decoder_streams as streams,decoder_stream_permissions as permissions


def fixture(root):
    texts=[f'local record {i} abcdefghijklmnopqrstuvwxyz banana café 世界' for i in range(100)]
    texts+=['long '+('abcdefghij '*450)+str(i) for i in range(12)]
    data=('\n'.join(texts+[texts[0]])+'\n').encode()
    source=streams.create(root,'compare-fit.txt',len(data),hashlib.sha256(data).hexdigest(),True)
    for offset in range(0,len(data),65536):streams.append(root,source['id'],offset,base64.b64encode(data[offset:offset+65536]).decode(),True)
    streams.seal(root,source['id'],True);index=indexes.begin(root,source['id'],True)
    while index['status']!='complete':index=indexes.step(root,index['id'],True)
    return index


def finish(worker,root,record):
    while record['status']!='complete':record=worker.step(root,record['id'],True)
    return record


class FittedTokenizerComparisonTests(unittest.TestCase):
    def test_both_completed_codecs_compare_all_records_including_over_4096_without_refitting(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root)
            for kind,worker,cap in [('one_merge',one,257),('iterative',iterative,260)]:
                fitted=finish(worker,root,worker.begin(root,index['id'],True,worker.review(root,index['id'],cap)))
                before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
                report=scans.begin(root,fitted['id'],True,fitted,kind)
                with patch.object(scans,'MAX_BATCH_RECORDS',9):report=scans.step(root,report['id'],True)
                self.assertEqual(report['processed_records'],9)
                importlib.reload(scans);self.assertEqual(scans.read(root,report['id']),report)
                with patch.object(worker,'step',side_effect=AssertionError('Comparison must not advance or refit the tokenizer')):
                    report=finish(scans,root,report)
                self.assertTrue(report['all_records_lossless']);self.assertEqual(report['processed_records'],index['unique_records'])
                self.assertEqual(report['method']['maximum_encoded_record_bytes'],65536)
                self.assertFalse(report['model_training_enabled']);self.assertFalse(report['tokenizer_refitted'])
                codec=worker.StreamByteBPE.restore(json.loads((worker._folder(root,fitted['id'])/'artifacts'/'tokenizer.json').read_text()))
                with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                    rows=list(db.execute('SELECT text,split FROM documents'))
                for split,value in report['splits'].items():
                    selected=[text for text,part in rows if part==split]
                    self.assertEqual(value['records'],len(selected));self.assertEqual(value['unsupported_records'],0)
                    self.assertEqual(value['lossless_tokens'],sum(len(codec.encode(text)) for text in selected))
                    self.assertEqual(value['lossless_bytes'],sum(len(text.encode()) for text in selected))
                self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
                self.assertEqual(scans.step(root,report['id'],True),report)
                self.assertEqual(scans.list_reports(root,fitted['id'],kind),[report])

    def test_typed_scope_confirmation_completion_and_permission_guards(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);pending=iterative.begin(root,index['id'],True,iterative.review(root,index['id'],260))
            with self.assertRaisesRegex(ValueError,'Complete'):scans.begin(root,pending['id'],True,pending,'iterative')
            fitted=finish(iterative,root,pending)
            for confirmed,reviewed,kind in [(False,fitted,'iterative'),(True,{},'iterative'),(True,fitted,'wrong'),(True,fitted,'one_merge')]:
                with self.assertRaises(ValueError):scans.begin(root,fitted['id'],confirmed,reviewed,kind)
            report=scans.begin(root,fitted['id'],True,fitted,'iterative')
            old=permissions.review(root,index['id']);permissions.declare(root,index['id'],True,old,'user_created','QA')
            with self.assertRaisesRegex(ValueError,'permissions changed'):scans.step(root,report['id'],True)
            self.assertEqual(scans.read(root,report['id']),report)

    def test_same_bytes_codec_rewrite_during_batch_invalidates_signatures_without_publishing_counts(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);fitted=finish(one,root,one.begin(root,index['id'],True,one.review(root,index['id'])))
            report=scans.begin(root,fitted['id'],True,fitted,'one_merge')
            artifact=one._folder(root,fitted['id'])/'artifacts'/'tokenizer.json'
            binding=scans._binding;calls=0
            def rewritten(*args):
                nonlocal calls
                calls+=1
                if calls==2:artifact.write_bytes(artifact.read_bytes())
                return binding(*args)
            with patch.object(scans,'_binding',side_effect=rewritten):
                with self.assertRaisesRegex(ValueError,'changed during'):scans.step(root,report['id'],True)
            self.assertEqual(scans.read(root,report['id']),report)

    def test_atomic_failure_codec_tamper_and_source_change_keep_saved_progress(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);fitted=finish(one,root,one.begin(root,index['id'],True,one.review(root,index['id'])))
            report=scans.begin(root,fitted['id'],True,fitted,'one_merge')
            with patch.object(Path,'replace',side_effect=OSError('fixture save failure')):
                with self.assertRaises(ValueError):scans.step(root,report['id'],True)
            self.assertEqual(scans.read(root,report['id']),report)
            codec=one._folder(root,fitted['id'])/'artifacts'/'tokenizer.json';before=codec.read_bytes();codec.write_text('{}')
            with self.assertRaises(ValueError):scans.step(root,report['id'],True)
            self.assertEqual(scans.read(root,report['id']),report);codec.write_bytes(before)
            source=streams.folder(root,index['source_id'])/'source.bin';source.write_bytes(source.read_bytes()+b'x')
            with self.assertRaises(ValueError):scans.step(root,report['id'],True)
            self.assertEqual(scans.read(root,report['id']),report)
