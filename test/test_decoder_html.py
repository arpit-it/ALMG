import base64
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from backend import decoder_html as html, decoder_datasets as datasets
from backend.run_manifest import digest


class LocalHtmlTests(unittest.TestCase):
    def inputs(self):
        bodies=['Orchard café &amp; fresh fruit harvest in the local garden.',
                'Distant stars and galaxies observed through a telescope at night.',
                'Ocean coral reefs and coastal waves shelter marine fish.']
        return [{'name':f'input-{i}.html','data':base64.b64encode((
            '<!doctype html><html><head><title>HEAD OMITTED</title><style>STYLE OMITTED</style></head>'
            '<body><script>SCRIPT OMITTED</script><!-- COMMENT OMITTED --><template>TEMPLATE OMITTED</template>'
            '<p hidden>HIDDEN OMITTED</p><div aria-hidden="true">ARIA OMITTED</div><noscript>NOSCRIPT OMITTED</noscript>'
            '<input hidden><img src="https://example.invalid/private.png"><p>'+body+'</p></body></html>').encode()).decode()}
            for i,body in enumerate(bodies)]

    def test_offline_extraction_review_and_dataset_export_keep_original_and_extracted_hashes(self):
        documents=self.inputs();review=html.review(documents)
        self.assertEqual(review['revision'],digest({k:v for k,v in review.items() if k!='revision'}))
        self.assertIn('Orchard café & fresh',review['sources'][0]['preview'])
        self.assertFalse(review['method']['network_access']);self.assertFalse(review['training_approved'])
        for source,document in zip(review['sources'],documents):
            raw=base64.b64decode(document['data']);self.assertEqual(source['original_source_sha256'],hashlib.sha256(raw).hexdigest())
            self.assertNotIn('OMITTED',source['preview'])
        with TemporaryDirectory() as temporary:
            root=Path(temporary);manifest=html.prepare(root,documents,True,review)
            self.assertEqual(datasets.read(root,manifest['id']),manifest)
            provenance=manifest['derivation']['extraction_provenance']
            self.assertEqual(provenance['revision'],digest({k:v for k,v in provenance.items() if k!='revision'}))
            self.assertEqual(provenance['review_revision'],review['revision'])
            for extracted,original in zip(manifest['sources'],sorted(provenance['sources'],key=lambda row:row['name'])):
                self.assertEqual(extracted['source_sha256'],original['extracted_source_sha256'])
            rows=(root/'decoder-datasets'/manifest['id']/'documents.jsonl').read_text()
            self.assertNotIn('OMITTED',rows);self.assertNotIn('<p>',rows)
            export=datasets.export_review(root,manifest['id'])
            archive=datasets.export_dataset(root,manifest['id'],True,export['revision'])
            self.assertGreater(archive['bytes'],0)
            self.assertFalse((root/'decoder-trials').exists())

    def test_consent_stale_bytes_and_implementation_review_reject_without_publication(self):
        documents=self.inputs();review=html.review(documents)
        with TemporaryDirectory() as temporary:
            with self.assertRaises(ValueError):html.prepare(temporary,documents,False,review)
            with self.assertRaises(ValueError):html.prepare(temporary,documents,True,dict(review,implementation_sha256='changed'))
            changed=[dict(document) for document in documents];changed[0]['data']=base64.b64encode(b'<p>Changed source</p>').decode()
            with self.assertRaises(ValueError):html.prepare(temporary,changed,True,review)
            self.assertFalse((Path(temporary)/'decoder-datasets').exists())

    def test_invalid_encoding_hidden_only_oversized_and_deep_inputs_reject(self):
        for data in (b'\xff',b'<script>only script</script>',b'<div>'*129+b'body'+b'</div>'*129,b'x'*65537):
            documents=self.inputs();documents[0]['data']=base64.b64encode(data).decode()
            with self.subTest(data=data[:30]),self.assertRaises(ValueError):html.review(documents)
        documents=self.inputs();documents[0]['name']='source.pdf'
        with self.assertRaises(ValueError):html.review(documents)
        with self.assertRaises(ValueError):html.review([])


if __name__=='__main__':unittest.main()
