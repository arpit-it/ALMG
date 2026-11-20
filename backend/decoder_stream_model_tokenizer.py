"""Explicit streamed-codec model persistence wrapper; no student-training approval."""
from copy import deepcopy
import re

if __package__:
    from .decoder_tokenizer import Tokenizer
    from . import decoder_stream_bpe as one,decoder_stream_iterative_bpe as iterative,decoder_stream_character_bpe as character,decoder_stream_unigram as unigram
    from .decoder_recipe import architecture_version
    from .run_manifest import digest
else:
    from decoder_tokenizer import Tokenizer
    import decoder_stream_bpe as one,decoder_stream_iterative_bpe as iterative,decoder_stream_character_bpe as character,decoder_stream_unigram as unigram
    from decoder_recipe import architecture_version
    from run_manifest import digest

FORMAT='almg-reviewed-stream-model-tokenizer-v1'


class StreamModelTokenizer(Tokenizer):
    def __init__(self,artifact,selection):
        codecs={'almg-stream-one-merge-byte-bpe-v1':one.StreamByteBPE,
                'almg-stream-iterative-byte-bpe-v1':iterative.StreamByteBPE,'almg-stream-iterative-byte-bpe-v2':iterative.StreamByteBPE,
                'almg-stream-character-bpe-v1':character.StreamCharacterBPE,'almg-stream-unigram-v1':unigram.StreamUnigram}
        if not isinstance(artifact,dict) or artifact.get('format') not in codecs:raise ValueError('Provide a completed supported full-split codec.')
        self.codec=codecs[artifact['format']].restore(artifact)
        architecture_version({'vocab_size':len(self.codec.pieces)})
        fields={'windows_id':32,'windows_revision':64,'fit_id':32,'fit_revision':64,'index_id':32,'index_revision':64,
                'source_sha256':64,'tokenizer_sha256':64,'approval_sha256':64}
        if (not isinstance(selection,dict) or set(selection)!=set(fields)
                or any(not isinstance(selection[key],str) or re.fullmatch('[a-f0-9]{'+str(size)+'}',selection[key]) is None for key,size in fields.items())
                or selection['tokenizer_sha256']!=digest(artifact)):
            raise ValueError('Bind the exact streamed window, codec, source and persistence approval revisions.')
        self.selection=deepcopy(selection)

    @property
    def vocabulary(self):return [f'<stream-token-id-{index}>' for index in range(len(self.codec.pieces))]

    def encode(self,text):
        tokens=self.codec.encode(text)
        if not tokens or any(type(value) is not int or not 0<=value<len(self.codec.pieces) for value in tokens):raise ValueError('Stream model input must encode to valid lossless IDs.')
        return tokens

    def decode(self,tokens):return self.codec.decode(tokens)

    def decode_preview(self,tokens):
        if (not isinstance(tokens,list) or not 1<=len(tokens)<=160
                or any(type(value) is not int or not 0<=value<len(self.codec.pieces) for value in tokens)):
            raise ValueError('Stream model preview requires 1 to 160 valid IDs.')
        pieces=[self.codec.pieces[value] for value in tokens]
        data=b''.join(piece if isinstance(piece,bytes) else piece.encode('utf-8') for piece in pieces)
        if len(data)>65536:raise ValueError('Stream model preview exceeds 65536 decoded bytes.')
        text=data.decode('utf-8',errors='replace')
        if len(text.encode('utf-8'))>65536:raise ValueError('Stream model preview exceeds 65536 UTF-8 output bytes.')
        return text

    def validate_training_documents(self,texts):
        raise ValueError('Stream model tokenizers require a separately approved streamed training workflow; bounded-dataset refitting is unavailable.')

    def validate_persistence_record(self,record):
        expected={'kind','schema_version','approval','approval_sha256','optimizer_updates','pretrained_weights_loaded','model_training_approved','release_approved'}
        if (not isinstance(record,dict) or set(record)!=expected or record.get('kind')!='stream_model_persistence_check'
                or type(record.get('schema_version')) is not int or record['schema_version']!=1
                or type(record.get('optimizer_updates')) is not int or record['optimizer_updates']!=0
                or any(record.get(key) is not False for key in ('pretrained_weights_loaded','model_training_approved','release_approved'))):
            raise ValueError('Stream model bundles currently support only explicitly reviewed zero-update persistence checks.')
        approval=record['approval']
        if (not isinstance(approval,dict) or set(approval)!={'version','scope','windows_id','windows_revision','tokenizer_sha256','inspected_batch_sha256','seed'}
                or type(approval.get('version')) is not int or approval['version']!=1
                or approval.get('scope')!='fresh_stream_model_persistence_only' or type(approval.get('seed')) is not int or approval['seed']!=7
                or not isinstance(approval.get('inspected_batch_sha256'),str) or re.fullmatch('[a-f0-9]{64}',approval['inspected_batch_sha256']) is None
                or any(approval.get(key)!=self.selection[key] for key in ('windows_id','windows_revision','tokenizer_sha256'))
                or record['approval_sha256']!=digest(approval) or record['approval_sha256']!=self.selection['approval_sha256']):
            raise ValueError('Stream bundle persistence approval binding changed.')

    def artifact(self):
        return {'format':FORMAT,'schema_version':1,'codec':self.codec.artifact(),'selection':deepcopy(self.selection),
                'scope':'separately_approved_stream_model_persistence_only','input_policy':'lossless_only_no_unknown_replacement',
                'generated_decode_policy':'utf8_replacement_preview_160_ids_65536_bytes','training_approved':False,'release_approved':False}

    @classmethod
    def restore(cls,artifact):
        if (not isinstance(artifact,dict) or set(artifact)!={'format','schema_version','codec','selection','scope','input_policy','generated_decode_policy','training_approved','release_approved'}
                or artifact.get('format')!=FORMAT or type(artifact.get('schema_version')) is not int):raise ValueError('Unsupported streamed model tokenizer artifact.')
        model=cls(artifact['codec'],artifact['selection'])
        if digest(artifact)!=digest(model.artifact()):raise ValueError('Streamed model tokenizer version or policy changed.')
        return model
