"""Bounded version-1 whitespace tokenizer for local decoder pipeline fixtures."""
import hashlib
import json
import unicodedata


class Tokenizer:
    def __init__(self, vocabulary):
        if (not isinstance(vocabulary, list) or not 4 <= len(vocabulary) <= 256
                or any(not isinstance(token, str) or not token or len(token) > 64
                       or any(character.isspace() for character in token)
                       or unicodedata.normalize('NFC', token) != token for token in vocabulary)
                or vocabulary != sorted(set(vocabulary))):
            raise ValueError('Tokenizer requires 4 to 256 sorted, unique NFC words of at most 64 characters.')
        self._vocabulary = tuple(vocabulary)
        self._ids = {word: index for index, word in enumerate(vocabulary)}

    @property
    def vocabulary(self):
        return list(self._vocabulary)

    @staticmethod
    def words(text):
        if not isinstance(text, str) or not 1 <= len(text) <= 65536:
            raise ValueError('Provide local text between 1 and 65536 characters.')
        words = unicodedata.normalize('NFC', text).split()
        if not words or len(words) > 4096 or any(len(word) > 64 for word in words):
            raise ValueError('Text requires 1 to 4096 words of at most 64 characters.')
        return words

    @classmethod
    def fit(cls, training_documents):
        if not isinstance(training_documents, list) or not 1 <= len(training_documents) <= 256:
            raise ValueError('Provide 1 to 256 training documents for this local tokenizer.')
        vocabulary = set()
        for document in training_documents:
            for word in cls.words(document):
                vocabulary.add(word)
                if len(vocabulary) > 256:
                    raise ValueError('This local tokenizer supports at most 256 vocabulary words.')
        return cls(sorted(vocabulary))

    def encode(self, text):
        words = self.words(text)
        if any(word not in self._ids for word in words):
            raise ValueError('Text contains words outside the training vocabulary; this tokenizer does not refit on evaluation text.')
        return [self._ids[word] for word in words]

    def decode(self, tokens):
        if (not isinstance(tokens, list) or not 1 <= len(tokens) <= 4096
                or any(type(token) is not int or not 0 <= token < len(self._vocabulary) for token in tokens)):
            raise ValueError('Provide bounded integer token IDs from this vocabulary.')
        return ' '.join(self._vocabulary[token] for token in tokens)

    def artifact(self):
        return {'format': 'almg-whitespace-tokenizer-v1', 'schema_version': 1,
                'normalization': 'NFC', 'whitespace': 'split_then_join', 'vocabulary': self.vocabulary}

    @classmethod
    def restore(cls, artifact):
        if isinstance(artifact, dict) and artifact.get('format') == 'almg-approved-stream-training-tokenizer-v1':
            if __package__:
                from .decoder_stream_training_tokenizer import StreamTrainingTokenizer
            else:
                from decoder_stream_training_tokenizer import StreamTrainingTokenizer
            return StreamTrainingTokenizer.restore(artifact)
        if isinstance(artifact, dict) and artifact.get('format') == 'almg-reviewed-stream-model-tokenizer-v1':
            if __package__:
                from .decoder_stream_model_tokenizer import StreamModelTokenizer
            else:
                from decoder_stream_model_tokenizer import StreamModelTokenizer
            return StreamModelTokenizer.restore(artifact)
        if isinstance(artifact, dict) and artifact.get('format') == 'almg-reviewed-model-tokenizer-v1':
            if __package__:
                from .decoder_model_tokenizer import ModelTokenizer
            else:
                from decoder_model_tokenizer import ModelTokenizer
            return ModelTokenizer.restore(artifact)
        if isinstance(artifact, dict) and artifact.get('format') == 'almg-utf8-byte-tokenizer-v1':
            return ByteTokenizer.restore(artifact)
        if (not isinstance(artifact, dict) or set(artifact) != {'format', 'schema_version', 'normalization', 'whitespace', 'vocabulary'}
                or artifact.get('format') != 'almg-whitespace-tokenizer-v1'
                or type(artifact.get('schema_version')) is not int or artifact['schema_version'] != 1
                or artifact.get('normalization') != 'NFC' or artifact.get('whitespace') != 'split_then_join'):
            raise ValueError('Unsupported tokenizer artifact.')
        return cls(artifact['vocabulary'])

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.artifact(), sort_keys=True, ensure_ascii=False,
                                        separators=(',', ':')).encode('utf-8')).hexdigest()


class ByteTokenizer(Tokenizer):
    """Fixed UTF-8 byte alphabet; only training provenance is fitted."""
    def __init__(self, training_sha256):
        import re
        if not isinstance(training_sha256, str) or not re.fullmatch('[a-f0-9]{64}', training_sha256):
            raise ValueError('Byte tokenizer requires a training-document revision.')
        self.training_sha256 = training_sha256

    @property
    def vocabulary(self):
        return [f'<0x{value:02x}>' for value in range(256)]

    @classmethod
    def fit(cls, training_documents):
        if not isinstance(training_documents, list) or not 1 <= len(training_documents) <= 256:
            raise ValueError('Provide 1 to 256 training documents for this local tokenizer.')
        normalized = []
        for text in training_documents:
            if not isinstance(text, str):
                raise ValueError('Byte tokenization requires UTF-8 text.')
            text = unicodedata.normalize('NFC', text)
            cls('0'*64).encode(text)
            normalized.append(text)
        revision = hashlib.sha256(json.dumps(normalized, ensure_ascii=False, separators=(',', ':')).encode('utf-8')).hexdigest()
        return cls(revision)

    def encode(self, text):
        if not isinstance(text, str) or not 1 <= len(text) <= 65536:
            raise ValueError('Provide bounded UTF-8 text for byte tokenization.')
        tokens = list(unicodedata.normalize('NFC', text).encode('utf-8'))
        if not 1 <= len(tokens) <= 4096:
            raise ValueError('Byte tokenization supports 1 to 4096 encoded bytes per document.')
        return tokens

    def decode(self, tokens):
        if (not isinstance(tokens, list) or not 1 <= len(tokens) <= 4096
                or any(type(token) is not int or not 0 <= token <= 255 for token in tokens)):
            raise ValueError('Provide 1 to 4096 integer byte token IDs.')
        return bytes(tokens).decode('utf-8', errors='replace')

    def artifact(self):
        return {'format': 'almg-utf8-byte-tokenizer-v1', 'schema_version': 1,
                'normalization': 'NFC', 'encoding': 'utf-8', 'decoding_errors': 'replace',
                'training_documents_sha256': self.training_sha256}

    @classmethod
    def restore(cls, artifact):
        if (not isinstance(artifact, dict)
                or set(artifact) != {'format', 'schema_version', 'normalization', 'encoding', 'decoding_errors', 'training_documents_sha256'}
                or artifact.get('format') != 'almg-utf8-byte-tokenizer-v1'
                or type(artifact.get('schema_version')) is not int or artifact['schema_version'] != 1
                or artifact.get('normalization') != 'NFC' or artifact.get('encoding') != 'utf-8'
                or artifact.get('decoding_errors') != 'replace'):
            raise ValueError('Unsupported byte tokenizer artifact.')
        return cls(artifact['training_documents_sha256'])
