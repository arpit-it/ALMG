import base64
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams,decoder_stream_indexes as indexes,decoder_stream_token_stats as stats,decoder_stream_tokenizers as tokenizers,decoder_stream_overlap as overlap,decoder_stream_windows as windows
from backend.decoder_tokenizer import ByteTokenizer
from backend.run_manifest import digest


class StreamWindowTests(unittest.TestCase):
    def pipeline(self,lines):
        raw=('\n'.join(lines)+'\n').encode();source=streams.create(self.root,'windows.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        for offset in range(0,len(raw),65536):streams.append(self.root,source['id'],offset,base64.b64encode(raw[offset:offset+65536]).decode(),True)
        streams.seal(self.root,source['id'],True);index=indexes.begin(self.root,source['id'],True)
        while index['status']!='complete':index=indexes.step(self.root,index['id'],True)
        report=stats.begin(self.root,index['id'],True)
        while report['status']!='complete':report=stats.step(self.root,report['id'],True)
        tokenizer=tokenizers.prepare(self.root,report['id'],True,report)
        evidence=overlap.begin(self.root,index['id'],True)
        while evidence['status']!='complete':evidence=overlap.step(self.root,evidence['id'],True)
        return {'index':index,'tokenizer':tokenizer,'overlap':evidence}

    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.review=self.pipeline([' '.join(f'unique{i}word{j}' for j in range(20)) for i in range(121)])
        self.tokenizer_id=self.review['tokenizer']['id'];self.overlap_id=self.review['overlap']['id']

    def test_resume_exact_windows_targets_and_source_references_without_crossing_documents(self):
        source_folder=indexes._folder(self.root,self.review['index']['id']);before={p.name:p.read_bytes() for p in source_folder.iterdir()}
        record=windows.begin(self.root,self.tokenizer_id,self.overlap_id,True,self.review)
        record=windows.step(self.root,record['id'],True);self.assertEqual(record['processed_records'],100)
        importlib.reload(windows);self.assertEqual(windows.read(self.root,record['id']),record)
        while record['status']!='complete':record=windows.step(self.root,record['id'],True)
        artifact=json.loads((tokenizers._folder(self.root,self.tokenizer_id)/'tokenizer.json').read_text());tokenizer=ByteTokenizer.restore(artifact)
        with indexes._connect(source_folder/'records.sqlite3',True) as db:source={row[0]:row[1:] for row in db.execute('SELECT group_sha256,text,split,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents')}
        with indexes._connect(windows._folder(self.root,record['id'])/'windows.sqlite3',True) as db:
            rows=db.execute('SELECT group_sha256,token_offset,split,tokens FROM windows').fetchall()
            for group,offset,split,encoded in rows:
                ids=json.loads(encoded);self.assertEqual(ids,tokenizer.encode(source[group][0])[offset:offset+17])
                self.assertEqual(split,source[group][1]);self.assertTrue(2<=len(ids)<=17);self.assertEqual(offset%16,0)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],121)
        self.assertEqual(len(rows),sum(record['window_counts'].values()))
        self.assertEqual(record['target_tokens'],sum(len(tokenizer.encode(value[0]))-1 for value in source.values()))
        page=windows.record_page(self.root,record['id'],True);self.assertEqual(len(page['records']),10)
        next_page=windows.record_page(self.root,record['id'],True,page['next_cursor'])
        self.assertTrue({(x['group'],x['token_offset']) for x in page['records']}.isdisjoint({(x['group'],x['token_offset']) for x in next_page['records']}))
        with self.assertRaises(ValueError):windows.record_page(self.root,record['id'],True,page['next_cursor'],'test')
        for part in ('train','validation','test'):
            self.assertTrue(all(row['split']==part for row in windows.record_page(self.root,record['id'],True,split=part)['records']))
        self.assertFalse(record['training_approved']);self.assertEqual(before,{p.name:p.read_bytes() for p in source_folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_cross_split_findings_consent_and_stale_reviews_block_before_publication(self):
        with self.assertRaises(ValueError):windows.begin(self.root,self.tokenizer_id,self.overlap_id,False,self.review)
        with self.assertRaises(ValueError):windows.begin(self.root,self.tokenizer_id,self.overlap_id,True,{})
        variants={}
        for i in range(10000):
            text=' '.join([f'baseword{j}' for j in range(50)]+[f'tail{i}']);bucket=int(digest(text)[:8],16)%100
            variants.setdefault('train' if bucket<80 else 'validation' if bucket<90 else 'test',text)
            if len(variants)==3:break
        bad=self.pipeline(list(variants.values()))
        with self.assertRaisesRegex(ValueError,'Cross-split'):windows.begin(self.root,bad['tokenizer']['id'],bad['overlap']['id'],True,bad)
        self.assertFalse((self.root/'decoder-stream-windows').exists())

    def test_partial_batch_rollback_and_changed_code_preserve_progress(self):
        record=windows.begin(self.root,self.tokenizer_id,self.overlap_id,True,self.review)
        original=ByteTokenizer.encode;calls=[]
        def interrupted(text):
            calls.append(1)
            if len(calls)==4:raise RuntimeError('interrupted')
            return original(ByteTokenizer('0'*64),text)
        with patch.object(windows.ByteTokenizer,'encode',side_effect=interrupted):
            with self.assertRaises(RuntimeError):windows.step(self.root,record['id'],True)
        self.assertEqual(windows.read(self.root,record['id']),record)
        with indexes._connect(windows._folder(self.root,record['id'])/'windows.sqlite3',True) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM windows').fetchone()[0],0)
        with patch.object(windows,'_implementation',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'implementation changed'):windows.step(self.root,record['id'],True)
        with self.assertRaises(ValueError):windows.step(self.root,record['id'],False)
        database=indexes._folder(self.root,self.review['index']['id'])/'records.sqlite3'
        with database.open('ab') as output:output.write(b'changed')
        with self.assertRaisesRegex(ValueError,'source index changed'):windows.step(self.root,record['id'],True)
        self.assertEqual(windows.read(self.root,record['id']),record)


if __name__=='__main__':unittest.main()
