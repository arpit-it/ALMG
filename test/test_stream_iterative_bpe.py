import base64
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend import decoder_stream_iterative_bpe as fits,decoder_stream_bpe as legacy,decoder_streams as streams,decoder_stream_indexes as indexes
from backend.decoder_bpe import ByteBPE


def fixture(root,uniform=False):
    texts=[f'record {i} banana bandana café 世界 abcdefghijklmnopqrstuvwxyz' for i in range(12)]
    if uniform:texts=['a','b','c']
    data=('\n'.join(texts)+'\n').encode()
    source=streams.create(root,'iterative.txt',len(data),hashlib.sha256(data).hexdigest(),True)
    streams.append(root,source['id'],0,base64.b64encode(data).decode(),True);streams.seal(root,source['id'],True)
    index=indexes.begin(root,source['id'],True)
    while index['status']!='complete':index=indexes.step(root,index['id'],True)
    return index


def finish(root,record):
    while record['status']!='complete':record=fits.step(root,record['id'],True)
    return record


class IterativeStreamBPETests(unittest.TestCase):
    def test_all_merge_ranks_match_existing_bpe_oracle_and_resume_between_passes(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root)
            record=fits.begin(root,index['id'],True,fits.review(root,index['id'],260))
            while record['completed_passes']<1:
                with patch.object(fits,'MAX_BATCH_RECORDS',2):record=fits.step(root,record['id'],True)
            self.assertEqual(record['processed_records'],0);self.assertEqual(len(record['merges']),1)
            first=record['merges'][0];importlib.reload(fits);self.assertEqual(fits.read(root,record['id']),record)
            record=finish(root,record)
            with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                train=[text for text, in db.execute('SELECT text FROM documents WHERE split=? ORDER BY group_sha256',('train',))]
            oracle=ByteBPE.fit(train,260)
            self.assertEqual(record['merges'],oracle.merges);self.assertEqual(record['merges'][0],first)
            self.assertEqual(record['completed_passes'],4);self.assertEqual(record['vocabulary_size'],260)
            self.assertEqual(record['processed_records'],len(train))
            artifact=json.loads((fits._folder(root,record['id'])/'artifacts'/'tokenizer.json').read_text())
            codec=fits.StreamByteBPE.restore(artifact)
            for text in train+['unseen café 世界 🚀','ab '*20000]:self.assertEqual(codec.decode(codec.encode(text)),text)
            self.assertEqual([row['id'] for row in record['merge_history']],list(range(256,260)))
            self.assertFalse(record['model_training_enabled'])
            self.assertEqual(fits.step(root,record['id'],True),record)

    def test_maximum_sixteen_merges_matches_the_existing_oracle(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root)
            record=finish(root,fits.begin(root,index['id'],True,fits.review(root,index['id'],272)))
            with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                train=[text for text, in db.execute('SELECT text FROM documents WHERE split=? ORDER BY group_sha256',('train',))]
            self.assertEqual(record['merges'],ByteBPE.fit(train,272).merges)
            self.assertEqual(len(record['merges']),16)
            self.assertEqual(record['vocabulary_size'],272)

    def test_pass_transition_rolls_back_merges_counters_and_cursor_on_failure(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);record=fits.begin(root,index['id'],True,fits.review(root,index['id'],260))
            with patch.object(fits,'_write',side_effect=OSError('fixture boundary failure')):
                with self.assertRaises(ValueError):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)
            with indexes._connect(fits._folder(root,record['id'])/'work.sqlite3',True) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0],0)
            complete=finish(root,record);self.assertEqual(len(complete['merges']),4)

    def test_publication_recovery_and_legacy_one_merge_fit_remain_compatible(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root)
            old=legacy.begin(root,index['id'],True,legacy.review(root,index['id']))
            record=fits.begin(root,index['id'],True,fits.review(root,index['id'],264))
            with patch.object(fits,'_publish',side_effect=OSError('fixture interrupted publication')):
                with self.assertRaises(ValueError):finish(root,record)
            pending=fits.read(root,record['id']);self.assertEqual(pending['status'],'awaiting_publication')
            complete=fits.step(root,record['id'],True);self.assertEqual(len(complete['merges']),8)
            while old['status']!='complete':old=legacy.step(root,old['id'],True)
            self.assertEqual(old['learned_merges'],complete['merges'][:1]);self.assertEqual(legacy.read(root,old['id']),old)
            self.assertEqual(old['vocabulary_size'],257)

    def test_invalid_caps_and_large_requested_cap_stops_when_no_pairs_remain(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root,True)
            for cap in (True,255,273,512):
                with self.assertRaises(ValueError):fits.review(root,index['id'],cap)
            for cap in (256,272):
                record=finish(root,fits.begin(root,index['id'],True,fits.review(root,index['id'],cap)))
                self.assertEqual(record['merges'],[]);self.assertEqual(record['vocabulary_size'],256)
                self.assertEqual(record['completed_passes'],1)
