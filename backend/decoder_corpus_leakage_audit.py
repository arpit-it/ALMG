"""Read-only exact token overlap diagnostics for reviewed corpus snapshots."""
from pathlib import Path
if __package__:
    from . import decoder_corpus_optimizer as training, decoder_corpus_evaluation as heldout
    from .run_manifest import digest, file_digest
else:
    import decoder_corpus_optimizer as training, decoder_corpus_evaluation as heldout
    from run_manifest import digest, file_digest

PROTOCOL={'format':'almg-corpus-overlap-protocol-v1','schema_version':1,
          'comparisons':[['validation','train'],['test','train'],['test','validation']],
          'exact_windows':'first_input_plus_active_target_prefix_without_padding',
          'span_tokens':4,'reference_deduplication':'exact_active_token_sequence',
          'examples_per_comparison':8,'ordering':'saved_query_then_first_unique_reference_window'}


def active_tokens(row):
    mask=row['target_mask'];count=sum(mask)
    if not count or mask != [1]*count+[0]*(len(mask)-count):
        raise ValueError('Overlap audit requires nonempty right-padded target masks.')
    return tuple(row['inputs'][:1]+row['targets'][:count])


def audit_pair(query, reference, tokenizer):
    unique={}
    for index,row in enumerate(reference):unique.setdefault(active_tokens(row),(index,row))
    examples=[];exact_count=0;shared_count=0;pair_count=0;short_count=0
    for query_index,row in enumerate(query):
        tokens=active_tokens(row);has_exact=False;has_shared=False
        if len(tokens)<PROTOCOL['span_tokens']:short_count+=1
        for other,(reference_index,reference_row) in unique.items():
            exact=tokens==other;span=None
            reference_spans={}
            for offset in range(len(other)-PROTOCOL['span_tokens']+1):
                reference_spans.setdefault(other[offset:offset+PROTOCOL['span_tokens']],offset)
            for offset in range(len(tokens)-PROTOCOL['span_tokens']+1):
                value=tokens[offset:offset+PROTOCOL['span_tokens']]
                if value in reference_spans:
                    span={'query_token_offset':offset,'reference_token_offset':reference_spans[value],
                          'token_ids':list(value),'text':tokenizer.decode(list(value))};break
            if span is not None:has_shared=True;pair_count+=1
            if exact:has_exact=True
            if (exact or span is not None) and len(examples)<PROTOCOL['examples_per_comparison']:
                examples.append({'query_window_index':query_index,'reference_window_index':reference_index,
                                 'query_document_sha256':row['document_sha256'],'reference_document_sha256':reference_row['document_sha256'],
                                 'query_window_document_offset':row['offset'],'reference_window_document_offset':reference_row['offset'],
                                 'exact_active_window_match':exact,'shared_span':span})
        exact_count+=has_exact;shared_count+=has_shared
    return {'query_windows':len(query),'reference_windows_including_mixing_copies':len(reference),
            'unique_reference_token_sequences':len(unique),'exact_duplicate_query_windows':exact_count,
            'shared_four_token_query_windows':shared_count,'shared_four_token_window_pairs':pair_count,
            'query_windows_shorter_than_four_tokens':short_count,'examples':examples,
            'overlap_detected':bool(exact_count or shared_count)}


def audit(root, identifier):
    saved=training.inputs.read(root,identifier);origin=saved['review']['source']
    initialized=training.hardware.initializations.read(root,origin['plan_id'],origin['initialization_id'])
    _,_,_,windows,tokenizer=training._source(root,initialized,saved)
    comparisons={f'{query}_against_{reference}':audit_pair(windows[query],windows[reference],tokenizer)
                 for query,reference in PROTOCOL['comparisons']}
    overlap=any(item['overlap_detected'] for item in comparisons.values())
    result={'format':'almg-corpus-leakage-audit-v1','schema_version':1,
            'protocol':dict(PROTOCOL,comparisons=[list(pair) for pair in PROTOCOL['comparisons']]),'protocol_revision':digest(PROTOCOL),
            'corpus_id':saved['id'],'corpus_revision':saved['revision'],'evaluation_data_binding':heldout.data_binding(saved),
            'comparisons':comparisons,'overlap_detected':overlap,'requires_overlap_review':overlap,
            'independent_evaluation_certified':False,'memorization_validated':False,
            'training_approved':False,'release_approved':False,
            'limitations':'Exact saved token windows and four-token spans only, within window boundaries. Padding is excluded and identical reference sequences are deduplicated, including training mixing copies. Short query windows can match exactly but cannot produce four-token-span evidence. Source hashes/offsets locate saved provenance; they do not prove document independence. No semantic/fuzzy/cross-window matching, external benchmark audit or model memorization test. No overlap does not certify independent evaluation. Findings do not mutate data, change training gates or approve training/release.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_leakage_audit.py','decoder_corpus_evaluation.py','decoder_corpus_inputs.py','decoder_corpus_optimizer.py','decoder_tokenizer.py')})}
    result['revision']=digest(result)
    return result
