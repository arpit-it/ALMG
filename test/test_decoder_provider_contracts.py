import unittest
from backend import decoder_provider_contracts as providers
from backend.run_manifest import digest


class ProviderContractTests(unittest.TestCase):
    def source(self):
        return dict(provider_id='local-fixture', adapter_version='1.0', source_id='document-1',
                    source_revision='immutable-v1', source_sha256='a'*64, source_bytes=4096,
                    permission_basis='user_permission', permission_notes='Synthetic fixture declared by its author.')

    def test_contract_is_versioned_optional_and_stable(self):
        spec=providers.contract()
        self.assertEqual(spec['revision'],digest({k:v for k,v in spec.items() if k!='revision'}))
        self.assertEqual(spec,providers.contract())
        self.assertEqual(spec['installed_adapters'],[])
        self.assertFalse(spec['collection_available'])
        self.assertEqual(spec['maximum_chunk_bytes'],65536)
        self.assertEqual(set(spec['operations']),{'review','collect','resume'})
        spec['installed_adapters'].append('changed')
        self.assertEqual(providers.contract()['installed_adapters'],[])

    def test_metadata_review_preserves_provenance_without_granting_permission(self):
        source=self.source();review=providers.validate_source(source)
        self.assertEqual(review['source'],source)
        self.assertEqual(review['contract_revision'],providers.contract()['revision'])
        self.assertFalse(review['collection_authorized'])
        self.assertFalse(review['permission_verified'])
        self.assertFalse(review['training_approved'])
        source['source_id']='mutated'
        self.assertEqual(review['source']['source_id'],'document-1')
        for field in ('adapter_version','source_revision','source_sha256','permission_notes'):
            changed=self.source();changed[field]='b'*64
            self.assertNotEqual(providers.validate_source(changed)['revision'],review['revision'])

    def test_bad_or_credential_bearing_metadata_fails_closed(self):
        for field,value in [('source_bytes',True),('source_bytes',0),('source_bytes',1024**4+1),
                            ('source_sha256','A'*64),('source_sha256','not-a-hash'),
                            ('permission_basis','unknown'),('permission_notes',''),('adapter_version',None),
                            ('source_id','x'*2049)]:
            source=self.source();source[field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):providers.validate_source(source)
        for key in ('api_key','authorization','unexpected'):
            source=self.source();source[key]='secret'
            with self.assertRaises(ValueError):providers.validate_source(source)
        missing=self.source();del missing['permission_notes']
        for source in (missing,[],None):
            with self.assertRaises(ValueError):providers.validate_source(source)


if __name__=='__main__':unittest.main()
