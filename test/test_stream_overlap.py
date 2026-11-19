import base64
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_overlap as overlap
from backend.run_manifest import digest


def fixture_lines(noise=20):
    variants={}
    for i in range(10000):
        text=' '.join([f'baseword{j}' for j in range(50)]+[f'tail{i}'])
        bucket=int(digest(text)[:8],16)%100
        split='train' if bucket<80 else 'validation' if bucket<90 else 'test'
        variants.setdefault(split,text)
        if len(variants)==3:break
    return list(variants.values())+[' '.join(f'unique{i}word{j}' for j in range(20)) for i in range(noise)]+['short text']


class StreamOverlapTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        lines=fixture_lines();raw=('\n'.join(lines+[lines[0]])+'\n').encode()
        source=streams.create(self.root,'overlap.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        self.index=indexes.begin(self.root,source['id'],True)
        while self.index['status']!='complete':self.index=indexes.step(self.root,self.index['id'],True)
        self.id=self.index['id']

    def test_exhaustive_resume_finds_all_three_cross_split_pairs_with_both_source_references(self):
        folder=indexes._folder(self.root,self.id);before={p.name:p.read_bytes() for p in folder.iterdir()}
        report=overlap.begin(self.root,self.id,True)
        report=overlap.step(self.root,report['id'],True);self.assertEqual(report['processed_pairs'],100)
        importlib.reload(overlap);self.assertEqual(overlap.read(self.root,report['id']),report)
        while report['status']!='complete':report=overlap.step(self.root,report['id'],True)
        self.assertEqual(report['processed_pairs'],276);self.assertEqual(report['total_pairs'],276)
        self.assertEqual(report['near_duplicate_pairs'],3);self.assertEqual(report['cross_split_pairs'],3)
        self.assertEqual(report['short_pairs_skipped'],23)
        rows=[];cursor=None
        while True:
            page=overlap.record_page(self.root,report['id'],True,cursor,limit=1);rows+=page['records'];cursor=page['next_cursor']
            if cursor is None:break
        self.assertEqual(len(rows),3);self.assertEqual(len({row['pair_id'] for row in rows}),3)
        self.assertTrue(all(row['similarity']>=.8 and len(row['records'])==2 for row in rows))
        self.assertTrue(all(ref['source_sha256']==self.index['source_sha256'] and ref['first_line']>0 for row in rows for ref in row['records']))
        self.assertNotIn('baseword',json.dumps(rows))
        for split in ('train','validation','test'):
            page=overlap.record_page(self.root,report['id'],True,split=split)
            self.assertEqual(len(page['records']),2)
            self.assertTrue(all(any(ref['split']==split for ref in row['records']) for row in page['records']))
        first=overlap.record_page(self.root,report['id'],True,limit=1)
        with self.assertRaises(ValueError):overlap.record_page(self.root,report['id'],True,first['next_cursor'],'train')
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_batch_failure_and_changed_source_or_implementation_preserve_committed_cursor(self):
        report=overlap.begin(self.root,self.id,True)
        with patch.object(overlap.Tokenizer,'words',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):overlap.step(self.root,report['id'],True)
        self.assertEqual(overlap.read(self.root,report['id']),report)
        with patch.object(overlap,'_implementation',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'implementation changed'):overlap.step(self.root,report['id'],True)
        with (indexes._folder(self.root,self.id)/'records.sqlite3').open('ab') as output:output.write(b'changed')
        with self.assertRaisesRegex(ValueError,'source index changed'):overlap.step(self.root,report['id'],True)
        self.assertEqual(overlap.read(self.root,report['id']),report)

    def test_consent_and_incomplete_record_review_reject(self):
        with self.assertRaises(ValueError):overlap.begin(self.root,self.id,False)
        report=overlap.begin(self.root,self.id,True)
        with self.assertRaises(ValueError):overlap.step(self.root,report['id'],False)
        with self.assertRaises(ValueError):overlap.record_page(self.root,report['id'],True)
        with self.assertRaises(ValueError):overlap.record_page(self.root,report['id'],False)


if __name__=='__main__':unittest.main()
