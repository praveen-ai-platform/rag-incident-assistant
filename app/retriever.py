"""TF-IDF evidence retrieval with atomic JSON persistence and bounded indexing."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from threading import RLock
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

@dataclass(frozen=True)
class Chunk:
    document_id: str
    chunk_id: str
    title: str
    text: str

class SimpleTfidfRetriever:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self._lock = RLock()
        self._chunks, self._vectorizer, self._matrix = [], None, None
        if self.path and self.path.exists():
            self.ingest(json.loads(self.path.read_text(encoding='utf-8')), persist=False)

    def ingest(self, docs, persist=True):
        if not docs or len(docs) > 200:
            raise ValueError('Provide between 1 and 200 documents')
        if len({d['id'] for d in docs}) != len(docs):
            raise ValueError('Document IDs must be unique')
        chunks = []
        for doc in docs:
            if not doc['id'].strip() or not doc['text'].strip() or len(doc['text']) > 20000:
                raise ValueError('Documents require an ID and 1 to 20000 characters of text')
            words = doc['text'].split()
            for start in range(0, len(words), 100):
                chunks.append(Chunk(doc['id'], f"{doc['id']}:{start//100}", doc.get('title', ''), ' '.join(words[start:start+120])))
        if len(chunks) > 2000:
            raise ValueError('Corpus exceeds the 2000-chunk limit')
        vectorizer = TfidfVectorizer(stop_words='english', ngram_range=(1, 2), max_features=50000)
        try:
            matrix = vectorizer.fit_transform([f'{c.title}. {c.text}' for c in chunks])
        except ValueError as exc:
            raise ValueError('Documents contain no searchable terms') from exc
        with self._lock:
            if persist and self.path:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                handle, temporary = tempfile.mkstemp(dir=self.path.parent, suffix='.tmp')
                try:
                    with os.fdopen(handle, 'w', encoding='utf-8') as stream:
                        json.dump(docs, stream, ensure_ascii=False)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, self.path)
                finally:
                    Path(temporary).unlink(missing_ok=True)
            self._chunks, self._vectorizer, self._matrix = chunks, vectorizer, matrix
        return len(chunks)

    @property
    def ready(self):
        with self._lock:
            return self._matrix is not None

    def top_k(self, query, k=3, min_score=0.1):
        if not 1 <= k <= 10 or not 0 < min_score <= 1:
            raise ValueError('Invalid retrieval parameters')
        with self._lock:
            if self._matrix is None:
                return []
            scores = cosine_similarity(self._vectorizer.transform([query]), self._matrix).flatten()
            indices = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), self._chunks[i].chunk_id))
            return [(self._chunks[i], float(scores[i])) for i in indices if scores[i] >= min_score][:k]
