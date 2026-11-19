import base64
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_streams as streams, decoder_stream_indexes as indexes, decoder_stream_languages as reports


class StreamLanguageTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
        lines=[f'This local document describes an orchard harvest and astronomy observations number {i}.' for i in range(230)]+['12345']
        raw=('\n'.join(lines+[lines[0]])+'\n').encode()
        source=streams.create(self.root,'languages.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
        streams.append(self.root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(self.root,source['id'],True)
        self.index=indexes.begin(self.root,source['id'],True)
        while self.index['status']!='complete':self.index=indexes.step(self.root,self.index['id'],True)
        self.id=self.index['id']

    def test_resume_full_record_reports_with_provenance_and_bounded_pages(self):
        folder=indexes._folder(self.root,self.id);before={p.name:p.read_bytes() for p in folder.iterdir()}
        report=reports.begin(self.root,self.id,True)
        with patch.object(reports.languages,'_recognize',side_effect=lambda texts:[{'en':.95,'fr':.02} for _ in texts]):
            report=reports.step(self.root,report['id'],True);self.assertEqual(report['processed_records'],100)
            importlib.reload(reports);self.assertEqual(reports.read(self.root,report['id']),report)
            while report['status']!='complete':report=reports.step(self.root,report['id'],True)
        self.assertEqual(report['identified_records'],230);self.assertEqual(report['unknown_records'],1)
        self.assertEqual(report['language_counts'],{'en':230,'und':1})
        self.assertEqual(report['source_occurrences'],232)
        self.assertEqual(sum(sum(v.values()) for v in report['split_language_counts'].values()),231)
        page=reports.record_page(self.root,report['id'],True);self.assertEqual(len(page['records']),10)
        all_rows=[];cursor=None
        while True:
            page=reports.record_page(self.root,report['id'],True,cursor,limit=20);all_rows+=page['records'];cursor=page['next_cursor']
            if cursor is None:break
        self.assertEqual(len(all_rows),231)
        self.assertEqual(len({r['group'] for r in all_rows}),231)
        self.assertTrue(all(r['source_sha256']==self.index['source_sha256'] and r['text_omitted'] for r in all_rows))
        self.assertNotIn('This local document',json.dumps(all_rows))
        first=reports.record_page(self.root,report['id'],True)
        with self.assertRaises(ValueError):reports.record_page(self.root,report['id'],True,first['next_cursor'],'test')
        self.assertEqual(reports.list_audits(self.root,self.id),[report])
        self.assertEqual(reports.step(self.root,report['id'],True),report)
        self.assertEqual(before,{p.name:p.read_bytes() for p in folder.iterdir()})
        self.assertFalse((self.root/'decoder-trials').exists())

    def test_provider_unavailable_is_unknown_and_transaction_failure_preserves_progress(self):
        report=reports.begin(self.root,self.id,True)
        with patch.object(reports.languages,'_recognize',side_effect=RuntimeError('interrupted')):
            with self.assertRaises(RuntimeError):reports.step(self.root,report['id'],True)
        self.assertEqual(reports.read(self.root,report['id']),report)
        with patch.object(reports.languages,'_recognize',return_value=None):
            while report['status']!='complete':report=reports.step(self.root,report['id'],True)
        self.assertEqual(report['unknown_records'],231);self.assertEqual(report['identified_records'],0)
        self.assertEqual(report['unavailable_batches'],3)
        page=reports.record_page(self.root,report['id'],True)
        self.assertTrue(all(r['reason'] in ('provider_unavailable','insufficient_alphabetic_text') for r in page['records']))

    def test_consent_implementation_source_changes_and_report_integrity_reject(self):
        with self.assertRaises(ValueError):reports.begin(self.root,self.id,False)
        report=reports.begin(self.root,self.id,True)
        with self.assertRaises(ValueError):reports.step(self.root,report['id'],False)
        with patch.object(reports,'_implementation',return_value='changed'):
            with self.assertRaisesRegex(ValueError,'implementation changed'):reports.step(self.root,report['id'],True)
        database=indexes._folder(self.root,self.id)/'records.sqlite3'
        with database.open('ab') as output:output.write(b'changed')
        with self.assertRaisesRegex(ValueError,'source index changed'):reports.step(self.root,report['id'],True)
        self.assertEqual(reports.read(self.root,report['id']),report)
        with self.assertRaises(ValueError):reports.record_page(self.root,report['id'],True)


if __name__=='__main__':unittest.main()
