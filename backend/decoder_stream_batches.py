"""Bounded model-input batches from reviewed source-bound windows; no training."""
if __package__:
    from . import decoder_stream_windows as windows
else:
    import decoder_stream_windows as windows


def read_batch(root,window_id,confirmed,reviewed,cursor=None,split='train',batch_size=4):
    if confirmed is not True:raise ValueError('Confirm local model-input review; token IDs encode source text.')
    if type(batch_size) is not int or not 1<=batch_size<=16 or split not in ('train','validation','test'):
        raise ValueError('Choose one saved split and 1 to 16 windows per batch.')
    record=windows.read(root,window_id)
    if record['status']!='complete':raise ValueError('Complete token-window preparation before reading model inputs.')
    if not isinstance(reviewed,dict) or reviewed!=record:raise ValueError('The prepared-window review changed. Reopen it before reading batches.')
    sources=windows._bindings(root,record['tokenizer_id'],record['overlap_id'])
    if (sources['index']['revision']!=record['index_revision']
            or sources['tokenizer']['revision']!=record['tokenizer_revision']
            or sources['overlap']['revision']!=record['overlap_revision']):
        raise ValueError('Source or contamination evidence changed. Preserve the prepared windows and review current sources.')
    page=windows.record_page(root,window_id,True,cursor,split,batch_size)
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
