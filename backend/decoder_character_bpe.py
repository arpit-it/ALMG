"""Bounded character-alphabet BPE; uncovered evaluation characters never refit it."""
from collections import Counter
import re
import unicodedata

if __package__:
    from .decoder_bpe import ByteBPE
    from .run_manifest import digest
else:
    from decoder_bpe import ByteBPE
    from run_manifest import digest


class CharacterBPE(ByteBPE):
    def __init__(self,alphabet,merges,training_sha256,vocabulary_size):
        if type(vocabulary_size) is not int or not 32<=vocabulary_size<=512:raise ValueError('Choose a character BPE vocabulary cap from 32 to 512.')
        if (not isinstance(alphabet,list) or not 1<=len(alphabet)<=vocabulary_size
                or any(not isinstance(char,str) or len(char)!=1 or unicodedata.normalize('NFC',char)!=char for char in alphabet)
                or alphabet!=sorted(set(alphabet))):raise ValueError('Character BPE needs a sorted unique training alphabet within the cap.')
        for char in alphabet:char.encode('utf-8')
        if not isinstance(training_sha256,str) or re.fullmatch('[a-f0-9]{64}',training_sha256) is None:raise ValueError('Bind BPE to its training documents.')
        if not isinstance(merges,list) or len(alphabet)+len(merges)>vocabulary_size:raise ValueError('Invalid bounded character BPE merge list.')
        self.alphabet=list(alphabet);self.pieces=list(alphabet);self.merges=[];seen=set()
        for pair in merges:
            if (not isinstance(pair,list) or len(pair)!=2 or any(type(value) is not int or not 0<=value<len(self.pieces) for value in pair)
                    or tuple(pair) in seen):raise ValueError('BPE merges require unique backward references.')
            piece=self.pieces[pair[0]]+self.pieces[pair[1]]
            if len(piece.encode('utf-8'))>4096:raise ValueError('A BPE token exceeds the sample byte bound.')
            self.pieces.append(piece);self.merges.append(list(pair));seen.add(tuple(pair))
        self._ids={char:index for index,char in enumerate(alphabet)}
        self.training_sha256=training_sha256;self.vocabulary_size=vocabulary_size

    @classmethod
    def fit(cls,texts,vocabulary_size):
        if not isinstance(texts,list) or not 1<=len(texts)<=16:raise ValueError('Fit BPE on 1 to 16 training documents.')
        normalized=[cls.normalized(text) for text in texts]
        if sum(len(encoded) for _,encoded in normalized)>128000:raise ValueError('BPE training bytes exceed 128000.')
        alphabet=sorted({char for text,_ in normalized for char in text})
        model=cls(alphabet,[],digest([text for text,_ in normalized]),vocabulary_size)
        sequences=[[model._ids[char] for char in text] for text,_ in normalized]
        while len(model.pieces)<vocabulary_size:
            counts=Counter(pair for tokens in sequences for pair in zip(tokens,tokens[1:]))
            if not counts:break
            best=min(counts,key=lambda pair:(-counts[pair],pair))
            if counts[best]<2:break
            new_id=len(model.pieces);piece=model.pieces[best[0]]+model.pieces[best[1]]
            if len(piece.encode('utf-8'))>4096:raise ValueError('A fitted BPE token exceeds the sample bound.')
            model.merges.append(list(best));model.pieces.append(piece)
            sequences=[cls._merge(tokens,best,new_id) for tokens in sequences]
        return model

    def uncovered(self,text):
        normalized,_=self.normalized(text)
        return sum(char not in self._ids for char in normalized)

    def encode(self,text):
        normalized,_=self.normalized(text)
        if any(char not in self._ids for char in normalized):raise ValueError('NFC characters are outside the fitted training alphabet; held-out text never refits it.')
        tokens=[self._ids[char] for char in normalized]
        for rank,pair in enumerate(self.merges):tokens=self._merge(tokens,tuple(pair),len(self.alphabet)+rank)
        return tokens

    def decode(self,tokens):
        if (not isinstance(tokens,list) or not 1<=len(tokens)<=4096
                or any(type(value) is not int or not 0<=value<len(self.pieces) for value in tokens)):
            raise ValueError('Provide bounded token IDs from this character BPE vocabulary.')
        if sum(len(self.pieces[value].encode('utf-8')) for value in tokens)>4096:raise ValueError('Decoded BPE text exceeds 4096 bytes.')
        return ''.join(self.pieces[value] for value in tokens)

    def artifact(self):
        return {'format':'almg-character-bpe-tokenizer-v1','schema_version':1,'normalization':'NFC',
                'base_alphabet':'training_nfc_codepoints_only','alphabet':self.alphabet,'vocabulary_cap':self.vocabulary_size,
                'training_documents_sha256':self.training_sha256,'merges':self.merges,
                'method':{'version':1,'minimum_pair_frequency':2,'tie_break':'lexicographic_token_id_pair',
                          'cross_document_merges':False,'special_tokens':False,'uncovered_characters':'reject_without_refitting'}}

    @classmethod
    def restore(cls,artifact):
        if not isinstance(artifact,dict) or set(artifact)!={'format','schema_version','normalization','base_alphabet','alphabet','vocabulary_cap','training_documents_sha256','merges','method'}:
            raise ValueError('Unsupported character BPE artifact fields.')
        model=cls(artifact['alphabet'],artifact['merges'],artifact['training_documents_sha256'],artifact['vocabulary_cap'])
        if digest(artifact)!=digest(model.artifact()) or type(artifact['schema_version']) is not int:raise ValueError('Unsupported character BPE artifact method/version.')
        return model
