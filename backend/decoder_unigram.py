"""Bounded fixed-candidate Unigram EM and Viterbi; not a SentencePiece artifact.

Likelihood/EM reference: https://aclanthology.org/P18-1007/
Vocabulary pruning and segmentation sampling are deliberately not implemented.
"""
from collections import Counter
import math

if __package__:
    from .decoder_character_bpe import CharacterBPE
    from .run_manifest import digest
else:
    from decoder_character_bpe import CharacterBPE
    from run_manifest import digest


def _logadd(left,right):
    if left==-math.inf:return right
    if right==-math.inf:return left
    high=max(left,right);return high+math.log1p(math.exp(min(left,right)-high))


class UnigramTokenizer(CharacterBPE):
    def __init__(self,alphabet,pieces,probabilities,training_sha256,vocabulary_size,history=None):
        super().__init__(alphabet,[],training_sha256,vocabulary_size)
        if (not isinstance(pieces,list) or not len(alphabet)<=len(pieces)<=vocabulary_size
                or pieces[:len(alphabet)]!=alphabet
                or any(not isinstance(piece,str) or not 2<=len(piece)<=8 or any(char.isspace() for char in piece)
                       or any(char not in self._ids for char in piece) for piece in pieces[len(alphabet):])
                or pieces[len(alphabet):]!=sorted(set(pieces[len(alphabet):]))):raise ValueError('Invalid fixed Unigram vocabulary.')
        self.pieces=list(pieces);self._piece_ids={piece:index for index,piece in enumerate(pieces)}
        self._set_probabilities(probabilities)
        if history is not None and not isinstance(history,list):raise ValueError('Invalid Unigram EM history.')
        self.history=[] if history is None else list(history)
        if (len(self.history) not in (0,6) or any(type(value) not in (int,float) or not math.isfinite(value) for value in self.history)
                or any(after<before-1e-6 for before,after in zip(self.history,self.history[1:]))):raise ValueError('Invalid Unigram EM evidence.')

    def _set_probabilities(self,values):
        if (not isinstance(values,list) or len(values)!=len(self.pieces)
                or any(type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=1 for value in values)
                or abs(math.fsum(values)-1)>1e-9):raise ValueError('Unigram probabilities must be positive, finite and sum to one.')
        self.probabilities=[float(value) for value in values];self._logs=[math.log(value) for value in values]

    def _transitions(self,text,start):
        for size in range(1,min(8,len(text)-start)+1):
            index=self._piece_ids.get(text[start:start+size])
            if index is not None:yield start+size,index

    def _expected(self,text):
        text,_=self.normalized(text)
        if self.uncovered(text):raise ValueError('Unigram text contains uncovered training-alphabet characters.')
        size=len(text);edges=[list(self._transitions(text,index)) for index in range(size)]
        forward=[-math.inf]*(size+1);forward[0]=0.
        for start in range(size):
            for end,index in edges[start]:forward[end]=_logadd(forward[end],forward[start]+self._logs[index])
        backward=[-math.inf]*(size+1);backward[size]=0.
        for start in reversed(range(size)):
            for end,index in edges[start]:backward[start]=_logadd(backward[start],self._logs[index]+backward[end])
        total=forward[size];counts=[0.]*len(self.pieces)
        if not math.isfinite(total):raise ValueError('Unigram likelihood is unavailable.')
        for start in range(size):
            for end,index in edges[start]:counts[index]+=math.exp(forward[start]+self._logs[index]+backward[end]-total)
        return total,counts

    @classmethod
    def fit(cls,texts,vocabulary_size):
        if not isinstance(texts,list) or not 1<=len(texts)<=16:raise ValueError('Fit Unigram on 1 to 16 training documents.')
        normalized=[cls.normalized(text) for text in texts]
        if sum(len(encoded) for _,encoded in normalized)>128000:raise ValueError('Unigram training bytes exceed 128000.')
        alphabet=sorted({char for text,_ in normalized for char in text})
        # Reuse strict training alphabet/cap validation before enumerating candidates.
        CharacterBPE(alphabet,[],digest([text for text,_ in normalized]),vocabulary_size)
        counts=Counter(char for text,_ in normalized for char in text)
        for text,_ in normalized:
            for start in range(len(text)):
                for size in range(2,min(8,len(text)-start)+1):
                    piece=text[start:start+size]
                    if any(char.isspace() for char in piece):break
                    counts[piece]+=1
        candidates=sorted((piece for piece,count in counts.items() if len(piece)>1 and count>=2),
                          key=lambda piece:(-counts[piece]*(len(piece)-1),piece))[:vocabulary_size-len(alphabet)]
        pieces=alphabet+sorted(candidates);mass=math.fsum(counts[piece] for piece in pieces)
        model=cls(alphabet,pieces,[counts[piece]/mass for piece in pieces],digest([text for text,_ in normalized]),vocabulary_size)
        model.history=[sum(model._expected(text)[0] for text,_ in normalized)]
        for _ in range(5):
            expected=[1e-12]*len(pieces)
            for text,_ in normalized:
                _,contribution=model._expected(text)
                expected=[left+right for left,right in zip(expected,contribution)]
            total=math.fsum(expected);model._set_probabilities([value/total for value in expected])
            likelihood=sum(model._expected(text)[0] for text,_ in normalized)
            if likelihood<model.history[-1]-1e-6:raise ValueError('Unigram EM likelihood decreased; no tokenizer published.')
            model.history.append(likelihood)
        return model

    def encode(self,text):
        text,_=self.normalized(text)
        if self.uncovered(text):raise ValueError('NFC characters are outside the fitted training alphabet; held-out text never refits it.')
        best=[-math.inf]*(len(text)+1);best[0]=0.;previous=[None]*(len(text)+1)
        for start in range(len(text)):
            for end,index in self._transitions(text,start):
                score=best[start]+self._logs[index];tie=(index,start)
                if score>best[end] or (score==best[end] and (previous[end] is None or tie<previous[end])):
                    best[end]=score;previous[end]=tie
        tokens=[];end=len(text)
        while end:
            if previous[end] is None:raise ValueError('No Unigram segmentation is available.')
            index,start=previous[end];tokens.append(index);end=start
        return list(reversed(tokens))

    def validate_current_model(self,config):
        if not isinstance(config,dict) or type(config.get('vocab_size')) is not int or config['vocab_size']!=len(self.pieces):
            raise ValueError('Model vocabulary size must exactly match the Unigram artifact.')
        raise ValueError('Unigram experiment artifacts are not enabled for pretraining yet.')

    def artifact(self):
        return {'format':'almg-unigram-tokenizer-v1','schema_version':1,'normalization':'NFC',
                'base_alphabet':'training_nfc_codepoints_only','alphabet':self.alphabet,'pieces':self.pieces,
                'probabilities':self.probabilities,'vocabulary_cap':self.vocabulary_size,
                'training_documents_sha256':self.training_sha256,'training_log_likelihood_history':self.history,
                'method':{'version':1,'em_updates':max(0,len(self.history)-1),'smoothing':1e-12,'maximum_piece_characters':8,
                          'candidate_selection':'frequency_times_length_minus_one_then_lexical','minimum_substring_frequency':2,
                          'pruning':False,'cross_word_pieces':False,'cross_document_pieces':False,'subword_sampling':False,
                          'encoding':'viterbi_highest_probability','tie_break':'lowest_final_piece_id_then_start',
                          'special_tokens':False,'uncovered_characters':'reject_without_refitting'}}

    @classmethod
    def restore(cls,artifact):
        if not isinstance(artifact,dict) or set(artifact)!={'format','schema_version','normalization','base_alphabet','alphabet','pieces','probabilities','vocabulary_cap','training_documents_sha256','training_log_likelihood_history','method'}:
            raise ValueError('Unsupported Unigram artifact fields.')
        model=cls(artifact['alphabet'],artifact['pieces'],artifact['probabilities'],artifact['training_documents_sha256'],artifact['vocabulary_cap'],artifact['training_log_likelihood_history'])
        if digest(artifact)!=digest(model.artifact()) or type(artifact['schema_version']) is not int:raise ValueError('Unsupported Unigram artifact method/version.')
        return model
