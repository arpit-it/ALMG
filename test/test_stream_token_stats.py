import base64
from collections import Counter
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_token_stats as stats
from backend.decoder_tokenizer import ByteTokenizer


class StreamByteStatisticsTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        lines=[f'Local café unique document {i} with several words' for i in range(230)]+['alpha '*1000]
        raw=('\n'.join(lines+[lines[0]]*2)+'\n').encode()
        source=streams.create(self.root,'café.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        self.index=indexes.begin(self.root,source['id'],True)
        while self.index['status']!='complete':self.index=indexes.step(self.root,self.index['id'],True)

    def test_resumes_complete_histograms_and_preserves_source_without_fitting(self):
        index=self.index;folder=indexes._folder(self.root,index['id'])
        before={p.name:p.read_bytes() for p in folder.iterdir()}
        report=stats.begin(self.root,index['id'],True);report=stats.step(self.root,report['id'],True)
        self.assertEqual(report['processed_records'],100)
        with patch.object(stats,'_save',side_effect=OSError('simulated publication failure')):
            with self.assertRaises(OSError):stats.step(self.root,report['id'],True)
        self.assertEqual(stats.read(self.root,report['id']),report)
        importlib.reload(stats)
        self.assertEqual(stats.read(self.root,report['id']),report)
        while report['status']!='complete':report=stats.step(self.root,report['id'],True)
        self.assertEqual(report['processed_records'],231)
        with indexes._connect(folder/'records.sqlite3',True) as db:rows=db.execute('SELECT text,split,occurrences FROM documents').fetchall()
        for part,summary in report['splits'].items():
            population=[(text,n) for text,split,n in rows if split==part]
            histogram=Counter();weighted=Counter()
            for text,n in population:
                byte_counts=Counter(text.encode());histogram.update(byte_counts)
                weighted.update({token:count*n for token,count in byte_counts.items()})
                if len(text.encode())<=4096:self.assertEqual(ByteTokenizer('0'*64).encode(text),list(text.encode()))
            self.assertEqual(summary['token_counts'],[histogram[i] for i in range(256)])
            self.assertEqual(summary['occurrence_weighted_token_counts'],[weighted[i] for i in range(256)])
            self.assertEqual(summary['tokens'],sum(histogram.values()))
            self.assertEqual(summary['occurrence_weighted_tokens'],sum(weighted.values()))
            self.assertEqual(summary['source_occurrences'],sum(n for _,n in population))
        self.assertEqual(sum(x['records_over_current_tokenizer_limit'] for x in report['splits'].values()),1)
        self.assertFalse(report['method']['tokenizer_fitted']);self.assertFalse(report['training_approved'])
        self.assertEqual(report['source_provenance']['source_sha256'],index['source_sha256'])
        self.assertEqual(stats.step(self.root,report['id'],True),report)
        self.assertEqual(stats.list_reports(self.root,index['id']),[report])
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertNotIn('Local café',json.dumps(report,ensure_ascii=False))
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_consent_source_changes_and_code_changes_preserve_progress(self):
        with self.assertRaises(ValueError):stats.begin(self.root,self.index['id'],False)
        report=stats.begin(self.root,self.index['id'],True)
        with self.assertRaises(ValueError):stats.step(self.root,report['id'],False)
        with patch.object(stats,'_implementation',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'implementation changed'):stats.step(self.root,report['id'],True)
        self.assertEqual(stats.read(self.root,report['id']),report)
        database=indexes._folder(self.root,self.index['id'])/'records.sqlite3'
        with database.open('ab') as output:output.write(b'changed')
        with self.assertRaisesRegex(ValueError,'source index changed'):stats.step(self.root,report['id'],True)
        self.assertEqual(stats.read(self.root,report['id']),report)

    def test_report_tampering_and_unfinished_indexes_reject(self):
        pending=indexes.begin(self.root,self.index['source_id'],True)
        with self.assertRaisesRegex(ValueError,'Complete text indexing'):stats.begin(self.root,pending['id'],True)
        report=stats.begin(self.root,self.index['id'],True)
        path=stats._folder(self.root,report['id'])/'report.json'
        changed=dict(report,processed_records=9);path.write_text(json.dumps(changed))
        with self.assertRaisesRegex(ValueError,'integrity check'):stats.read(self.root,report['id'])


if __name__=='__main__':unittest.main()
