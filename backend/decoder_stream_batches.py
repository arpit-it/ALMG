"""Bounded model-input batches from reviewed source-bound windows; no training."""
import json

if __package__:
    from . import decoder_stream_windows as windows
else:
    import decoder_stream_windows as windows


def read_batch(root,window_id,confirmed,reviewed,cursor=None,split='train',batch_size=4):
    if confirmed is not True:raise ValueError('Confirm local model-input review; token IDs encode source text.')
    if type(batch_size) is not int or not 1<=batch_size<=16 or split not in ('train','validation','test'):
        raise ValueError('Choose one saved split and 1 to 16 windows per batch.')
    record=_validated(root,window_id,reviewed)
    page=windows.record_page(root,window_id,True,cursor,split,batch_size)
    return _assemble(window_id,record,split,page)


def _validated(root,window_id,reviewed):
    record=windows.read(root,window_id)
    if record['status']!='complete':raise ValueError('Complete token-window preparation before reading model inputs.')
    if not isinstance(reviewed,dict) or reviewed!=record:raise ValueError('The prepared-window review changed. Reopen it before reading batches.')
    sources=windows._bindings(root,record['tokenizer_id'],record['overlap_id'])
    if (sources['index']['revision']!=record['index_revision']
            or sources['tokenizer']['revision']!=record['tokenizer_revision']
            or sources['overlap']['revision']!=record['overlap_revision']):
        raise ValueError('Source or contamination evidence changed. Preserve the prepared windows and review current sources.')
    return record


def _assemble(window_id,record,split,page):
    inputs=[];targets=[];masks=[];lengths=[];provenance=[]
    for row in page['records']:
        ids=row['token_ids']
        if (not isinstance(ids,list) or not 2<=len(ids)<=17
                or any(type(token) is not int or not 0<=token<=255 for token in ids)
                or row['split']!=split):
            raise ValueError('Window tokens or split do not match the model-input contract.')
        length=len(ids)-1;padding=16-length
        inputs.append(ids[:-1]+[0]*padding);targets.append(ids[1:]+[0]*padding)
        masks.append([1]*length+[0]*padding);lengths.append(length)
        provenance.append({key:row[key] for key in ('group','token_offset','split','first_line','first_byte_offset','raw_line_sha256','occurrences','source_sha256')})
    return {'format':'almg-stream-model-batch-v1','schema_version':1,'windows_id':window_id,
            'windows_revision':record['revision'],'split':split,'rows':len(inputs),'sequence_width':16,
            'inputs':inputs,'targets':targets,'loss_mask':masks,'sequence_lengths':lengths,
            'real_target_tokens':sum(lengths),'provenance':provenance,'next_cursor':page['next_cursor'],
            'method':{'version':1,'padding_value':0,'padding_is_special_token':False,
                      'loss_mask_required':True,'source_order':'group_then_token_offset',
                      'source_occurrences_expanded':False,'document_boundaries_preserved':True,
                      'limitations':'Deterministic read-only batches; no shuffling, sampling weights, model execution or training approval.'},
            'training_approved':False}


def _signatures(root,record):
    paths=[]
    for folder,files in (
        (windows._folder(root,record['id']),('manifest.json','windows.sqlite3')),
        (windows.indexes._folder(root,record['index_id']),('manifest.json','records.sqlite3')),
        (windows.tokenizers._folder(root,record['tokenizer_id']),('manifest.json','tokenizer.json')),
        (windows.overlap._folder(root,record['overlap_id']),('manifest.json','overlap.sqlite3'))):
        for name in files:
            path=folder/name
            try:
                stat=path.stat();paths.append((str(path),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns,stat.st_ino))
            except OSError as error:raise ValueError('Evaluation source files changed or became unavailable.') from error
    return paths


def iter_batches(root,window_id,confirmed,reviewed,split='validation',batch_size=16):
    """One complete split: full validation at boundaries, file guards per bounded page.

    Consumers must exhaust the iterator before publishing metrics. Early termination
    is not a verified evaluation. No global cache or caller-supplied trusted cursor.
    """
    if confirmed is not True:raise ValueError('Confirm local model-input review; token IDs encode source text.')
    if type(batch_size) is not int or not 1<=batch_size<=16 or split not in ('train','validation','test'):
        raise ValueError('Choose one saved split and 1 to 16 windows per batch.')
    # Capture before hashing so concurrent changes during initial verification reject.
    if not isinstance(reviewed,dict) or reviewed.get('id')!=window_id:raise ValueError('Reopen the prepared-window review.')
    signatures=_signatures(root,reviewed)
    record=_validated(root,window_id,reviewed)
    def unchanged():
        if _signatures(root,record)!=signatures:raise ValueError('Evaluation source files changed; no complete metrics may be published.')
    unchanged();group='';offset=-1
    database=windows._folder(root,window_id)/'windows.sqlite3'
    while True:
        unchanged()
        with windows.indexes._connect(database,True) as db:
            rows=db.execute(
                'SELECT w.group_sha256,w.token_offset,w.split,w.tokens,d.first_line,d.first_byte_offset,d.raw_line_sha256,d.occurrences '
                'FROM windows w JOIN documents d ON d.group_sha256=w.group_sha256 '
                'WHERE w.split=? AND (w.group_sha256>? OR (w.group_sha256=? AND w.token_offset>?)) '
                'ORDER BY w.group_sha256,w.token_offset LIMIT ?',
                (split,group,group,offset,batch_size+1)).fetchall()
        unchanged();records=[]
        for group_value,token_offset,part,tokens,line,source_offset,raw_sha,occurrences in rows[:batch_size]:
            records.append({'group':group_value,'token_offset':token_offset,'split':part,'token_ids':json.loads(tokens),
                            'first_line':line,'first_byte_offset':source_offset,'raw_line_sha256':raw_sha,
                            'occurrences':occurrences,'source_sha256':record['source_sha256']})
        following=({'revision':record['revision'],'after_group':records[-1]['group'],
                    'after_offset':records[-1]['token_offset'],'split':split} if len(rows)>batch_size else None)
        yield _assemble(window_id,record,split,{'records':records,'next_cursor':following})
        unchanged()
        if following is None:break
        group=following['after_group'];offset=following['after_offset']
    _validated(root,window_id,reviewed)
    unchanged()
