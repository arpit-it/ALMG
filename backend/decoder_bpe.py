"""Bounded deterministic byte-level BPE experiments, separate from model tokenizers."""
from collections import Counter
import re
import unicodedata

if __package__:
    from .run_manifest import digest
else:
    from run_manifest import digest


class ByteBPE:
    def __init__(self,merges,training_sha256,vocabulary_size):
        if type(vocabulary_size) is not int or not 256<=vocabulary_size<=512:
            raise ValueError('Choose a vocabulary cap from 256 to 512.')
        if not isinstance(training_sha256,str) or re.fullmatch('[a-f0-9]{64}',training_sha256) is None:
            raise ValueError('Bind BPE to its training document revision.')
        if not isinstance(merges,list) or len(merges)>vocabulary_size-256:raise ValueError('Invalid bounded BPE merge list.')
        self.pieces=[bytes([value]) for value in range(256)];self.merges=[];seen=set()
        for pair in merges:
            if (not isinstance(pair,list) or len(pair)!=2 or any(type(value) is not int or not 0<=value<len(self.pieces) for value in pair)
                    or tuple(pair) in seen):raise ValueError('BPE merges require unique backward references.')
            piece=self.pieces[pair[0]]+self.pieces[pair[1]]
            if len(piece)>4096:raise ValueError('A BPE token exceeds the input byte bound.')
            self.pieces.append(piece);self.merges.append(list(pair));seen.add(tuple(pair))
        self.training_sha256=training_sha256;self.vocabulary_size=vocabulary_size

    @staticmethod
    def normalized(text):
        if not isinstance(text,str):raise ValueError('BPE requires Unicode text.')
        text=unicodedata.normalize('NFC',text);encoded=text.encode('utf-8')
        if not 1<=len(encoded)<=4096:raise ValueError('Each BPE sample must fit 1 to 4096 UTF-8 bytes.')
        return text,encoded

    @staticmethod
    def _merge(tokens,pair,new_id):
        result=[];index=0
        while index<len(tokens):
            if index+1<len(tokens) and (tokens[index],tokens[index+1])==pair:
                result.append(new_id);index+=2
            else:result.append(tokens[index]);index+=1
        return result

    @classmethod
    def fit(cls,texts,vocabulary_size):
        if not isinstance(texts,list) or not 1<=len(texts)<=16:raise ValueError('Fit BPE on 1 to 16 training documents.')
        normalized=[cls.normalized(text) for text in texts]
        if sum(len(encoded) for _,encoded in normalized)>128000:raise ValueError('BPE training bytes exceed 128000.')
        model=cls([],digest([text for text,_ in normalized]),vocabulary_size)
        sequences=[list(encoded) for _,encoded in normalized]
        while len(model.pieces)<vocabulary_size:
            counts=Counter(pair for tokens in sequences for pair in zip(tokens,tokens[1:]))
            if not counts:break
            best=min(counts,key=lambda pair:(-counts[pair],pair))
            if counts[best]<2:break
            new_id=len(model.pieces);piece=model.pieces[best[0]]+model.pieces[best[1]]
            if len(piece)>4096:raise ValueError('A fitted BPE token exceeds the input bound.')
            model.merges.append(list(best));model.pieces.append(piece)
            sequences=[cls._merge(tokens,best,new_id) for tokens in sequences]
        return model

    def encode(self,text):
        _,encoded=self.normalized(text);tokens=list(encoded)
        for rank,pair in enumerate(self.merges):tokens=self._merge(tokens,tuple(pair),256+rank)
        return tokens

    def decode(self,tokens,*,errors='strict'):
        if errors not in ('strict','replace'):raise ValueError('Choose strict or explicit replacement UTF-8 decoding.')
        if (not isinstance(tokens,list) or not 1<=len(tokens)<=4096
                or any(type(value) is not int or not 0<=value<len(self.pieces) for value in tokens)):
            raise ValueError('Provide bounded token IDs from this BPE vocabulary.')
        if sum(len(self.pieces[value]) for value in tokens)>4096:raise ValueError('Decoded BPE text exceeds 4096 bytes.')
        return b''.join(self.pieces[value] for value in tokens).decode('utf-8',errors=errors)

    def artifact(self):
        return {'format':'almg-byte-bpe-tokenizer-v1','schema_version':1,'normalization':'NFC',
                'base_alphabet':'all_256_utf8_bytes','vocabulary_cap':self.vocabulary_size,
                'training_documents_sha256':self.training_sha256,'merges':self.merges,
                'method':{'version':1,'minimum_pair_frequency':2,'tie_break':'lexicographic_token_id_pair','cross_document_merges':False,'special_tokens':False}}

    @classmethod
    def restore(cls,artifact):
        if not isinstance(artifact,dict) or set(artifact)!={'format','schema_version','normalization','base_alphabet','vocabulary_cap','training_documents_sha256','merges','method'}:
            raise ValueError('Unsupported BPE artifact fields.')
        model=cls(artifact['merges'],artifact['training_documents_sha256'],artifact['vocabulary_cap'])
        if digest(artifact)!=digest(model.artifact()) or type(artifact['schema_version']) is not int:raise ValueError('Unsupported BPE artifact method/version.')
        return model

    def validate_current_model(self,config):
        if not isinstance(config,dict) or type(config.get('vocab_size')) is not int or config['vocab_size']!=len(self.pieces):
            raise ValueError('Model vocabulary size must exactly match the BPE artifact.')
        raise ValueError('BPE experiment artifacts are not enabled for pretraining yet.')
