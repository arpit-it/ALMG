"""Complete bounded learned-tokenizer split scans; exhaust before publishing metrics."""
import json
if __package__:
    from . import decoder_stream_learned_windows as windows
else:
    import decoder_stream_learned_windows as windows

read_batch=windows.read_batch


def _validated(root,window_id,reviewed):
    record=windows.read(root,window_id)
    if (record['status']!='complete' or not isinstance(reviewed,dict) or record!=reviewed):
        raise ValueError('Reopen the exact completed learned-window review.')
    if windows.review(root,record['comparison_id'],record['overlap_id'])!=record['reviewed_sources']:
        raise ValueError('Learned-window source evidence changed.')
    return record


def _signatures(root,record):
    # The fast binding also verifies permission history and current codec metadata.
    current,_=windows._sources(root,record['comparison_id'],record['overlap_id'],False)
    if current!=record['reviewed_sources']:raise ValueError('Evaluation source files changed; no metrics may be published.')
    paths=[windows._folder(root,record['id'])/name for name in ('manifest.json','windows.sqlite3')]
    paths.append(windows.indexes._folder(root,record['index_id'])/'manifest.json')
    try:return {str(path):windows.comparisons._signature(path) for path in paths}
    except OSError as error:raise ValueError('Evaluation source files became unavailable.') from error


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
        yield windows._assemble(window_id,record,split,{'records':records,'next_cursor':following})
        unchanged()
        if following is None:break
        group=following['after_group'];offset=following['after_offset']
    _validated(root,window_id,reviewed)
    unchanged()
