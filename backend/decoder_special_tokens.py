"""Explicit reserved control IDs around immutable experimental tokenizers."""
import re

if __package__:
    from .decoder_bpe import ByteBPE
    from .decoder_character_bpe import CharacterBPE
    from .decoder_unigram import UnigramTokenizer
    from .run_manifest import digest
else:
    from decoder_bpe import ByteBPE
    from decoder_character_bpe import CharacterBPE
    from decoder_unigram import UnigramTokenizer
    from run_manifest import digest

ROLE_ORDER=('pad','bos','eos','unk')
FORMATS={'almg-byte-bpe-tokenizer-v1':ByteBPE,'almg-character-bpe-tokenizer-v1':CharacterBPE,'almg-unigram-tokenizer-v1':UnigramTokenizer}


def definitions(value):
    if not isinstance(value,dict) or not set(value)<=set(ROLE_ORDER):raise ValueError('Define only PAD, BOS, EOS and UNK roles.')
    if any(not isinstance(label,str) or re.fullmatch(r'<[A-Za-z0-9_/|.:-]{1,24}>',label) is None for label in value.values()):
        raise ValueError('Use short ASCII markers such as <BOS> for special-token labels.')
    if len(set(value.values()))!=len(value):raise ValueError('Special-token labels must be distinct.')
    return {role:value[role] for role in ROLE_ORDER if role in value}


def restore_base(artifact):
    name=artifact.get('format') if isinstance(artifact,dict) else None
    if not isinstance(name,str) or name not in FORMATS:raise ValueError('Unsupported base tokenizer artifact.')
    return FORMATS[name].restore(artifact)


class SpecialTokenizer:
    def __init__(self,base,labels,unknown_policy='reject'):
        if base.artifact().get('format') not in FORMATS:raise ValueError('Use an unwrapped supported base tokenizer.')
        self.definitions=definitions(labels)
        if not self.definitions:raise ValueError('A special-token wrapper needs at least one reserved role.')
        if unknown_policy not in ('reject','replace') or (unknown_policy=='replace' and 'unk' not in self.definitions):
            raise ValueError('Unknown replacement requires an explicitly defined UNK role.')
        self.base=base;self.unknown_policy=unknown_policy
        self.special_ids={role:len(base.pieces)+index for index,role in enumerate(self.definitions)}
        self.pieces=list(base.pieces)+list(self.definitions.values())
        self.vocabulary_size=base.vocabulary_size+len(self.definitions);self.training_sha256=base.training_sha256
        if self.vocabulary_size>512:raise ValueError('Reserved IDs exceed the configured vocabulary bound.')

    def normalized(self,text):return self.base.normalized(text)

    def uncovered(self,text):return self.base.uncovered(text) if hasattr(self.base,'uncovered') else 0

    def encode(self,text,*,add_boundaries=True):
        if type(add_boundaries) is not bool:raise ValueError('Choose an explicit boundary-token policy.')
        text,_=self.normalized(text);missing=self.uncovered(text)
        if missing and self.unknown_policy!='replace':raise ValueError('Uncovered characters reject without refitting or UNK replacement consent.')
        tokens=[]
        if not missing:tokens=self.base.encode(text)
        else:
            known=set(self.base.alphabet);pending=[]
            def flush():
                if pending:tokens.extend(self.base.encode(''.join(pending)));pending.clear()
            for char in text:
                if char in known:pending.append(char)
                else:flush();tokens.append(self.special_ids['unk'])
            flush()
        if add_boundaries and 'bos' in self.special_ids:tokens.insert(0,self.special_ids['bos'])
        if add_boundaries and 'eos' in self.special_ids:tokens.append(self.special_ids['eos'])
        return tokens

    def decode(self,tokens,*,skip_special_tokens=True,byte_errors='strict'):
        if byte_errors not in ('strict','replace') or (byte_errors!='strict' and type(self.base) is not ByteBPE):
            raise ValueError('Explicit byte replacement decoding requires a byte-BPE base.')
        if (type(skip_special_tokens) is not bool or not isinstance(tokens,list) or not 1<=len(tokens)<=4100
                or any(type(value) is not int or not 0<=value<len(self.pieces) for value in tokens)):
            raise ValueError('Provide bounded IDs and an explicit special-token decode policy.')
        roles={value:role for role,value in self.special_ids.items()};parts=[];pending=[];size=0
        def append(text):
            nonlocal size
            size+=len(text.encode('utf-8'))
            if size>262144:raise ValueError('Decoded special-token text exceeds its bound.')
            parts.append(text)
        def flush():
            if pending:
                append(self.base.decode(pending,errors=byte_errors) if type(self.base) is ByteBPE else self.base.decode(pending));pending.clear()
        for value in tokens:
            role=roles.get(value)
            if role is None:pending.append(value);continue
            if role!='unk' and skip_special_tokens:continue
            flush();append(self.definitions[role])
        flush();return ''.join(parts)

    def validate_current_model(self,config):
        if not isinstance(config,dict) or type(config.get('vocab_size')) is not int or config['vocab_size']!=len(self.pieces):
            raise ValueError('Model vocabulary must include the exact reserved token IDs.')
        raise ValueError('Special-token experiment artifacts are not enabled for pretraining yet.')

    def artifact(self):
        return {'format':'almg-special-tokenizer-v1','schema_version':1,'base':self.base.artifact(),
                'definitions':self.definitions,'special_ids':self.special_ids,'unknown_policy':self.unknown_policy,
                'method':{'version':1,'automatic_defined_bos_eos':True,'automatic_padding':False,
                          'literal_input_markers':'ordinary_text_not_control_ids','unknown_replacement':'one_id_per_uncovered_nfc_codepoint',
                          'decode_skips_bos_eos_pad_by_default':True,'decode_never_skips_unk':True,'maximum_decoded_bytes':262144}}

    @classmethod
    def restore(cls,artifact):
        if not isinstance(artifact,dict) or set(artifact)!={'format','schema_version','base','definitions','special_ids','unknown_policy','method'}:
            raise ValueError('Unsupported special-token artifact fields.')
        model=cls(restore_base(artifact['base']),artifact['definitions'],artifact['unknown_policy'])
        if type(artifact['schema_version']) is not int or digest(artifact)!=digest(model.artifact()):raise ValueError('Special-token ID/configuration binding changed.')
        return model
