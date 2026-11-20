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

from backend import decoder_stream_bpe as fits,decoder_streams as streams,decoder_stream_indexes as indexes,decoder_stream_permissions as permissions
from backend.run_manifest import digest


def fixture(root):
    texts=[f'local record {i} abcdefghijklmnopqrstuvwxyz banana' for i in range(120)]
    texts+=['oversized '+('abcdefghij '*450)+str(i) for i in range(4)]
    for j in range(2):
        for i in range(100):
            text=('zz '*4000)+f'heldout {j} {i}'
            if int(digest(text)[:8],16)%100>=80:break
        texts.append(text)
    data=('\n'.join(texts+[texts[0]])+'\n').encode()
    source=streams.create(root,'fit.txt',len(data),hashlib.sha256(data).hexdigest(),True)
    for offset in range(0,len(data),65536):streams.append(root,source['id'],offset,base64.b64encode(data[offset:offset+65536]).decode(),True)
    streams.seal(root,source['id'],True);index=indexes.begin(root,source['id'],True)
    while index['status']!='complete':index=indexes.step(root,index['id'],True)
    return index


def finish(root,record):
    while record['status']!='complete':record=fits.step(root,record['id'],True)
    return record


class WholeSplitBPETests(unittest.TestCase):
    def test_global_training_counts_chain_heldout_exclusion_and_restart_export(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            review=fits.review(root,index['id']);record=fits.begin(root,index['id'],True,review)
            with patch.object(fits,'MAX_BATCH_RECORDS',7):record=fits.step(root,record['id'],True)
            self.assertEqual(record['processed_records'],7)
            importlib.reload(fits);self.assertEqual(fits.read(root,record['id']),record)
            record=finish(root,record);counts=Counter();all_counts=Counter();chain=digest([]);size=n=0
            with indexes._connect(indexes._folder(root,index['id'])/'records.sqlite3',True) as db:
                for group,text,split in db.execute('SELECT group_sha256,text,split FROM documents ORDER BY group_sha256'):
                    encoded=text.encode();all_counts.update(zip(encoded,encoded[1:]))
                    if split=='train':
                        counts.update(zip(encoded,encoded[1:]));chain=digest({'previous':chain,'group_sha256':group});n+=1;size+=len(encoded)
            winner=min(counts,key=lambda pair:(-counts[pair],pair))
            self.assertEqual(record['learned_merges'],[list(winner)]);self.assertEqual(record['pair_frequency'],counts[winner])
            self.assertNotEqual(winner,min(all_counts,key=lambda pair:(-all_counts[pair],pair)))
            self.assertEqual((record['processed_records'],record['training_bytes'],record['training_chain_sha256']),(n,size,chain))
            self.assertEqual(n,index['split_counts']['train']);self.assertEqual(record['vocabulary_size'],257)
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            artifact=json.loads((fits._folder(root,record['id'])/'artifacts'/'tokenizer.json').read_text());codec=fits.StreamByteBPE.restore(artifact)
            for text in ['café 世界 🚀','ab '*20000]:self.assertEqual(codec.decode(codec.encode(text)),text)
            self.assertEqual(fits.step(root,record['id'],True),record)
            exported=fits.export(root,record['id'],True,record)
            with zipfile.ZipFile(io.BytesIO(base64.b64decode(exported['data']))) as z:
                self.assertEqual(set(z.namelist()),{'manifest.json','tokenizer.json'})
                self.assertEqual(json.loads(z.read('manifest.json')),record)
                self.assertEqual(fits.StreamByteBPE.restore(json.loads(z.read('tokenizer.json'))).artifact(),artifact)
            self.assertFalse(record['model_training_enabled']);self.assertFalse((root/'decoder-trials').exists())

    def test_sql_transaction_failure_and_post_count_publication_recovery(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);record=fits.begin(root,index['id'],True,fits.review(root,index['id']))
            with patch.object(fits,'_write',side_effect=OSError('fixture disk failure')):
                with self.assertRaisesRegex(ValueError,'committed progress is preserved'):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)
            with indexes._connect(fits._folder(root,record['id'])/'work.sqlite3',True) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM pairs').fetchone()[0],0)
            with patch.object(fits,'_publish',side_effect=OSError('fixture publication interruption')):
                with self.assertRaises(ValueError):finish(root,record)
            pending=fits.read(root,record['id']);self.assertEqual(pending['status'],'awaiting_publication')
            self.assertEqual(pending['processed_records'],pending['total_records'])
            complete=fits.step(root,record['id'],True)
            self.assertEqual(complete['training_chain_sha256'],pending['training_chain_sha256'])
            self.assertEqual(fits.list_fits(root,index['id']),[complete])

    def test_lost_response_after_atomic_publication_recovers_without_overwriting_artifacts(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);record=fits.begin(root,index['id'],True,fits.review(root,index['id']))
            publish=fits._publish
            def lost_response(*args):
                publish(*args)
                raise OSError('fixture response lost after publication')
            with patch.object(fits,'_publish',side_effect=lost_response):
                with self.assertRaises(ValueError):finish(root,record)
            recovered=fits.read(root,record['id']);self.assertEqual(recovered['status'],'complete')
            files={p:p.read_bytes() for p in (fits._folder(root,record['id'])/'artifacts').iterdir()}
            self.assertEqual(fits.step(root,record['id'],True),recovered)
            self.assertTrue(all(p.read_bytes()==data for p,data in files.items()))

    def test_invalid_confirmation_cap_stale_review_permissions_and_code(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root)
            for cap in (True,255,258,512):
                with self.assertRaises(ValueError):fits.review(root,index['id'],cap)
            review=fits.review(root,index['id'])
            for confirmed,reviewed in [(False,review),(True,{})]:
                with self.assertRaises(ValueError):fits.begin(root,index['id'],confirmed,reviewed)
            with patch.object(fits.shutil,'disk_usage',return_value=type('Disk',(),{'free':0})()):
                with self.assertRaisesRegex(ValueError,'scratch space'):fits.begin(root,index['id'],True,review)
            record=fits.begin(root,index['id'],True,review)
            with self.assertRaises(ValueError):fits.step(root,record['id'],False)
            with patch.object(fits,'_implementation',return_value='0'*64):
                with self.assertRaisesRegex(ValueError,'implementation changed'):fits.step(root,record['id'],True)
            old=permissions.review(root,index['id']);permissions.declare(root,index['id'],True,old,'user_created','QA')
            with self.assertRaisesRegex(ValueError,'permissions changed'):fits.step(root,record['id'],True)
            self.assertEqual(fits.read(root,record['id']),record)

    def test_zero_merge_baseline_and_tampered_codec_are_explicit(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);index=fixture(root);record=finish(root,fits.begin(root,index['id'],True,fits.review(root,index['id'],256)))
            self.assertEqual(record['learned_merges'],[]);self.assertEqual(record['vocabulary_size'],256)
            for confirmed,reviewed in [(False,record),(True,{})]:
                with self.assertRaises(ValueError):fits.export(root,record['id'],confirmed,reviewed)
            path=fits._folder(root,record['id'])/'artifacts'/'tokenizer.json';artifact=json.loads(path.read_text());artifact['maximum_learned_merges']=2
            with self.assertRaises(ValueError):fits.StreamByteBPE.restore(artifact)
            path.write_text('{}')
            with self.assertRaises(ValueError):fits.read(root,record['id'])
