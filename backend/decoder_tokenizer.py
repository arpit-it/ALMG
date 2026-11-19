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
        if (not isinstance(artifact, dict) or set(artifact) != {'format', 'schema_version', 'normalization', 'whitespace', 'vocabulary'}
                or artifact.get('format') != 'almg-whitespace-tokenizer-v1'
                or type(artifact.get('schema_version')) is not int or artifact['schema_version'] != 1
                or artifact.get('normalization') != 'NFC' or artifact.get('whitespace') != 'split_then_join'):
            raise ValueError('Unsupported tokenizer artifact.')
        return cls(artifact['vocabulary'])

    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.artifact(), sort_keys=True, ensure_ascii=False,
                                        separators=(',', ':')).encode('utf-8')).hexdigest()
