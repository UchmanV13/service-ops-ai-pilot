import numpy as np
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer

from sopilot.textvec import Block, TfidfLinear

DOCS = ["My Aero 15 won't turn on at all", "Where is my refund? ORD-12345678", "the  battery is   swelling!!",
        "Mój laptop się nie włącza", "Wi-Fi drops every few minutes on the Tower T5", "x"]


def test_numpy_tfidf_matches_sklearn():
    vw = TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, min_df=1).fit(DOCS)
    vc = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=1).fit(DOCS)
    X = hstack([vw.transform(DOCS), vc.transform(DOCS)]).toarray()
    rng = np.random.default_rng(0)
    coef = rng.normal(size=(3, X.shape[1]))
    icpt = rng.normal(size=3)
    blocks = [Block("word", (1, 2), vw.vocabulary_, vw.idf_), Block("char_wb", (2, 5), vc.vocabulary_, vc.idf_)]
    ours = TfidfLinear(blocks, coef, icpt, ["a", "b", "c"]).logits(DOCS)
    np.testing.assert_allclose(ours, X @ coef.T + icpt, atol=1e-9)
