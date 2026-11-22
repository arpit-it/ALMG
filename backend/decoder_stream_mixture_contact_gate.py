"""Current full-source contact-pattern evidence layered on the lexical input gate."""
from pathlib import Path

if __package__:
    from . import decoder_stream_mixture_lexical_gate as lexical, decoder_stream_audits as audits
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixture_lexical_gate as lexical
    import decoder_stream_audits as audits
    from run_manifest import digest, file_digest


def _build(root, session_id, reviewed_lexical, selections):
    if not isinstance(reviewed_lexical, dict) or reviewed_lexical.get('session_id') != session_id:
        raise ValueError('Reopen this session lexical input gate review.')
    current = lexical.review(root, session_id, True, reviewed_lexical.get('input_review'), reviewed_lexical.get('evidence'))
    if current != reviewed_lexical:
        raise ValueError('Lexical evidence or input review changed before contact-pattern gating.')
    state = lexical.inputs.sessions.read(root, session_id)
    sources = lexical.inputs.sessions._bindings(root, state)['sources']
    if (not isinstance(selections, list) or len(selections) != len(sources)
            or any(not isinstance(value, dict) or set(value) != {'index_id', 'audit_id'}
                   or any(not isinstance(value[key], str) for key in ('index_id', 'audit_id')) for value in selections)):
        raise ValueError('Select one complete contact-pattern audit for every mixture source.')
    chosen = {value['index_id']: value['audit_id'] for value in selections}
    if len(chosen) != len(sources) or set(chosen) != {source['index_id'] for source in sources}:
        raise ValueError('Contact audit selection repeats, omits or substitutes a mixture source.')
    summaries = []
    for source in sources:
        report = audits.read(root, chosen[source['index_id']])
        expected = sum(source['split_counts'].values())
        method = report.get('method')
        if (report.get('status') != 'complete' or type(report.get('total_records')) is not int
                or type(report.get('processed_records')) is not int
                or report['total_records'] != expected or report['processed_records'] != expected):
            raise ValueError('Complete the matching full-source contact audit before gated input access.')
        if (not isinstance(method, dict) or type(method.get('version')) is not int or method['version'] != 1
                or method.get('population') != 'all_unique_normalized_records'
                or method.get('privacy') != 'local_contact_patterns_v1' or method.get('raw_text_included') is not False):
            raise ValueError('Contact audit method does not match the supported all-record pattern policy.')
        if (report.get('index_id') != source['index_id'] or report.get('index_revision') != source['index_revision']
                or report.get('index_file_sha256') != source['index_file_sha256']
                or report.get('source_id') != source['source_id'] or report.get('source_sha256') != source['source_sha256']
                or report.get('implementation_sha256') != audits._implementation()):
            raise ValueError('Contact audit source binding or producer changed; rerun the matching audit.')
        if (any(type(report.get(key)) is not int or report[key] < 0 for key in
                ('privacy_records', 'privacy_matches', 'privacy_match_occurrences', 'hygiene_review_records'))
                or report['privacy_records'] > expected or report['hygiene_review_records'] > expected
                or report['privacy_matches'] < report['privacy_records']
                or report['privacy_match_occurrences'] < report['privacy_matches']):
            raise ValueError('Contact audit coverage or counters are invalid.')
        if any(report[key] for key in ('privacy_records', 'privacy_matches', 'privacy_match_occurrences')):
            raise ValueError('Known source contact-pattern findings block these gated model inputs. Inspect the retained audit and prepare a newly reviewed source.')
        summaries.append({'index_id': source['index_id'], 'audit_id': report['id'], 'audit_revision': report['revision'],
                          'processed_records': report['processed_records'], 'privacy_records': 0, 'privacy_matches': 0,
                          'hygiene_review_records': report['hygiene_review_records']})
    canonical = [{'index_id': source['index_id'], 'audit_id': chosen[source['index_id']]} for source in sources]
    result = {'format': 'almg-stream-mixture-contact-input-gate-v1', 'schema_version': 1,
              'session_id': session_id, 'lexical_review': current, 'contact_audits': canonical, 'source_audits': summaries,
              'contact_pattern_gate_passed': True, 'lexical_cross_split_gate_passed': True,
              'hygiene_review_records': sum(value['hygiene_review_records'] for value in summaries),
              'hygiene_gate_applied': False,
              'method': {'version': 1, 'population': 'all_source_records_all_saved_splits',
                         'privacy': 'local_contact_patterns_v1', 'gate': 'zero_known_contact_matches',
                         'patterns': ['ascii_email', 'international_plus_phone', 'north_american_formatted_phone']},
              'implementation_sha256': digest({name: file_digest(Path(__file__).with_name(name)) for name in
                    ('decoder_stream_mixture_contact_gate.py', 'decoder_stream_mixture_lexical_gate.py',
                     'decoder_stream_audits.py', 'decoder_datasets.py')}),
              **{flag: False for flag in lexical.inputs.sessions.FLAGS},
              'scope': 'Complete matching source audits found zero of the configured contact patterns, including held-out records. This does not establish comprehensive PII, text-hygiene, semantic quality or legal permission clearance. Hygiene findings remain visible but are not cleared by this gate. Source declarations stay unverified and no model-training or release approval is granted. No source is filtered or rewritten.'}
    result['revision'] = digest(result)
    return result


@lexical.inputs._source_errors
def review(root, session_id, confirmed, reviewed_lexical, contact_audits):
    if confirmed is not True: raise ValueError('Confirm complete-source contact-pattern evidence review; training is not approved.')
    return _build(root, session_id, reviewed_lexical, contact_audits)


@lexical.inputs._source_errors
def batch(root, session_id, confirmed, reviewed, cursor=None, batch_size=4):
    if confirmed is not True: raise ValueError('Confirm contact-pattern-gated private input inspection.')
    if type(batch_size) is not int or not 1 <= batch_size <= 16: raise ValueError('Choose one to 16 causal windows.')
    if not isinstance(reviewed, dict): raise ValueError('Reopen the exact contact input gate review.')
    current = _build(root, session_id, reviewed.get('lexical_review'), reviewed.get('contact_audits'))
    if current != reviewed: raise ValueError('Contact evidence or the lexical input review changed.')
    inner = None
    if cursor is not None:
        if (not isinstance(cursor, dict) or set(cursor) != {'contact_gate_revision', 'lexical_cursor'}
                or cursor.get('contact_gate_revision') != current['revision'] or not isinstance(cursor.get('lexical_cursor'), dict)):
            raise ValueError('Contact-gated input cursor is invalid or stale.')
        inner = cursor['lexical_cursor']
    page = lexical.batch(root, session_id, True, current['lexical_review'], inner, batch_size)
    if _build(root, session_id, current['lexical_review'], current['contact_audits']) != current:
        raise ValueError('Contact audit evidence changed while reading inputs; discard this page.')
    return {**page, 'format': 'almg-stream-mixture-contact-gated-input-batch-v1',
            'contact_gate_revision': current['revision'], 'contact_pattern_gate_passed': True,
            'hygiene_gate_applied': False, 'hygiene_review_records': current['hygiene_review_records'],
            'next_cursor': {'contact_gate_revision': current['revision'], 'lexical_cursor': page['next_cursor']} if page['next_cursor'] is not None else None}
