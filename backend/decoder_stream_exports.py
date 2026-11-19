"""Reviewed bounded-chunk export of immutable text indexes; no raw-source export."""
import base64
import json
from pathlib import Path

if __package__:
    from . import decoder_stream_indexes as indexes, decoder_stream_permissions as permissions
    from .run_manifest import digest,file_digest
else:
    import decoder_stream_indexes as indexes
    import decoder_stream_permissions as permissions
    from run_manifest import digest,file_digest

FILES=('manifest.json','records.sqlite3')


def _review(root,index_id,verify):
    folder=indexes._folder(root,index_id)
    manifest=indexes.read(root,index_id) if verify else json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('format')!='almg-stream-text-index-v1' or type(manifest.get('schema_version')) is not int
            or manifest['schema_version']!=1 or manifest.get('id')!=index_id or manifest.get('status')!='complete'
            or manifest.get('revision')!=digest({key:value for key,value in manifest.items() if key!='revision'})
            or set(manifest.get('files',{}))!={'records.sqlite3'}):
        raise ValueError('Complete and verify the text index before export.')
    review={'format':'almg-stream-index-export-v2','schema_version':2,'index_id':index_id,
            'index_revision':manifest['revision'],'scope':'private_local_normalized_text_index',
            'includes_normalized_text':True,'includes_original_raw_source':False,
            'includes_saved_audits':False,'includes_training_approvals':False,
            'source_provenance':{key:manifest[key] for key in ('source_id','source_name','source_sha256','source_bytes')},
            'source_permission_review':permissions.snapshot(root,manifest),
            'files':{name:{'bytes':(folder/name).stat().st_size,
                           'sha256':file_digest(folder/name) if name=='manifest.json' else manifest['files'][name]}
                     for name in FILES},
            'file_signatures':{name:indexes._signature(folder/name) for name in FILES},
            'implementation_sha256':file_digest(Path(__file__))}
    review['revision']=digest(review)
    return review


def review(root,index_id):
    return _review(root,index_id,True)


def _validate(root,index_id,confirmed,approved,verify=False):
    if confirmed is not True:raise ValueError('Confirm the exact private text-index export review.')
    if not isinstance(approved,dict) or approved!=_review(root,index_id,verify):
        raise ValueError('The text-index export review changed. Reopen the current review before saving.')


def chunk(root,index_id,confirmed,approved,file_name,offset,limit=65536):
    if (file_name not in FILES or type(offset) is not int or offset<0
            or type(limit) is not int or not 1<=limit<=65536):
        raise ValueError('Choose a fixed export file, exact offset and at most 65536 bytes.')
    _validate(root,index_id,confirmed,approved)
    total=approved['files'][file_name]['bytes']
    if offset>=total:raise ValueError('Export offset exceeds the reviewed file.')
    with (indexes._folder(root,index_id)/file_name).open('rb') as source:
        source.seek(offset);data=source.read(min(limit,total-offset))
    if len(data)!=min(limit,total-offset):raise ValueError('Export file changed during read.')
    return {'file_name':file_name,'offset':offset,'bytes':len(data),'total_bytes':total,
            'data':base64.b64encode(data).decode('ascii')}


def seal(root,index_id,confirmed,approved):
    _validate(root,index_id,confirmed,approved,verify=True)
    return {'export_manifest':approved,'revision':approved['revision']}
