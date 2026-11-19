"""Immutable local-text preparation for future decoder jobs; never starts training."""
import json
import hashlib
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid
import re
import math
import io
import zipfile
from collections import Counter
from statistics import median

if __package__:
    from .decoder_tokenizer import Tokenizer, ByteTokenizer
    from .run_manifest import digest, file_digest
else:
    from decoder_tokenizer import Tokenizer, ByteTokenizer
    from run_manifest import digest, file_digest


def prepare(root, documents, confirmed, tokenizer_kind="words", *, _derivation=None, _dataset_id=None):
    if not isinstance(tokenizer_kind, str) or tokenizer_kind not in ('words', 'utf8_bytes'):
        raise ValueError('Choose word or UTF-8 byte tokenization.')
    tokenizer_type = ByteTokenizer if tokenizer_kind == 'utf8_bytes' else Tokenizer
    if confirmed is not True:
        raise ValueError('Confirm local decoder dataset preparation first.')
    if not isinstance(documents, list) or not 3 <= len(documents) <= 16:
        raise ValueError('Select 3 to 16 local text documents.')
    sources, unique, findings = [], {}, []
    total_bytes = 0
    for document in documents:
        if not isinstance(document, dict):
            raise ValueError('Each document requires a name and UTF-8 text.')
        name = document.get('name')
        if 'data' in document:
            if not isinstance(document['data'], str) or len(document['data']) > 90000 or 'text' in document:
                raise ValueError('Provide bounded original UTF-8 bytes for each document.')
            encoded = base64.b64decode(document['data'], validate=True)
            text = encoded.decode('utf-8')
        else:
            text = document.get('text')
            if not isinstance(text, str):
                raise ValueError('Each document requires UTF-8 text or original bytes.')
            encoded = text.encode('utf-8')
        if not isinstance(name, str) or not 1 <= len(name) <= 255:
            raise ValueError('Each document requires a short source name.')
        if not isinstance(text, str) or any(ord(ch) < 32 and ch not in '\r\n\t' for ch in text):
            raise ValueError('Only plain UTF-8 text documents are supported.')
        total_bytes += len(encoded)
        if len(encoded) > 65536 or total_bytes > 128000:
            raise ValueError('Each document must fit 64 KiB; the selection must fit 128000 bytes.')
        normalized = ' '.join(Tokenizer.words(text.removeprefix('\ufeff')))
        group = digest(normalized)
        source_hash = hashlib.sha256(encoded).hexdigest()
        sources.append({'name': name, 'source_sha256': source_hash, 'utf8_bytes': len(encoded),
                        'normalized_sha256': group, 'license': 'user_provided_not_reviewed'})
        unique.setdefault(group, []).append({'name': name, 'text': normalized, 'source_sha256': source_hash})
    if len(unique) < 3:
        raise ValueError('Select at least three distinct documents for separate train, validation and test groups.')
    groups = sorted(unique)
    records = []
    for index, group in enumerate(groups):
        part = 'test' if index == 0 else ('validation' if index == 1 else 'train')
        candidates = sorted(unique[group], key=lambda row: (row['name'], row['source_sha256']))
        record = {**candidates[0], 'group': group, 'split': part}
        records.append(record)
        for duplicate in candidates[1:]:
            findings.append({'kind': 'duplicate_document', 'source': duplicate['name'],
                             'source_sha256': duplicate['source_sha256'], 'kept_source': record['name'],
                             'kept_source_sha256': record['source_sha256'], 'group': group})
        for source in sources:
            if source['normalized_sha256'] == group:
                source['split'] = part
    tokenizer = None
    try:
        tokenizer = tokenizer_type.fit([row['text'] for row in records if row['split'] == 'train'])
        for row in records:
            try:
                tokenizer.encode(row['text'])
            except ValueError:
                findings.append({'kind': 'out_of_training_vocabulary', 'source': row['name'], 'split': row['split']})
    except ValueError as error:
        findings.append({'kind': 'tokenizer_limits', 'message': str(error)})
    directory = Path(root) / 'decoder-datasets'
    directory.mkdir(parents=True, exist_ok=True)
    dataset_id = _dataset_id or uuid.uuid4().hex
    if not isinstance(dataset_id, str) or not re.fullmatch('[a-f0-9]{32}', dataset_id):
        raise ValueError('Invalid decoder dataset ID.')
    sources.sort(key=lambda source: (source['name'], source['source_sha256']))
    manifest = {'format': 'almg-decoder-text-dataset-v1', 'schema_version': 1, 'id': dataset_id,
                'status': 'prepared_for_review', 'preparation_version': 1,
                'input_documents': len(documents), 'unique_documents': len(records),
                'dataset_sha256': digest(records), 'sources': sources, 'findings': findings,
                'splits': {part: sum(row['split'] == part for row in records) for part in ('train', 'validation', 'test')},
                'tokenizer': None if tokenizer is None else {'format': tokenizer.artifact()['format'],
                    'sha256': tokenizer.fingerprint(), 'fit_source': 'training_documents_only',
                    'vocabulary_size': len(tokenizer.vocabulary)}}
    if _derivation is not None:
        manifest['derivation'] = _derivation
    with TemporaryDirectory(prefix='.prepare-', dir=directory) as temporary:
        staged = Path(temporary) / 'dataset'
        staged.mkdir()
        (staged / 'documents.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records), encoding='utf-8')
        if tokenizer is not None:
            (staged / 'tokenizer.json').write_text(json.dumps(tokenizer.artifact(), ensure_ascii=False), encoding='utf-8')
        manifest['files'] = {path.name: file_digest(path) for path in staged.iterdir()}
        (staged / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        staged.rename(directory / dataset_id)
    return manifest


def read(root, dataset_id):
    import re
    if not isinstance(dataset_id, str) or not re.fullmatch('[a-f0-9]{32}', dataset_id):
        raise ValueError('Invalid decoder dataset ID.')
    folder = Path(root) / 'decoder-datasets' / dataset_id
    try:
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        if (manifest.get('format') != 'almg-decoder-text-dataset-v1'
                or type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1
                or manifest.get('id') != dataset_id or not isinstance(manifest.get('files'), dict)
                or set(manifest['files']) not in ({'documents.jsonl'}, {'documents.jsonl', 'tokenizer.json'})):
            raise ValueError('Unsupported decoder dataset manifest.')
        for name, expected in manifest['files'].items():
            if file_digest(folder / name) != expected:
                raise ValueError('Decoder dataset file hash mismatch.')
        records = [json.loads(line) for line in (folder / 'documents.jsonl').read_text(encoding='utf-8').splitlines()]
        if digest(records) != manifest['dataset_sha256']:
            raise ValueError('Decoder dataset content revision does not match.')
        if (len(records) != manifest['unique_documents']
                or len({row['group'] for row in records}) != len(records)
                or manifest['splits'] != {part: sum(row['split'] == part for row in records) for part in ('train', 'validation', 'test')}):
            raise ValueError('Decoder dataset partition metadata does not match its content.')
        if 'tokenizer.json' in manifest['files']:
            tokenizer = Tokenizer.restore(json.loads((folder / 'tokenizer.json').read_text(encoding='utf-8')))
            fitted = type(tokenizer).fit([row['text'] for row in records if row['split'] == 'train'])
            if (tokenizer.artifact()['format'] != manifest['tokenizer']['format']
                    or tokenizer.fingerprint() != manifest['tokenizer']['sha256'] or tokenizer.fingerprint() != fitted.fingerprint()):
                raise ValueError('Decoder tokenizer does not match the training partition.')
        return manifest
    except (OSError, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Decoder dataset is unavailable or incomplete.') from error


def list_datasets(root):
    directory = Path(root) / 'decoder-datasets'
    manifests = []
    if directory.exists():
        for folder in directory.iterdir():
            if not folder.name.startswith('.'):
                try:
                    manifests.append(read(root, folder.name))
                except ValueError:
                    continue
    return {'datasets': manifests[-20:]}


# Deliberately conservative local heuristics, not a guarantee of PII-free text.
_PRIVACY_PATTERNS = (
    ('email_address', re.compile(r"(?<![\w.+-])[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]*[A-Z0-9])?)+", re.IGNORECASE | re.ASCII)),
    ('phone_number', re.compile(r"(?<!\w)\+[1-9][0-9(). -]{6,24}[0-9](?!\w)|(?<![\w+])(?:\([0-9]{3}\)|[0-9]{3})[-. ][0-9]{3}[-. ][0-9]{4}(?!\w)", re.ASCII)),
)


def _privacy_findings(text, source):
    findings = []
    for category, pattern in _PRIVACY_PATTERNS:
        for match in pattern.finditer(text):
            if category == 'phone_number' and not 8 <= sum(char.isdigit() for char in match.group()) <= 15:
                continue
            findings.append({'kind': 'potential_personal_information', 'category': category,
                             'record': source, 'normalized_character_start': match.start(),
                             'normalized_character_end': match.end()})
    return sorted(findings, key=lambda row: (row['normalized_character_start'], row['category']))


def _token_distribution(folder, manifest, records):
    method = {'version': 1, 'source': 'saved_tokenizer_without_refitting',
              'token_text_included': False, 'entropy_population': 'known_tokens_only'}
    if manifest['tokenizer'] is None:
        return {**method, 'available': False, 'reason': 'No valid saved tokenizer; resolve tokenizer findings first.'}
    tokenizer = Tokenizer.restore(json.loads((folder / 'tokenizer.json').read_text(encoding='utf-8')))
    vocabulary = {word: index for index, word in enumerate(tokenizer.vocabulary)}
    split_tokens = {part: [] for part in ('train', 'validation', 'test')}
    split_lengths = {part: [] for part in split_tokens}
    for row in records:
        if isinstance(tokenizer, ByteTokenizer):
            try:
                tokens = tokenizer.encode(row['text'])
            except ValueError:
                return {**method, 'available': False, 'reason': 'A document exceeds saved tokenizer encoding limits.',
                        'record': {key: row[key] for key in ('name', 'source_sha256', 'group', 'split')}}
        else:
            # Keep unknown occurrences explicit; never learn vocabulary from evaluation data.
            tokens = [vocabulary.get(word) for word in Tokenizer.words(row['text'])]
        split_tokens[row['split']].extend(tokens)
        split_lengths[row['split']].append(len(tokens))

    def summarize(tokens, lengths):
        counts = Counter(token for token in tokens if token is not None)
        known = sum(counts.values())
        return {'documents': len(lengths), 'token_count': len(tokens), 'known_tokens': known,
                'unknown_tokens': len(tokens) - known, 'observed_vocabulary': len(counts),
                'known_token_coverage': round(known / len(tokens), 6) if tokens else 0.0,
                'entropy_bits': round(-sum((count / known) * math.log2(count / known) for count in counts.values()), 6),
                'document_tokens': {'minimum': min(lengths), 'maximum': max(lengths),
                                    'mean': round(sum(lengths) / len(lengths), 6), 'median': median(lengths)},
                'top_token_ids': [{'token_id': token, 'count': count} for token, count in
                                  sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]]}
    return {**method, 'available': True, 'tokenizer_sha256': tokenizer.fingerprint(),
            'tokenizer_format': tokenizer.artifact()['format'], 'vocabulary_size': len(tokenizer.vocabulary),
            'overall': summarize([token for tokens in split_tokens.values() for token in tokens],
                                 [length for lengths in split_lengths.values() for length in lengths]),
            'splits': {part: summarize(split_tokens[part], split_lengths[part]) for part in split_tokens}}


def quality_report(root, dataset_id):
    """Compute overlap findings from verified data without changing stored artifacts."""
    manifest = read(root, dataset_id)
    records = [json.loads(line) for line in (Path(root)/'decoder-datasets'/dataset_id/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    summaries, shingles, findings = [], [], []
    for record in records:
        words = Tokenizer.words(record['text'])
        source = {'name':record['name'], 'source_sha256':record['source_sha256'],
                  'group':record['group'], 'split':record['split']}
        findings.extend(_privacy_findings(record['text'], source))
        license_status = next((item.get('license','unknown') for item in manifest['sources']
                               if item['source_sha256']==record['source_sha256']), 'unknown')
        summaries.append({**source,'word_count':len(words),'distinct_words':len(set(words)), 'license':license_status})
        shingles.append({tuple(words[i:i+5]) for i in range(len(words)-4)} if len(words)>=12 else set())
        if len(words)<12:
            findings.append({'kind':'short_document', 'record':source, 'minimum_words_for_overlap_check':12})
    near_count = cross_count = 0
    for left in range(len(records)):
        for right in range(left+1,len(records)):
            if not shingles[left] or not shingles[right]:
                continue
            similarity = len(shingles[left]&shingles[right])/len(shingles[left]|shingles[right])
            if similarity < .8:
                continue
            cross_split = records[left]['split'] != records[right]['split']
            near_count += 1
            cross_count += int(cross_split)
            affected = [{key:records[index][key] for key in ('name','source_sha256','group','split')} for index in (left,right)]
            findings.append({'kind':'potential_evaluation_contamination' if cross_split else 'near_duplicate_documents',
                             'records':affected, 'similarity':round(similarity,6), 'cross_split':cross_split})
    report = {'schema_version':1,'format':'almg-decoder-data-audit-v1','audit_version':3,
              'dataset_id':dataset_id,'dataset_manifest_sha256':digest(manifest),'dataset_sha256':manifest['dataset_sha256'],
              'method':{'name':'word_shingle_jaccard','version':1,'shingle_words':5,'minimum_words':12,'threshold':.8},
              'privacy_method':{'name':'local_contact_patterns','version':1,
                  'scope':['ascii_email','international_plus_phone','north_american_formatted_phone'],
                  'offsets':'normalized_text_unicode_codepoints','matched_values_included':False,
                  'limitations':'Heuristic review only; other personal information and unrecognized formats may remain.'},
              'token_distribution':_token_distribution(Path(root)/'decoder-datasets'/dataset_id, manifest, records),
              'privacy_matches':sum(row['kind']=='potential_personal_information' for row in findings),
              'policy':'report_only_preserve_existing_approvals', 'records':summaries,'findings':findings,
              'near_duplicate_pairs':near_count,'cross_split_pairs':cross_count,
              'implementation_sha256':file_digest(Path(__file__))}
    report['revision'] = digest(report)
    return report


def audit(root, dataset_id, confirmed):
    """Save a deterministic report-only near-duplicate/partition-overlap audit."""
    if confirmed is not True:
        raise ValueError('Confirm the local dataset quality audit.')
    report = quality_report(root, dataset_id)
    directory = Path(root)/'decoder-dataset-audits'/dataset_id
    directory.mkdir(parents=True,exist_ok=True)
    destination = directory/(report['revision']+'.json')
    if destination.exists():
        if json.loads(destination.read_text(encoding='utf-8')) != report:
            raise ValueError('Saved dataset audit revision does not match its content.')
        return report
    temporary = directory/(uuid.uuid4().hex+'.tmp')
    try:
        temporary.write_text(json.dumps(report,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    return report


def list_audits(root, dataset_id):
    manifest = read(root,dataset_id)
    directory = Path(root)/'decoder-dataset-audits'/dataset_id
    result = []
    for path in sorted(directory.glob('*.json')) if directory.exists() else []:
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
            payload = {key:value for key,value in report.items() if key!='revision'}
            if (report.get('format')!='almg-decoder-data-audit-v1' or type(report.get('audit_version')) is not int
                    or report['audit_version'] not in (1, 2, 3) or report.get('dataset_id')!=dataset_id
                    or report.get('dataset_manifest_sha256')!=digest(manifest)
                    or report.get('revision')!=digest(payload) or path.stem!=report['revision']):
                continue
            result.append(report)
        except (OSError,ValueError,TypeError,AttributeError):
            continue
    return result[-20:]


def redact(root, dataset_id, confirmed, audit_revision):
    """Create a separately reviewed version; original data and approvals are immutable."""
    if confirmed is not True:
        raise ValueError('Confirm creation of a redacted dataset version.')
    report = quality_report(root, dataset_id)
    if not isinstance(audit_revision, str) or audit_revision != report['revision']:
        raise ValueError('The privacy audit changed. Reopen the current audit before filtering.')
    if not report['privacy_matches']:
        raise ValueError('No detected contact details to replace in this dataset.')
    parent = read(root, dataset_id)
    rows = [json.loads(line) for line in (Path(root)/'decoder-datasets'/dataset_id/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    documents, lineage = [], []
    for row in rows:
        matches = [finding for finding in report['findings']
                   if finding['kind'] == 'potential_personal_information'
                   and finding['record']['group'] == row['group']]
        text = row['text']
        # Merge overlapping detections before replacement so offsets remain valid.
        spans = []
        for match in sorted(matches, key=lambda item: item['normalized_character_start']):
            start, end = match['normalized_character_start'], match['normalized_character_end']
            if spans and start < spans[-1][1]:
                spans[-1] = (spans[-1][0], max(spans[-1][1], end))
            else:
                spans.append((start, end))
        for start, end in reversed(spans):
            text = text[:start] + '[CONTACT_REDACTED]' + text[end:]
        documents.append({'name': row['name'], 'text': text})
        lineage.append({'name': row['name'], 'derived_source_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
                        'parent_group': row['group'], 'parent_split': row['split'],
                        'parent_sources': [source for source in parent['sources'] if source['normalized_sha256'] == row['group']],
                        'replacements': len(spans)})
    derivation = {'version': 1, 'operation': 'replace_detected_contacts',
                  'parent_dataset_id': dataset_id, 'parent_manifest_sha256': digest(parent),
                  'audit_revision': report['revision'], 'privacy_method': report['privacy_method'],
                  'replacement': '[CONTACT_REDACTED]', 'partition_policy': 'recompute_groups_and_splits_require_new_review',
                  'sources': lineage}
    tokenizer_kind = 'utf8_bytes' if (parent.get('tokenizer') or {}).get('format') == 'almg-utf8-byte-tokenizer-v1' else 'words'
    return prepare(root, documents, True, tokenizer_kind, _derivation=derivation)


def _export_payload(root, dataset_id):
    manifest = read(root, dataset_id)
    folder = Path(root) / 'decoder-datasets' / dataset_id
    limits = {'manifest.json': 1024 * 1024, 'documents.jsonl': 256 * 1024, 'tokenizer.json': 128 * 1024}
    payload = {}
    for name in sorted({'manifest.json', *manifest['files']}):
        with (folder / name).open('rb') as source:
            data = source.read(limits[name] + 1)
        if len(data) > limits[name]:
            raise ValueError('The prepared dataset exceeds the bounded local export size.')
        if name == 'manifest.json':
            if json.loads(data) != manifest:
                raise ValueError('The dataset manifest changed during export review.')
        elif hashlib.sha256(data).hexdigest() != manifest['files'][name]:
            raise ValueError('The dataset changed during export review.')
        payload[name] = data
    review = {'format': 'almg-decoder-dataset-export-v1', 'schema_version': 1,
              'dataset_id': dataset_id, 'dataset_manifest_sha256': digest(manifest),
              'scope': 'private_local_dataset', 'includes_normalized_text': True,
              'includes_source_provenance_and_derivation': True, 'includes_training_approvals': False,
              'files': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
                        for name, data in payload.items()},
              'implementation_sha256': file_digest(Path(__file__))}
    review['revision'] = digest(review)
    return review, payload


def export_review(root, dataset_id):
    return _export_payload(root, dataset_id)[0]


def export_dataset(root, dataset_id, confirmed, revision):
    if confirmed is not True:
        raise ValueError('Confirm the private local dataset export first.')
    review, payload = _export_payload(root, dataset_id)
    if not isinstance(revision, str) or revision != review['revision']:
        raise ValueError('The dataset export review changed. Reopen the current review before saving.')
    payload['dataset-export.json'] = json.dumps(review, ensure_ascii=False, allow_nan=False,
                                               sort_keys=True, indent=2).encode('utf-8')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_STORED) as archive:
        for name, data in sorted(payload.items()):
            entry = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            entry.external_attr = 0o100600 << 16
            archive.writestr(entry, data)
    data = buffer.getvalue()
    return {'file_name': f'decoder-dataset-{dataset_id[:8]}.zip',
            'data': base64.b64encode(data).decode('ascii'), 'sha256': hashlib.sha256(data).hexdigest(),
            'bytes': len(data), 'revision': review['revision']}


def extend_dataset(root, dataset_id, confirmed, reviewed, documents):
    """Append approved local inputs into a new immutable, independently reviewed version."""
    if confirmed is not True:
        raise ValueError('Confirm adding local documents to a new dataset version.')
    parent = read(root, dataset_id)
    if not isinstance(reviewed, dict) or digest(reviewed) != digest(parent):
        raise ValueError('The parent dataset review changed. Reopen it before adding documents.')
    if not isinstance(documents, list) or not documents:
        raise ValueError('Select at least one additional local text document.')
    rows = [json.loads(line) for line in (Path(root)/'decoder-datasets'/dataset_id/'documents.jsonl').read_text(encoding='utf-8').splitlines()]
    if len(rows) + len(documents) > 16:
        raise ValueError('The combined dataset supports at most 16 local documents. Prepare a separate dataset.')
    inherited = [{'name': row['name'], 'text': row['text']} for row in rows]
    derivation = {'version': 1, 'operation': 'append_local_documents',
                  'parent_dataset_id': dataset_id, 'parent_manifest_sha256': digest(parent),
                  'added_input_documents': len(documents),
                  'partition_policy': 'recompute_groups_and_splits_require_new_review',
                  'sources': [{'name': row['name'],
                               'derived_source_sha256': hashlib.sha256(row['text'].encode('utf-8')).hexdigest(),
                               'parent_group': row['group'], 'parent_split': row['split'],
                               'parent_sources': [source for source in parent['sources'] if source['normalized_sha256'] == row['group']]}
                              for row in rows]}
    tokenizer_kind = 'utf8_bytes' if (parent.get('tokenizer') or {}).get('format') == 'almg-utf8-byte-tokenizer-v1' else 'words'
    return prepare(root, inherited + documents, True, tokenizer_kind, _derivation=derivation)
