import base64
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import decoder_stream_tokenizer_evaluations as evaluations, decoder_stream_tokenizer_experiments as experiments
from backend import decoder_stream_indexes as indexes, decoder_streams as streams, decoder_stream_permissions as permissions
from backend.decoder_special_tokens import SpecialTokenizer, restore_base
from backend.decoder_bpe import ByteBPE


def fixture(root,algorithm='byte_level_bpe',replace=False):
    texts=[f'local record {i} banana bandana café 世界 abcdefghijklmnopqrstuvwxyz' for i in range(180)]
    texts += ['oversized '+('abcdefghij '*450)+str(i) for i in range(40)]
    texts += ['unusual Ω 🐈 😀 heldout label '+str(i) for i in range(9)]
    data=('\n'.join(texts+[texts[0]])+'\n').encode()
    source=streams.create(root,'eval.txt',len(data),hashlib.sha256(data).hexdigest(),True)
    for offset in range(0,len(data),65536):streams.append(root,source['id'],offset,base64.b64encode(data[offset:offset+65536]).decode(),True)
    streams.seal(root,source['id'],True);index=indexes.begin(root,source['id'],True)
    while index['status']!='complete':index=indexes.step(root,index['id'],True)
    config={'algorithm':algorithm,'vocabulary_cap':320 if algorithm=='byte_level_bpe' else 128}
    if replace:config.update(special_tokens={'bos':'<B>','eos':'<E>','unk':'<U>'},unknown_policy='replace')
    reviewed=experiments.review(root,index['id'],config)
    return index,experiments.train(root,index['id'],True,reviewed)


def finish(root,record):
    while record['status']!='complete':record=evaluations.step(root,record['id'],True)
    return record


class StreamTokenizerEvaluationTests(unittest.TestCase):
    def test_full_population_resume_counts_match_independent_encoding_and_originals_unchanged(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index,exp=fixture(root)
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            record=evaluations.begin(root,exp['id'],True,exp)
            with patch.object(evaluations,'MAX_BATCH_RECORDS',7):record=evaluations.step(root,record['id'],True)
            self.assertEqual(record['processed_records'],7);self.assertEqual(record['status'],'scanning')
            with patch.object(evaluations,'MAX_BATCH_BYTES',1):record=evaluations.step(root,record['id'],True)
            self.assertEqual(record['processed_records'],8)
            importlib.reload(evaluations)
            self.assertEqual(evaluations.read(root,record['id']),record)
            with patch.object(ByteBPE,'fit',side_effect=AssertionError('Comparison must not refit the tokenizer')):
                record=finish(root,record)
            model=restore_base(json.loads((experiments._folder(root,exp['id'])/'tokenizer.json').read_text()))
            with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                rows=list(db.execute('SELECT text,split,occurrences FROM documents'))
            for split,stats in record['splits'].items():
                selected=[(text,occ) for text,part,occ in rows if part==split]
                eligible=[text for text,occ in selected if len(text.encode())<=4096]
                self.assertEqual(stats['records'],len(selected));self.assertEqual(stats['source_occurrences'],sum(o for _,o in selected))
                self.assertEqual(stats['lossless_records'],len(eligible))
                self.assertEqual(stats['lossless_tokens'],sum(len(model.encode(text)) for text in eligible))
                self.assertEqual(stats['lossless_bytes'],sum(len(text.encode()) for text in eligible))
            self.assertEqual(record['processed_records'],index['unique_records'])
            self.assertEqual(sum(s['unsupported_records'] for s in record['splits'].values()),40)
            self.assertLessEqual(len(record['finding_samples']['unsupported']),20)
            self.assertFalse(record['all_records_lossless']);self.assertFalse(record['model_training_enabled'])
            self.assertEqual(evaluations.step(root,record['id'],True),record)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            self.assertFalse((root/'decoder-trials').exists())

    def test_lossy_replacement_is_not_lossless_and_oov_rejection_is_counted(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            for replace in (False,True):
                index,exp=fixture(root,'unigram',replace)
                record=finish(root,evaluations.begin(root,exp['id'],True,exp))
                folder=experiments._folder(root,exp['id'])
                artifact=json.loads((folder/'tokenizer.json').read_text())
                model=SpecialTokenizer.restore(artifact) if replace else restore_base(artifact)
                with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                    eligible=[text for text, in db.execute('SELECT text FROM documents') if len(text.encode())<=4096]
                missing=sum(model.uncovered(text)>0 for text in eligible)
                self.assertGreater(missing,0)
                key='lossy_records' if replace else 'encoding_failures'
                self.assertEqual(sum(s[key] for s in record['splits'].values()),missing)
                if replace:self.assertGreater(sum(s['unknown_tokens'] for s in record['splits'].values()),0)
                self.assertFalse(record['all_records_lossless'])

    def test_confirmation_code_change_source_change_and_permission_change_preserve_progress(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index,exp=fixture(root)
            with self.assertRaises(ValueError):evaluations.begin(root,exp['id'],False,exp)
            with self.assertRaises(ValueError):evaluations.begin(root,exp['id'],True,{})
            record=evaluations.begin(root,exp['id'],True,exp)
            with self.assertRaises(ValueError):evaluations.step(root,record['id'],False)
            with patch.object(evaluations,'_implementation',return_value='0'*64):
                with self.assertRaisesRegex(ValueError,'implementation changed'):evaluations.step(root,record['id'],True)
            old=permissions.review(root,index['id']);permissions.declare(root,index['id'],True,old,'user_created','QA author')
            with self.assertRaisesRegex(ValueError,'permissions changed'):evaluations.step(root,record['id'],True)
            self.assertEqual(evaluations.read(root,record['id']),record)
            original=streams.folder(root,index['source_id'])/'source.bin';original.write_bytes(original.read_bytes()+b'x')
            with self.assertRaisesRegex(ValueError,'integrity changed'):evaluations.step(root,record['id'],True)
            self.assertEqual(evaluations.read(root,record['id']),record)

    def test_atomic_save_failure_and_mid_batch_binding_change_do_not_advance_cursor(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);_,exp=fixture(root)
            record=evaluations.begin(root,exp['id'],True,exp)
            with patch.object(Path,'replace',side_effect=OSError('fixture disk failure')):
                with self.assertRaisesRegex(ValueError,'saved progress is preserved'):evaluations.step(root,record['id'],True)
            self.assertEqual(evaluations.read(root,record['id']),record)
            original=evaluations._binding;calls=0
            def changed(*args):
                nonlocal calls
                result=original(*args);calls+=1
                if calls==2:return ({**result[0],'revision':'0'*64},*result[1:])
                return result
            with patch.object(evaluations,'_binding',side_effect=changed):
                with self.assertRaisesRegex(ValueError,'changed during'):evaluations.step(root,record['id'],True)
            self.assertEqual(evaluations.read(root,record['id']),record)
            self.assertEqual(evaluations.list_reports(root,exp['id']),[record])
            self.assertFalse(any(p.suffix=='.tmp' for p in evaluations._folder(root,record['id']).iterdir()))
            final=finish(root,record);path=evaluations._folder(root,record['id'])/'report.json'
            final['processed_records']+=1;path.write_text(json.dumps(final))
            with self.assertRaises(ValueError):evaluations.read(root,record['id'])
