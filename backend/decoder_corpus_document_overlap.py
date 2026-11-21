"""Read-only document-stream overlap checks, including saved-window boundaries."""
import json
from pathlib import Path
import re
if __package__:
    from . import decoder_corpus_optimizer as training, decoder_corpus_benchmarks as benchmarks, decoder_corpus_evaluation as heldout, decoder_corpus_leakage_audit as window_overlap
    from .run_manifest import digest,file_digest
else:
    import decoder_corpus_optimizer as training, decoder_corpus_benchmarks as benchmarks, decoder_corpus_evaluation as heldout, decoder_corpus_leakage_audit as window_overlap
    from run_manifest import digest,file_digest

PROTOCOL={'format':'almg-document-token-overlap-protocol-v1','schema_version':1,'span_tokens':4,
          'reconstruction':'document_sha256_and_absolute_token_offsets_shared_boundary_token',
          'padding':'exclude_mask_zero','reference_deduplication':'full_document_token_sequence',
          'examples_per_comparison':8,'ordering':'saved_query_document_then_first_unique_reference_document',
          'scope':'exact_documents_and_four_token_spans_including_cross_window_boundaries'}


def reconstruct(windows):
    documents={}
    for row in windows:
        sha=row['document_sha256'];offset=row['offset'];tokens=window_overlap.active_tokens(row)
        if (not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha) or type(offset) is not int or offset<0
            or offset+len(tokens)>4096 or any(type(value) is not int or not 0<=value<512 for value in tokens)
            or row['inputs'][:len(tokens)-1]!=list(tokens[:-1])):raise ValueError('Invalid document token coordinates or shifted inputs.')
        document=documents.setdefault(sha,{'sha256':sha,'positions':{},'boundaries':set()})
        if offset:document['boundaries'].add(offset)
        for position,value in enumerate(tokens,offset):
            if position in document['positions'] and document['positions'][position]!=value:raise ValueError('Conflicting saved tokens for one document position.')
            document['positions'][position]=value
    result=[]
    for document in documents.values():
        positions=document.pop('positions')
        if set(positions)!=set(range(max(positions)+1)):raise ValueError('Document windows are incomplete; cannot audit gaps as independent text.')
        document['tokens']=tuple(positions[index] for index in range(len(positions)));result.append(document)
    return result


def _crosses(document, offset):
    return any(offset<boundary<offset+PROTOCOL['span_tokens']-1 for boundary in document['boundaries'])


def audit_pair(query_windows, reference_windows, tokenizer):
    query=reconstruct(query_windows);references=reconstruct(reference_windows);unique={}
    for document in references:unique.setdefault(document['tokens'],document)
    examples=[];exact_count=0;shared_count=0;cross_count=0;pair_count=0;short_count=0
    for document in query:
        tokens=document['tokens'];exact=False;shared=False;cross=False
        if len(tokens)<4:short_count+=1
        for other in unique.values():
            first=None;cross_span=None;spans={}
            for offset in range(len(other['tokens'])-3):spans.setdefault(other['tokens'][offset:offset+4],[]).append(offset)
            for left in range(len(tokens)-3):
                for right in spans.get(tokens[left:left+4],[]):
                    if first is None:first=(left,right)
                    if _crosses(document,left) or _crosses(other,right):cross_span=(left,right);break
                if cross_span is not None:break
            is_exact=tokens==other['tokens'];exact=exact or is_exact
            if first is not None:shared=True;pair_count+=1
            if cross_span is not None:cross=True
            if (is_exact or first is not None) and len(examples)<8:
                selected=cross_span or first
                span=None if selected is None else {'query_token_offset':selected[0],'reference_token_offset':selected[1],
                    'token_ids':list(tokens[selected[0]:selected[0]+4]),'text':tokenizer.decode(list(tokens[selected[0]:selected[0]+4])),
                    'query_crosses_window_boundary':_crosses(document,selected[0]),'reference_crosses_window_boundary':_crosses(other,selected[1])}
                examples.append({'query_document_sha256':document['sha256'],'reference_document_sha256':other['sha256'],
                                 'exact_document_match':is_exact,'shared_span':span})
        exact_count+=exact;shared_count+=shared;cross_count+=cross
    within=window_overlap.audit_pair(query_windows,reference_windows,tokenizer)['overlap_detected']
    detected=bool(exact_count or shared_count)
    return {'query_documents':len(query),'reference_documents':len(references),'unique_reference_token_sequences':len(unique),
            'exact_duplicate_query_documents':exact_count,'shared_four_token_query_documents':shared_count,
            'shared_four_token_document_pairs':pair_count,'cross_boundary_shared_query_documents':cross_count,
            'query_documents_shorter_than_four_tokens':short_count,'examples':examples,'overlap_detected':detected,
            'within_window_overlap_detected':within,'additional_document_overlap_detected':detected and not within}


def _corpus(root, identifier):
    record=training.inputs.read(root,identifier);source=record['review']['source']
    initialized=training.hardware.initializations.read(root,source['plan_id'],source['initialization_id'])
    _,_,_,windows,tokenizer=training._source(root,initialized,record)
    return record,windows,tokenizer


def _report(record, comparisons, benchmark=None):
    report={'format':'almg-document-token-overlap-audit-v1','schema_version':1,
            'protocol':dict(PROTOCOL),'protocol_revision':digest(PROTOCOL),'corpus_id':record['id'],'corpus_revision':record['revision'],
            'training_data_binding':heldout.data_binding(record),'benchmark_binding':benchmark,'comparisons':comparisons,
            'overlap_detected':any(item['overlap_detected'] for item in comparisons.values()),
            'requires_overlap_review':any(item['overlap_detected'] for item in comparisons.values()),
            'additional_document_overlap_detected':any(item['additional_document_overlap_detected'] for item in comparisons.values()),
            'independent_evaluation_certified':False,'memorization_validated':False,'training_approved':False,'release_approved':False,
            'limitations':'Exact reconstructed document tokens and four-token spans, including saved-window boundaries. Repeated window/mixing copies do not create extra documents. Conflicting or incomplete coordinates are rejected. This is not semantic/fuzzy/global-use independence or model memorization certification. Findings request review; this read-only audit does not alter existing version-one preparation/scoring gates, saved inputs or training/release approval.',
            'implementation_sha256':digest({name:file_digest(Path(__file__).with_name(name)) for name in ('decoder_corpus_document_overlap.py','decoder_corpus_leakage_audit.py','decoder_corpus_inputs.py','decoder_corpus_benchmarks.py')})}
    report['revision']=digest(report)
    return report


def audit_corpus(root, identifier):
    record,windows,tokenizer=_corpus(root,identifier)
    comparisons={f'{query}_against_{reference}':audit_pair(windows[query],windows[reference],tokenizer)
                 for query,reference in (('validation','train'),('test','train'),('test','validation'))}
    return _report(record,comparisons)


def audit_benchmark(root, identifier):
    benchmark=benchmarks.read(root,identifier);record,existing,tokenizer=_corpus(root,benchmark['review']['corpus_id'])
    if heldout.data_binding(record)!=benchmark['review']['training_data_binding']:raise ValueError('Benchmark corpus binding changed; reopen its reviewed data.')
    windows=json.loads((Path(root)/'decoder-corpus-benchmarks'/identifier/'windows.json').read_text(encoding='utf-8'))
    if digest(windows)!=benchmark['review']['windows_sha256']:raise ValueError('Benchmark windows changed during document audit.')
    return _report(record,{split:audit_pair(windows,existing[split],tokenizer) for split in ('train','validation','test')},
                   {'id':benchmark['id'],'revision':benchmark['revision']})
