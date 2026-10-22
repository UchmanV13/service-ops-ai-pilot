"""TF-IDF featurization that runs on numpy alone.

Training uses scikit-learn; this module reproduces sklearn's TfidfVectorizer
(word 1-2 grams and char_wb 2-5 grams, sublinear tf, smooth idf, l2 norm) so the
deployed API needs no scikit-learn. tests/test_textvec.py checks they agree.
"""
from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

_TOKEN = re.compile(r"(?u)\b\w\w+\b")
_WS = re.compile(r"\s\s+")


def word_ngrams(doc: str, ngram=(1, 2)):
    toks = _TOKEN.findall(doc.lower())
    lo, hi = ngram
    out = []
    for n in range(lo, hi + 1):
        for i in range(len(toks) - n + 1):
            out.append(" ".join(toks[i:i + n]))
    return out


def char_wb_ngrams(doc: str, ngram=(2, 5)):
    doc = _WS.sub(" ", doc.lower())
    lo, hi = ngram
    out = []
    for w in doc.split():
        w = " " + w + " "
        wl = len(w)
        for n in range(lo, hi + 1):
            offset = 0
            out.append(w[offset:offset + n])
            while offset + n < wl:
                offset += 1
                out.append(w[offset:offset + n])
            if offset == 0:
                break
    return out


class Block:
    """One vectorizer block exported from sklearn: vocabulary + idf."""

    def __init__(self, kind, ngram, vocab, idf):
        self.kind, self.ngram = kind, tuple(ngram)
        self.vocab = vocab
        self.idf = np.asarray(idf, dtype=np.float64)

    def transform_one(self, doc: str):
        grams = word_ngrams(doc, self.ngram) if self.kind == "word" else char_wb_ngrams(doc, self.ngram)
        counts = Counter(g for g in grams if g in self.vocab)
        if not counts:
            return np.array([], dtype=np.int64), np.array([], dtype=np.float64)
        idx = np.fromiter((self.vocab[g] for g in counts), dtype=np.int64, count=len(counts))
        tf = np.fromiter((1.0 + math.log(c) for c in counts.values()), dtype=np.float64, count=len(counts))
        val = tf * self.idf[idx]
        norm = np.sqrt((val ** 2).sum())
        return idx, (val / norm if norm > 0 else val)


class TfidfLinear:
    """Multinomial logistic regression on stacked TF-IDF blocks."""

    def __init__(self, blocks, coef, intercept, classes):
        self.blocks = blocks
        self.coef = np.asarray(coef, dtype=np.float64)        # (K, D)
        self.intercept = np.asarray(intercept, dtype=np.float64)
        self.classes = list(classes)
        self.offsets = np.cumsum([0] + [len(b.idf) for b in blocks])[:-1]

    def logits(self, docs):
        out = np.tile(self.intercept, (len(docs), 1))
        for r, d in enumerate(docs):
            for b, off in zip(self.blocks, self.offsets):
                idx, val = b.transform_one(d)
                if len(idx):
                    out[r] += self.coef[:, idx + off] @ val
        return out
