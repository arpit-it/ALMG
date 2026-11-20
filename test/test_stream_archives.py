import base64
import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile
from backend import decoder_stream_archives as archives,decoder_streams as streams,decoder_stream_indexes as indexes,decoder_stream_iterative_bpe as fits,decoder_stream_fitted_tokenizer_evaluations as scans,decoder_stream_overlap as overlap,decoder_stream_learned_windows as windows,decoder_stream_training as training,decoder_stream_evaluations as evaluations,decoder_stream_previews as previews,decoder_bundle
from test_stream_learned_windows import finish
import test_stream_previews as preview_tests


def passing_fixture(root):
    raw=('\n'.join('a'*60+str(i) for i in range(121))+'\n').encode()
    source=streams.create(root,'archive-fixture.txt',len(raw),hashlib.sha256(raw).hexdigest(),True)
    streams.append(root,source['id'],0,base64.b64encode(raw).decode(),True);streams.seal(root,source['id'],True)
    index=finish(indexes,root,indexes.begin(root,source['id'],True))
    fit=finish(fits,root,fits.begin(root,index['id'],True,fits.review(root,index['id'],256)))
    comparison=finish(scans,root,scans.begin(root,fit['id'],True,fit,'iterative'))
    evidence=finish(overlap,root,overlap.begin(root,index['id'],True))
    record=finish(windows,root,windows.begin(root,comparison['id'],evidence['id'],True,windows.review(root,comparison['id'],evidence['id'])))
    run=training.begin(root,record['id'],True,training.review(root,record['id']))
    while run['status']!='complete':run=training.step(root,run['id'],True,run['revision'])
    evaluation=evaluations.evaluate(root,run['id'],True,run['revision'])
    preview=previews.preview(root,run['id'],True,run['revision'],'aaaa',12)
    return run,evaluation,preview


class StreamArchiveTests(unittest.TestCase):
    def test_consent_blocks_export_without_touching_a_trial(self):
        with self.assertRaises(ValueError):archives.review('/unused','a'*32,False,'r')
        with self.assertRaises(ValueError):archives.export('/unused','a'*32,False,'r',{})

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires genuine trained passing fixture')
    def test_passing_review_is_readonly_archive_has_exact_bundle_and_receipts(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);run,evaluation,preview=passing_fixture(root);self.assertTrue(evaluation['passed'])
            before={p:p.read_bytes() for p in root.rglob('*') if p.is_file()}
            review=archives.review(root,run['id'],True,run['revision'])
            self.assertEqual({p for p in root.rglob('*') if p.is_file()},set(before))
            with self.assertRaises(ValueError):archives.export(root,run['id'],True,run['revision'],{})
            result=archives.export(root,run['id'],True,run['revision'],review)
            data=base64.b64decode(result['data']);self.assertEqual(hashlib.sha256(data).hexdigest(),result['receipt']['archive_sha256'])
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                self.assertEqual(set(archive.namelist()),{'bundle/decoder.json','bundle/tokenizer.json','bundle/manifest.json','evaluation.json','preview.json','export-manifest.json'})
                envelope=json.loads(archive.read('export-manifest.json'));self.assertFalse(envelope['release_approved'])
                self.assertEqual(json.loads(archive.read('evaluation.json')),evaluation);self.assertEqual(json.loads(archive.read('preview.json')),preview)
                for name,sha in review['files'].items():self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),sha)
                dest=root/'reloaded';dest.mkdir()
                for name in ('decoder.json','tokenizer.json','manifest.json'):(dest/name).write_bytes(archive.read('bundle/'+name))
                model,tokenizer,manifest=decoder_bundle.load(dest)
                self.assertEqual(manifest['stages']['tokenization'],4);self.assertEqual(tokenizer.decode(tokenizer.encode('aaaa')),'aaaa')
            self.assertTrue(all(p.read_bytes()==data for p,data in before.items()))
            self.assertFalse(result['receipt']['release_approved'])

    @unittest.skipUnless(os.environ.get('ALMG_METAL_TESTS')=='1','Requires genuinely trained fixture')
    def test_failing_quality_and_missing_saved_receipts_cannot_export(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary);run=preview_tests.StreamPreviewTests().complete(root)
            with self.assertRaisesRegex(ValueError,'Save an independent'):archives.review(root,run['id'],True,run['revision'])
            evaluation=evaluations.evaluate(root,run['id'],True,run['revision']);self.assertFalse(evaluation['passed'])
            previews.preview(root,run['id'],True,run['revision'],'unique',4)
            with self.assertRaisesRegex(ValueError,'80%'):archives.review(root,run['id'],True,run['revision'])
            self.assertFalse((root/'decoder-stream-training-exports').exists())
