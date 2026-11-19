"""Optional provider boundary only: no adapters, credentials, network or ingestion."""
import re

if __package__:
    from .run_manifest import digest
else:
    from run_manifest import digest


def contract():
    record = {
        'format': 'almg-dataset-provider-contract-v1', 'schema_version': 1,
        'installed_adapters': [], 'collection_available': False,
        'optional_provider_examples': ['ADAP'],
        'dependency_policy': 'Optional adapters must declare their own versions and dependencies; none are installed.',
        'operations': {
            'review': 'Return source identities, permission declarations, byte counts and hashes before collection.',
            'collect': 'Require current app consent bound to the exact reviewed source and provider revision.',
            'resume': 'Bind an opaque cursor to provider version, source hash, consent revision and committed byte offset.',
        },
        'source_fields': ['provider_id', 'adapter_version', 'source_id', 'source_revision',
                          'source_sha256', 'source_bytes', 'permission_basis', 'permission_notes'],
        'permission_bases': ['public_domain', 'licensed', 'user_permission'],
        'maximum_chunk_bytes': 65536,
        'requirements': [
            'Use existing app collection consent and source restrictions; never treat a provider declaration as consent.',
            'Keep credentials outside manifests, logs, exported datasets and Git.',
            'Preserve original source identity, revision, hash and permission declarations through preprocessing and export.',
            'Use bounded transfers, exact committed offsets and full final hash verification before publication.',
            'Invalidate resume when provider version, source revision, source hash or consent changes.',
        ],
        'limitations': 'Contract only. No ADAP integration, external collection, permission verification or training approval is enabled.',
    }
    return {**record, 'revision': digest(record)}


def validate_source(value):
    """Validate an adapter's local review metadata, without authorizing collection."""
    spec = contract()
    if not isinstance(value, dict) or set(value) != set(spec['source_fields']):
        raise ValueError('Provider review must contain exactly the versioned source fields; credentials are not accepted.')
    for key in ('provider_id', 'adapter_version', 'source_id', 'source_revision', 'permission_notes'):
        if not isinstance(value[key], str) or not value[key].strip() or len(value[key]) > 2048:
            raise ValueError(f'Provider review requires a bounded nonempty {key}.')
    if not isinstance(value['source_sha256'], str) or not re.fullmatch('[0-9a-f]{64}', value['source_sha256']):
        raise ValueError('Provider source requires a lowercase SHA-256 hash.')
    if type(value['source_bytes']) is not int or not 1 <= value['source_bytes'] <= 1024**4:
        raise ValueError('Provider source byte count must be a positive integer up to 1 TiB.')
    if value['permission_basis'] not in spec['permission_bases']:
        raise ValueError('Declare a supported source permission basis before review.')
    return {'format': 'almg-provider-source-review-v1', 'schema_version': 1,
            'contract_revision': spec['revision'], 'source': dict(value),
            'revision': digest(value), 'collection_authorized': False,
            'permission_verified': False, 'training_approved': False}
