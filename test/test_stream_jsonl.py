import base64
import hashlib
import importlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from backend import decoder_stream_jsonl as worker,decoder_streams as streams,decoder_stream_indexes as indexes,decoder_stream_exports as exports,decoder_stream_token_stats as stats
from backend.run_manifest import digest


class StreamJsonlTests(unittest.TestCase):
    def setUp(self):
        temporary=TemporaryDirectory();self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)

    def source(self,raw):
        record=streams.create(self.root,'records.jsonl',len(raw),hashlib.sha256(raw).hexdigest(),True)
        for offset in range(0,len(raw),65536):streams.append(self.root,record['id'],offset,base64.b64encode(raw[offset:offset+65536]).decode(),True)
        streams.seal(self.root,record['id'],True);return record

    def test_pause_reload_resume_dedup_and_original_line_provenance_survive_export(self):
        bodies=[f'Local café record {i} with distinct topic word{i} and synthetic text.' for i in range(61)]
        lines=[json.dumps({'text':body},ensure_ascii=False).encode()+b'\n' for body in bodies]
        lines.insert(2,b'\n');lines.append(lines[0]);raw=b'\xef\xbb\xbf'+b''.join(lines)
        source=self.source(raw);record=worker.begin(self.root,source['id'],True)
        with patch.object(worker,'MAX_STEP_LINES',7):paused=worker.step(self.root,record['id'],True)
        self.assertEqual(paused['lines'],7);self.assertEqual(paused['status'],'indexing')
        importlib.reload(worker);self.assertEqual(indexes.read(self.root,record['id']),paused)
        while record['status']!='complete':record=worker.step(self.root,record['id'],True)
        self.assertEqual(record['unique_records'],61);self.assertEqual(record['duplicate_records'],1);self.assertEqual(record['empty_lines'],1)
        self.assertEqual(record['method']['input_format'],'jsonl_text_only_v1')
        self.assertEqual((streams.folder(self.root,source['id'])/'source.bin').read_bytes(),raw)
        with indexes._connect(indexes._folder(self.root,record['id'])/'records.sqlite3',True) as db:
            rows=db.execute('SELECT text,first_line,first_byte_offset,raw_line_sha256,occurrences FROM documents').fetchall()
        for text,line,offset,line_hash,occurrences in rows:
            original=raw.splitlines(keepends=True)[line-1]
            self.assertEqual(offset,sum(len(item) for item in raw.splitlines(keepends=True)[:line-1]))
            self.assertEqual(line_hash,hashlib.sha256(original).hexdigest())
            self.assertEqual(text,' '.join(json.loads(original.decode('utf-8').removeprefix('\ufeff'))['text'].split()))
        review=exports.review(self.root,record['id'])
        payload=exports.chunk(self.root,record['id'],True,review,'manifest.json',0)
        exported=json.loads(base64.b64decode(payload['data']))
        self.assertEqual(exported,record)
        self.assertEqual(exports.seal(self.root,record['id'],True,review)['revision'],review['revision'])
        distribution=stats.begin(self.root,record['id'],True)
        while distribution['status']!='complete':distribution=stats.step(self.root,distribution['id'],True)
        self.assertEqual(sum(part['unique_records'] for part in distribution['splits'].values()),61)

    def test_malformed_record_rolls_back_entire_batch_and_preserves_prior_cursor(self):
        raw=b'{"text":"first synthetic document"}\n{"text":"second synthetic document"}\n{"text":"third","extra":true}\n'
        source=self.source(raw);record=worker.begin(self.root,source['id'],True)
        with patch.object(worker,'MAX_STEP_LINES',1):record=worker.step(self.root,record['id'],True)
        before=indexes.read(self.root,record['id'])
        with self.assertRaisesRegex(ValueError,'line 3'):worker.step(self.root,record['id'],True)
        self.assertEqual(indexes.read(self.root,record['id']),before)
        with indexes._connect(indexes._folder(self.root,record['id'])/'records.sqlite3',True) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM documents').fetchone()[0],1)
        with self.assertRaises(ValueError):worker.step(self.root,record['id'],False)

    def test_consent_encoding_schema_control_limits_and_legacy_separation(self):
        for raw in (b'{"text":"x","text":"y"}\n',b'{"text":null}\n',b'{"text":""}\n',b'["x"]\n',b'\xff\n',b'{"text":"\\ud800"}\n',b'{"text":"\\u0000"}\n',b'x'*65537):
            source=self.source(raw)
            with self.assertRaises(ValueError):worker.begin(self.root,source['id'],False)
            record=worker.begin(self.root,source['id'],True)
            with self.subTest(raw=raw[:30]),self.assertRaises(ValueError):worker.step(self.root,record['id'],True)
            self.assertEqual(indexes.read(self.root,record['id'])['offset'],0)
        source=self.source(b'original plain text document\n')
        legacy=indexes.begin(self.root,source['id'],True)
        with self.assertRaisesRegex(ValueError,'not a JSONL'):worker.step(self.root,legacy['id'],True)
        self.assertEqual(indexes.step(self.root,legacy['id'],True)['status'],'complete')
