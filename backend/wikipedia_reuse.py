"""Explicit reuse review for displayed Wikipedia search excerpts."""
import hashlib
import json
import time
import unicodedata
from urllib.parse import quote, unquote, urlsplit

TERMS_REFERENCE = 'https://foundation.wikimedia.org/wiki/Policy:Terms_of_Use#7._Licensing_of_Content'


def excerpt_checksum(record):
    source, text, title = record.get('source'), record.get('text'), record.get('title', '')
    if not isinstance(source, str):
        raise ValueError('Review a listed Wikipedia excerpt first.')
    parsed = urlsplit(source)
    page = unquote(parsed.path.removeprefix('/wiki/'), errors='strict')
    if (record.get('provider') != 'wikipedia' or parsed.scheme != 'https' or parsed.netloc != 'en.wikipedia.org'
            or not parsed.path.startswith('/wiki/') or not page or page.strip(' _') in {'.', '..'}
            or source != 'https://en.wikipedia.org/wiki/' + quote(page, safe='')
            or not isinstance(text, str) or not 40 <= len(text) <= 450 or not isinstance(title, str) or len(title) > 255
            or any(unicodedata.category(c) in {'Cc', 'Cs'} for c in page + text + title)):
        raise ValueError('Review a valid listed Wikipedia excerpt first.')
    return hashlib.sha256(json.dumps({'source': source, 'title': title, 'text': text}, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()


def excerpt_reuse_evidence(record, decision):
    basis = decision.get('permission_basis')
    if (decision.get('confirmed') is not True or decision.get('approved_url') != record.get('source')
            or decision.get('approved_scope') != 'wikipedia_excerpt'
            or not isinstance(basis, str) or not 10 <= len(basis.strip()) <= 2000):
        raise ValueError('Record permission for the displayed Wikipedia excerpt first.')
    return {'source': record['source'], 'scope': 'wikipedia_excerpt', 'permission_basis': basis.strip(),
            'excerpt_sha256': excerpt_checksum(record), 'terms_reference': TERMS_REFERENCE, 'time': time.time()}


def approved_excerpt_rows(records, urls):
    if (not isinstance(urls, list) or not urls or any(not isinstance(url, str) for url in urls)
            or len(set(urls)) != len(urls)):
        raise ValueError('Select listed reuse-approved excerpt URLs first.')
    rows = [record for record in records if record.get('source') in urls]
    if len(rows) != len(urls):
        raise ValueError('Select only listed Wikipedia excerpts.')
    for record in rows:
        approval = record.get('reuse_approval')
        if (record.get('reuse_status') != 'user_approved' or not isinstance(approval, dict)
                or approval.get('source') != record.get('source') or approval.get('scope') != 'wikipedia_excerpt'
                or approval.get('excerpt_sha256') != excerpt_checksum(record)):
            raise ValueError('Record current reuse permission for each selected Wikipedia excerpt first.')
    return [{**record, 'collection_scope': 'wikipedia_excerpt'} for record in rows]
