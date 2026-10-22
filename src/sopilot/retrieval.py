"""Hybrid retrieval over the knowledge base: BM25 plus embedding cosine."""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

_TOK = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or to of for on in is it my i you your with this that be are was at by from as if".split())


def toks(text: str):
    return [t for t in _TOK.findall(text.lower()) if t not in _STOP]


class BM25:
    def __init__(self, docs, k1=1.4, b=0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(toks(d)) for d in docs]
        self.len = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.avg = self.len.mean()
        df = Counter(t for d in self.docs for t in d)
        n = len(docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str):
        q = toks(query)
        out = np.zeros(len(self.docs))
        for i, d in enumerate(self.docs):
            s = 0.0
            for t in q:
                f = d.get(t, 0)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
            out[i] = s
        return out


class Retriever:
    def __init__(self, articles, embedder=None, w_bm25=0.5):
        self.articles = articles
        self.ids = [a["id"] for a in articles]
        self.texts = [self._doc(a) for a in articles]
        self.bm25 = BM25(self.texts)
        self.embedder = embedder
        self.w = w_bm25
        self.E = embedder.embed(self.texts) if embedder is not None else None

    @staticmethod
    def _doc(a):
        return " ".join([a["title"], a["title"], a["summary"], " ".join(a["steps"]), " ".join(a["intents"]).replace("_", " ")])

    def search(self, query: str, k: int = 3):
        s = self.bm25.scores(query)
        s = s / s.max() if s.max() > 0 else s
        if self.E is not None:
            q = self.embedder.embed([query])[0]
            c = self.E @ q
            c = (c - c.min()) / (c.max() - c.min() + 1e-9)
            s = self.w * s + (1 - self.w) * c
        order = np.argsort(-s)[:k]
        return [{"id": self.ids[i], "title": self.articles[i]["title"], "score": round(float(s[i]), 4)} for i in order]

    def get(self, kb_id):
        return next(a for a in self.articles if a["id"] == kb_id)
