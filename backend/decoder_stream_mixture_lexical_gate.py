"""Evidence-bound lexical cross-split gate for candidate mixed model inputs."""
from itertools import combinations
from pathlib import Path

if __package__:
    from . import decoder_stream_mixture_inputs as inputs, decoder_stream_overlap as within
    from . import decoder_stream_mixture_near_overlap as near, decoder_stream_mixture_audits as exact
    from .run_manifest import digest, file_digest
else:
    import decoder_stream_mixture_inputs as inputs
    import decoder_stream_overlap as within
    import decoder_stream_mixture_near_overlap as near
    import decoder_stream_mixture_audits as exact
    from run_manifest import digest, file_digest


def _method(report, cross=False):
    method = report.get('method')
    if (not isinstance(method, dict) or type(method.get('version')) is not int or method['version'] != 1
            or any(method.get(key) != value for key, value in
                   {'name': 'word_shingle_jaccard', 'shingle_words': 5, 'minimum_words': 12, 'threshold': .8}.items())
            or cross and any(method.get(key) is not value for key, value in
                             {'all_saved_splits': True, 'source_weights_applied': False, 'source_occurrences_expanded': False}.items())):
        raise ValueError('Lexical audit method does not match the supported complete-source policy.')


def _coverage(report, total):
    if (report.get('status') != 'complete' or type(report.get('total_pairs')) is not int
            or type(report.get('processed_pairs')) is not int
            or report['total_pairs'] != total or report['processed_pairs'] != total
            or type(report.get('short_pairs_skipped')) is not int or not 0 <= report['short_pairs_skipped'] <= total
            or type(report.get('cross_split_pairs')) is not int or not 0 <= report['cross_split_pairs'] <= total):
        raise ValueError('Complete the matching full-population lexical audit before gated input access.')


def _build(root, session_id, reviewed_input, evidence):
    if not isinstance(reviewed_input, dict) or reviewed_input.get('session_id') != session_id:
        raise ValueError('Reopen this session receipt input review.')
    current_input = inputs.review(root, session_id, True, reviewed_input.get('sequence'),
        reviewed_input.get('receipt'), reviewed_input.get('tokenizer', {}).get('id'), reviewed_input.get('tokenizer'))
    if current_input != reviewed_input:
        raise ValueError('Receipt input review changed before lexical gating.')
    if current_input['total_target_tokens'] <= 0:
        raise ValueError('The receipt has no causal targets; no gated model inputs are available.')
    state = inputs.sessions.read(root, session_id)
    view = inputs.sessions._bindings(root, state)
    plan = inputs.sessions.sampling.mixtures.read(root, view['mixture_id'])
    sources = plan['review']['sources']
    if any(not all(source['split_counts'].values()) for source in sources):
        raise ValueError('Every source needs nonempty train, validation and test splits for this lexical gate.')
    if (not isinstance(evidence, dict) or set(evidence) != {'source_audits', 'exact_audit_id', 'near_audit_id'}
            or not isinstance(evidence['source_audits'], list) or len(evidence['source_audits']) != len(sources)
            or any(not isinstance(value, dict) or set(value) != {'index_id', 'audit_id'} for value in evidence['source_audits'])):
        raise ValueError('Select exactly one within-source audit per source and matching exact/near mixture audits.')
    selected = {value['index_id']: value['audit_id'] for value in evidence['source_audits']}
    if len(selected) != len(sources) or set(selected) != {source['index_id'] for source in sources}:
        raise ValueError('Lexical source-audit selection is incomplete, duplicated or belongs to another mixture.')
    source_reports = []
    short_pairs = 0
    counts = []
    for source in sources:
        report = within.read(root, selected[source['index_id']])
        count = sum(source['split_counts'].values());counts.append(count)
        _method(report);_coverage(report, count * (count - 1) // 2)
        if (report.get('index_id') != source['index_id'] or report.get('index_revision') != source['index_revision']
                or report.get('index_file_sha256') != source['index_file_sha256']
                or report.get('source_sha256') != source['source_sha256'] or report.get('total_records') != count
                or report.get('implementation_sha256') != within._implementation()):
            raise ValueError('Within-source audit binding or producer changed; rerun the matching audit.')
        if report['cross_split_pairs']:
            raise ValueError('Within-source cross-split lexical findings block gated model inputs. Inspect the retained audit.')
        short_pairs += report['short_pairs_skipped']
        source_reports.append({'index_id': source['index_id'], 'audit_id': report['id'], 'audit_revision': report['revision'],
                               'processed_pairs': report['processed_pairs'], 'short_pairs_skipped': report['short_pairs_skipped']})
    exact_saved = exact.read(root, plan['id'], evidence['exact_audit_id'])
    exact_live = exact.overlap.review(root, plan['id'], True, plan)
    if exact_saved['report'] != exact_live:
        raise ValueError('The saved exact-overlap producer/report changed. Reinspect and save a current exact audit.')
    if exact_live['cross_split_record_pairs']:
        raise ValueError('Cross-source exact split conflicts block gated model inputs. Inspect the retained exact audit.')
    cross = near.read(root, evidence['near_audit_id'])
    pairs = list(combinations(range(len(sources)), 2))
    _method(cross, True);_coverage(cross, sum(counts[a] * counts[b] for a, b in pairs))
    if (cross.get('mixture_id') != plan['id'] or cross.get('mixture_revision') != plan['revision']
            or cross.get('sources') != sources or cross.get('source_pair_count') != len(pairs)
            or cross.get('implementation_sha256') != near._implementation()):
        raise ValueError('Cross-source near-overlap audit binding or producer changed; rerun the matching audit.')
    if cross['cross_split_pairs']:
        raise ValueError('Cross-source near-duplicate split findings block gated model inputs. Inspect the retained near audit.')
    short_pairs += cross['short_pairs_skipped']
    canonical = {'source_audits': [{'index_id': source['index_id'], 'audit_id': selected[source['index_id']]} for source in sources],
                 'exact_audit_id': evidence['exact_audit_id'], 'near_audit_id': evidence['near_audit_id']}
    result = {'format': 'almg-stream-mixture-lexical-input-gate-v1', 'schema_version': 1,
              'session_id': session_id, 'mixture_id': plan['id'], 'mixture_revision': plan['revision'],
              'input_review': current_input, 'evidence': canonical, 'source_audits': source_reports,
              'exact_audit': {'id': exact_saved['id'], 'revision': exact_saved['revision'], 'report_revision': exact_live['revision'],
                              'exact_overlap_record_pairs': exact_live['exact_overlap_record_pairs'], 'cross_split_record_pairs': 0},
              'near_audit': {'id': cross['id'], 'revision': cross['revision'], 'processed_pairs': cross['processed_pairs'],
                            'near_duplicate_pairs': cross['near_duplicate_pairs'], 'cross_split_pairs': 0},
              'short_record_pairs_unassessed': short_pairs, 'lexical_cross_split_gate_passed': True,
              'implementation_sha256': digest({name: file_digest(Path(__file__).with_name(name)) for name in
                    ('decoder_stream_mixture_lexical_gate.py', 'decoder_stream_mixture_inputs.py', 'decoder_stream_overlap.py',
                     'decoder_stream_mixture_near_overlap.py', 'decoder_stream_mixture_audits.py', 'decoder_stream_mixture_overlap.py')}),
              **{flag: False for flag in inputs.sessions.FLAGS},
              'scope': 'Complete matching within-source and cross-source lexical audits found zero cross-split findings at the recorded methods. Same-split duplicates are retained; short pairs remain unassessed and are counted. This is neither semantic/PII clearance nor verified permission or model-training approval. Inputs remain read-only candidates; all sources require retained evaluation splits.'}
    result['revision'] = digest(result)
    return result


@inputs._source_errors
def review(root, session_id, confirmed, reviewed_input, evidence):
    if confirmed is not True: raise ValueError('Confirm source-wide lexical evidence review; no training is approved.')
    return _build(root, session_id, reviewed_input, evidence)


@inputs._source_errors
def batch(root, session_id, confirmed, reviewed, cursor=None, batch_size=4):
    if confirmed is not True: raise ValueError('Confirm gated private input inspection; no training is approved.')
    if type(batch_size) is not int or not 1 <= batch_size <= 16: raise ValueError('Choose one to 16 causal windows.')
    if not isinstance(reviewed, dict): raise ValueError('Reopen the exact lexical input gate review.')
    current = _build(root, session_id, reviewed.get('input_review'), reviewed.get('evidence'))
    if current != reviewed: raise ValueError('Lexical evidence or input review changed. Reopen the gate review.')
    inner = None
    if cursor is not None:
        if (not isinstance(cursor, dict) or set(cursor) != {'gate_revision', 'input_cursor'}
                or cursor.get('gate_revision') != current['revision'] or not isinstance(cursor.get('input_cursor'), dict)):
            raise ValueError('Lexical-gated input cursor is invalid or stale.')
        inner = cursor['input_cursor']
    page = inputs.batch(root, session_id, True, current['input_review'], inner, batch_size)
    if _build(root, session_id, current['input_review'], current['evidence']) != current:
        raise ValueError('Lexical evidence changed while reading inputs; discard this batch.')
    return {**page, 'format': 'almg-stream-mixture-lexical-gated-input-batch-v1',
            'lexical_gate_revision': current['revision'], 'lexical_cross_split_gate_passed': True,
            'short_record_pairs_unassessed': current['short_record_pairs_unassessed'],
            'next_cursor': {'gate_revision': current['revision'], 'input_cursor': page['next_cursor']} if page['next_cursor'] is not None else None}
