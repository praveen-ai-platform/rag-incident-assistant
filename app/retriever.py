from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

@dataclass
class DocChunk:
    id: str
    title: str
    text: str

class SimpleTfidfRetriever:
    def __init__(self):
        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._chunks: List[DocChunk] = []
        self._matrix = None

    def ingest(self, docs: List[Dict[str, Any]]):
        self._chunks = [DocChunk(d["id"], d.get("title",""), d["text"]) for d in docs]
        corpus = [f"{c.title}. {c.text}" for c in self._chunks]
        self._matrix = self._vectorizer.fit_transform(corpus)

    def top_k(self, query: str, k: int = 3) -> List[Tuple[DocChunk, float]]:
        if not self._chunks or self._matrix is None:
            return []
        qv = self._vectorizer.transform([query])
        sims = cosine_similarity(qv, self._matrix).flatten()
        idxs = sims.argsort()[::-1][:k]
        return [(self._chunks[i], float(sims[i])) for i in idxs]
