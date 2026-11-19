import base64
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_streams as streams,decoder_stream_indexes as indexes,decoder_stream_token_stats as statistics,decoder_stream_tokenizers as tokenizers
from backend.decoder_tokenizer import ByteTokenizer


class StreamTokenizerTests(unittest.TestCase):
    def make_report(self,lines):
        raw=('\n'.join(lines)+'\n').encode();source=streams.create(self.root,'tokenizer.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        index=indexes.begin(self.root,source['id'],True)
        while index['status']!='complete':index=indexes.step(self.root,index['id'],True)
        report=statistics.begin(self.root,index['id'],True)
        while report['status']!='complete':report=statistics.step(self.root,report['id'],True)
        return index,report

    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        self.index,self.report=self.make_report([f'Local café document number {i} with orchard and astronomy words' for i in range(230)])

    def test_saved_artifact_matches_training_only_fit_and_survives_reload_without_mutating_index(self):
        folder=indexes._folder(self.root,self.index['id']);before={p.name:p.read_bytes() for p in folder.iterdir()}
        manifest=tokenizers.prepare(self.root,self.report['id'],True,self.report)
        self.assertEqual(tokenizers.read(self.root,manifest['id']),manifest)
        with indexes._connect(folder/'records.sqlite3',True) as db:
            training=[row[0] for row in db.execute("SELECT text FROM documents WHERE split='train' ORDER BY group_sha256")]
            all_records=[row[0] for row in db.execute('SELECT text FROM documents ORDER BY group_sha256')]
        artifact=json.loads((tokenizers._folder(self.root,manifest['id'])/'tokenizer.json').read_text())
        expected=ByteTokenizer.fit(training)
        self.assertEqual(artifact,expected.artifact());self.assertEqual(manifest['tokenizer_sha256'],expected.fingerprint())
        all_hash=hashlib.sha256(json.dumps(all_records,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        self.assertNotEqual(artifact['training_documents_sha256'],all_hash)
        self.assertEqual(ByteTokenizer.restore(artifact).decode(expected.encode('café orchard')),'café orchard')
        self.assertFalse(manifest['training_approved']);self.assertFalse(manifest['method']['vocabulary_fitted'])
        self.assertEqual(tokenizers.list_tokenizers(self.root,self.index['id']),[manifest])
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_consent_stale_and_unfinished_reports_cannot_publish(self):
        with self.assertRaises(ValueError):tokenizers.prepare(self.root,self.report['id'],False,self.report)
        with self.assertRaises(ValueError):tokenizers.prepare(self.root,self.report['id'],True,dict(self.report,revision='changed'))
        pending=statistics.begin(self.root,self.index['id'],True)
        with self.assertRaisesRegex(ValueError,'Complete byte distribution'):tokenizers.prepare(self.root,pending['id'],True,pending)
        self.assertFalse((self.root/'decoder-stream-tokenizers').exists())

    def test_oversized_records_and_tampered_artifacts_fail_closed(self):
        _,long_report=self.make_report(['alpha '*1000,'short orchard words','short telescope words'])
        with self.assertRaisesRegex(ValueError,'4096-byte'):tokenizers.prepare(self.root,long_report['id'],True,long_report)
        self.assertFalse((self.root/'decoder-stream-tokenizers').exists())
        manifest=tokenizers.prepare(self.root,self.report['id'],True,self.report)
        (tokenizers._folder(self.root,manifest['id'])/'tokenizer.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'integrity'):tokenizers.read(self.root,manifest['id'])


if __name__=='__main__':unittest.main()
