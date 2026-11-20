import base64
from collections import Counter
import hashlib
import importlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import zipfile
from backend import decoder_stream_character_bpe as fits,decoder_stream_indexes as indexes,decoder_streams as streams,decoder_stream_fitted_tokenizer_evaluations as scans,decoder_stream_learned_windows as windows,decoder_stream_permissions as permissions
from backend.decoder_character_bpe import CharacterBPE
from backend.run_manifest import digest


def finish(worker,root,record):
    while record['status']!='complete':record=worker.step(root,record['id'],True)
    return record


def fixture(root,extra=None):
    lines=[f'record {i} banana bandana café 世界 abcdefghijklmnopqrstuvwxyz 0123456789' for i in range(41)]
    if extra:lines+=extra
    raw=('\n'.join(lines+[lines[0]])+'\n').encode();source=streams.create(root,'characters.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
    for offset in range(0,len(raw),65536):streams.append(root,source['id'],offset,base64.b64encode(raw[offset:offset+65536]).decode(),True)
    streams.seal(root,source['id'],True)
    return finish(indexes,root,indexes.begin(root,source['id'],True))


class WholeCharacterBPETests(unittest.TestCase):
    def test_complete_alphabet_counts_and_merges_use_all_unique_training_records_and_resume(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);record=fits.begin(root,index['id'],True,fits.review(root,index['id'],64))
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file() and 'decoder-stream-character-bpe-fits' not in str(p)}
            with patch.object(fits,'MAX_BATCH_RECORDS',3):record=fits.step(root,record['id'],True)
            self.assertEqual(record['status'],'alphabet');self.assertEqual(record['processed_records'],3)
            importlib.reload(fits);self.assertEqual(fits.read(root,record['id']),record)
            while record['status']=='alphabet':record=fits.step(root,record['id'],True)
            self.assertEqual(record['status'],'counting');self.assertTrue(record['alphabet']);self.assertEqual(record['processed_records'],0)
            importlib.reload(fits);self.assertEqual(fits.read(root,record['id']),record)
            record=finish(fits,root,record)
            with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                rows=db.execute('SELECT group_sha256,text,split FROM documents ORDER BY group_sha256').fetchall()
            train=[text for _,text,part in rows if part=='train'];self.assertGreater(len(train),16)
            counts=Counter(''.join(train));self.assertEqual(record['alphabet'],sorted(counts));self.assertEqual(record['alphabet_counts'],[counts[c] for c in sorted(counts)])
            sequences=[[record['alphabet'].index(c) for c in text] for text in train]
            for rank,pair in enumerate(record['merges']):
                pairs=Counter(p for seq in sequences for p in zip(seq,seq[1:]));best=min(pairs,key=lambda p:(-pairs[p],p))
                self.assertEqual(list(best),pair);self.assertEqual(record['merge_history'][rank]['frequency'],pairs[best])
                sequences=[CharacterBPE._merge(seq,best,len(counts)+rank) for seq in sequences]
            chain=digest([])
            for group,text,part in rows:
                if part=='train':chain=digest({'previous':chain,'group_sha256':group})
            self.assertEqual(record['training_chain_sha256'],chain);self.assertEqual(record['vocabulary_size'],64)
            artifact=json.loads((fits._folder(root,record['id'])/'artifacts'/'tokenizer.json').read_text());codec=fits.StreamCharacterBPE.restore(artifact)
            for _,text,_ in rows:self.assertEqual(codec.decode(codec.encode(text)),text)
            self.assertEqual(codec.decode(codec.encode('banana '*9000)),'banana '*9000)
            with self.assertRaises(ValueError):codec.encode('Ω')
            exported=fits.export(root,record['id'],True,record)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as archive:self.assertEqual(json.loads(archive.read('tokenizer.json')),artifact)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            self.assertFalse(record['model_training_enabled']);self.assertEqual(fits.step(root,record['id'],True),record)

    def test_heldout_only_character_stays_uncovered_in_complete_comparison(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            extra=next(f'heldout Ω tail{i}' for i in range(10000) if int(digest(f'heldout Ω tail{i}')[:8],16)%100>=80)
            index=fixture(root,[extra]);record=finish(fits,root,fits.begin(root,index['id'],True,fits.review(root,index['id'],64)))
            self.assertNotIn('Ω',record['alphabet'])
            before={p:p.read_bytes() for p in fits._folder(root,record['id']).rglob('*') if p.is_file()}
            report=finish(scans,root,scans.begin(root,record['id'],True,record,'character_bpe'))
            self.assertFalse(report['all_records_lossless']);self.assertEqual(report['processed_records'],index['unique_records'])
            self.assertEqual(sum(v['uncovered_characters'] for v in report['splits'].values()),1)
            self.assertEqual(sum(v['encoding_failures'] for v in report['splits'].values()),1)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            with self.assertRaisesRegex(ValueError,'character-BPE admission'):windows.review(root,report['id'],'a'*32)

    def test_alphabet_overflow_consent_and_changed_review_fail_without_publication(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root)
            for cap in (True,31,513):
                with self.assertRaises(ValueError):fits.review(root,index['id'],cap)
            review=fits.review(root,index['id'],32)
            with self.assertRaises(ValueError):fits.begin(root,index['id'],False,review)
            with self.assertRaises(ValueError):fits.begin(root,index['id'],True,{**review,'vocabulary_cap':64})
            record=fits.begin(root,index['id'],True,review)
            with self.assertRaisesRegex(ValueError,'alphabet exceeds'):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)
            with indexes._connect(fits._folder(root,record['id'])/'work.sqlite3',True) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM characters').fetchone()[0],0)
            self.assertFalse((fits._folder(root,record['id'])/'artifacts').exists())

    def test_atomic_alphabet_pass_and_publication_recovery_and_permission_guards(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);record=fits.begin(root,index['id'],True,fits.review(root,index['id'],64))
            with patch.object(fits,'_write',side_effect=OSError('injected transaction failure')):
                with self.assertRaises(ValueError):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)
            record=fits.step(root,record['id'],True);self.assertEqual(record['status'],'counting')
            while len(record['alphabet'])+len(record['merges'])<63:record=fits.step(root,record['id'],True)
            with patch.object(fits,'_publish',side_effect=OSError('publication interrupted')):
                with self.assertRaises(ValueError):fits.step(root,record['id'],True)
            pending=fits.read(root,record['id']);self.assertEqual(pending['status'],'awaiting_publication')
            complete=fits.step(root,record['id'],True);self.assertEqual(complete['merges'],pending['merges'])
            other=fits.begin(root,index['id'],True,fits.review(root,index['id'],64))
            old=permissions.review(root,index['id']);permissions.declare(root,index['id'],True,old,'user_created','QA')
            with self.assertRaisesRegex(ValueError,'permissions changed'):fits.step(root,other['id'],True)
            self.assertEqual(fits.read(root,other['id']),other)

    def test_alphabet_seen_only_late_in_training_and_pair_transaction_rollback(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            late=next(f'late Ж banana tail{i}' for i in range(10000) if int(digest(f'late Ж banana tail{i}')[:8],16)%100<80)
            index=fixture(root,[late]);record=fits.begin(root,index['id'],True,fits.review(root,index['id'],64))
            with patch.object(fits,'MAX_BATCH_RECORDS',1):
                while record['status']=='alphabet':record=fits.step(root,record['id'],True)
            self.assertIn('Ж',record['alphabet']);self.assertEqual(record['alphabet_counts'][record['alphabet'].index('Ж')],1)
            with patch.object(fits,'_write',side_effect=OSError('injected pair transaction failure')):
                with self.assertRaises(ValueError):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)
            with indexes._connect(fits._folder(root,record['id'])/'work.sqlite3',True) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0],0)
            self.assertEqual(finish(fits,root,record)['vocabulary_size'],64)
