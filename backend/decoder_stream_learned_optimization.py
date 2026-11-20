"""Explicit learned-codec numerical diagnostic; no training approval or saved weights."""
if __package__:
    from . import decoder_stream_optimization as core, decoder_stream_learned_batches as batches
else:
    import decoder_stream_optimization as core
    import decoder_stream_learned_batches as batches


def run(root,window_id,confirmed,reviewed,reviewed_batch,cursor=None):
    return core._run(root,window_id,confirmed,reviewed,reviewed_batch,cursor,batches,True)


def list_reports(root,window_id,confirmed):
    batches.windows._folder(root,window_id)
    return core._list_reports(root,window_id,confirmed,True)
