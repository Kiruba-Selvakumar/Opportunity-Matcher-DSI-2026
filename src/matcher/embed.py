"""Encoders and profile vectors. Falls back to character TF-IDF so it runs offline."""
from __future__ import annotations

import json
import os

import numpy as np

from .config import PATHS
from .schema import Opportunity, Student
from .skills import load_vocab, normalize_opportunity, normalize_student, technical


class Encoder:
    method = "tfidf"
    dim = 0

    def encode(self, texts: list[str]) -> np.ndarray:  # pragma: no cover - interface
        raise NotImplementedError


class TfidfEncoder(Encoder):
    method = "tfidf"

    def __init__(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        self.vec.fit([s.lower() for s in load_vocab()])
        self.dim = len(self.vec.vocabulary_)

    def encode(self, texts: list[str]) -> np.ndarray:
        return self.vec.transform([t.lower() for t in texts]).toarray().astype(np.float32)


class MiniLMEncoder(Encoder):
    method = "minilm"

    def __init__(self) -> None:
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        self.dim = self.model.get_sentence_embedding_dimension()

    def encode(self, texts: list[str]) -> np.ndarray:
        v = self.model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)
        return np.asarray(v, dtype=np.float32)


_encoders: dict[str, Encoder] = {}


def get_encoder() -> Encoder:
    """EMBEDDINGS=auto tries MiniLM then TF-IDF; minilm forces the model; tfidf forces the fallback."""
    mode = os.environ.get("EMBEDDINGS", "auto").strip().lower()
    if mode in _encoders:
        return _encoders[mode]
    enc: Encoder | None = None
    if mode in ("auto", "minilm"):
        try:
            enc = MiniLMEncoder()
        except Exception:
            if mode == "minilm":
                raise
    _encoders[mode] = enc or TfidfEncoder()
    return _encoders[mode]


def _l2(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 0 else np.zeros_like(v)


def profile_vector(skills: list[str], enc: Encoder) -> np.ndarray:
    """Zero vector for no skills. TF-IDF encodes the joined text; MiniLM averages the skill vectors."""
    if not skills:
        return np.zeros(enc.dim, dtype=np.float32)
    if enc.method == "tfidf":
        return _l2(enc.encode([" ".join(skills)])[0])
    return _l2(enc.encode(skills).mean(axis=0))


def build_all() -> dict:
    """Write normalized_skills.json and vectors.npz from the clean files."""
    students = [Student(**d) for d in json.loads(PATHS["students"].read_text())]
    opps = [Opportunity(**d) for d in json.loads(PATHS["opportunities"].read_text())]
    enc = get_encoder()
    norm = {"students": {s.student_id: normalize_student(s, enc) for s in students},
            "opportunities": {o.opp_id: normalize_opportunity(o, enc) for o in opps}}
    PATHS["normalized"].parent.mkdir(parents=True, exist_ok=True)
    PATHS["normalized"].write_text(json.dumps(norm, indent=1))
    s_vecs = np.stack([profile_vector(technical(norm["students"][s.student_id]["skills"]), enc) for s in students])
    o_vecs = np.stack([profile_vector(technical(norm["opportunities"][o.opp_id]["skills"]), enc) for o in opps])
    np.savez(PATHS["vectors"], student_ids=np.array([s.student_id for s in students]), student_vecs=s_vecs,
             opp_ids=np.array([o.opp_id for o in opps]), opp_vecs=o_vecs, method=np.array(enc.method))
    return norm


def main() -> None:
    norm = build_all()
    print(f"normalized {len(norm['students'])} students and {len(norm['opportunities'])} opportunities "
          f"({get_encoder().method} vectors)")


if __name__ == "__main__":
    main()
