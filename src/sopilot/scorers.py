"""Intent scorers. Each returns calibrated probabilities over INTENT_NAMES.

- RulesScorer: keyword lists written from the labeling guide (no training).
- TfidfScorer: word + character TF-IDF, multinomial logistic regression.
- EmbedScorer: WordLlama static embeddings (pretrained, shipped in the pip
  wheel) mean-pooled, then logistic regression.
- EnsembleScorer: average of calibrated TF-IDF and embedding probabilities.

All scorers see `model_text(text)`: PII redacted and identifiers replaced by
placeholders, so the models learn "an order number is present", not digits.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from .extract import CASE, ORDER, SERVICE_TAG
from .guards import redact_pii
from .taxonomy import INTENT_NAMES
from .textvec import Block, TfidfLinear


def model_text(text: str) -> str:
    t, _ = redact_pii(text)
    t = SERVICE_TAG.sub(" [SERVICETAG] ", t)
    t = ORDER.sub(" [ORDERNO] ", t)
    t = CASE.sub(" [CASENO] ", t)
    return re.sub(r"[ \t]+", " ", t)


def softmax(z, T=1.0):
    z = np.asarray(z, dtype=np.float64) / T
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


class Scorer:
    name = "base"
    temperature = 1.0

    def logits(self, texts):  # pragma: no cover - interface
        raise NotImplementedError

    def predict_proba(self, texts):
        return softmax(self.logits([model_text(t) for t in texts]), self.temperature)


# --------------------------------------------------------------------------- rules
RULE_KEYWORDS = {
    "driver_update": ["driver", "drivers", "device manager", "unknown device", "exclamation", "treiber", "sterownik", "controlador"],
    "bios_update": ["bios", "firmware", "uefi", "flash"],
    "os_recovery": ["factory", "reinstall", "recovery", "reset", "boot loop", "no bootable", "wipe", "fabryczn", "werkseinstell", "fábrica", "neu installieren", "reinstalar"],
    "wifi_drops": ["wi-fi", "wifi", "wireless", "bluetooth", "5 ghz", "internet", "network", "wlan", "sieci"],
    "display_flicker": ["flicker", "flickers", "flashes", "blink", "resolution", "hz", "dims", "jitter", "blurry", "washed out"],
    "slow_performance": ["slow", "sluggish", "lag", "lagging", "freezes", "speed up", "stutter", "takes forever"],
    "no_power": ["won't turn on", "will not power", "won't power", "dead", "power button", "no power", "won't start", "doesn't respond", "nie włącza", "einschalten", "no enciende"],
    "screen_damage": ["cracked", "crack", "shattered", "broken screen", "dropped", "glass", "pressure mark", "pęknięty", "gesprungen", "rota"],
    "keyboard_failure": ["keys", "key ", "keyboard", "space bar", "trackpad", "touchpad", "keycap"],
    "fan_overheating": ["fan", "overheat", "hot", "thermal", "grinding", "rattling", "loud"],
    "dead_pixels": ["pixel", "pixels", "bright dot", "stuck"],
    "dock_not_detected": ["dock", "monitors", "external monitor", "usb devices", "ethernet port"],
    "warranty_status": ["warranty", "covered", "coverage", "entitlement", "gwarancj", "garantie", "garantía"],
    "warranty_extension": ["extend", "renew", "upgrade", "quote", "more years", "additional years"],
    "ownership_transfer": ["transfer", "used", "secondhand", "registered", "previous owner", "new owner"],
    "accidental_damage": ["spilled", "spill", "dropped", "water", "accidental", "fell", "wet", "coffee"],
    "part_order_status": ["replacement part", "tracking", "part", "shipped", "arrived", "courier", "przesyłk", "ersatzteil", "pieza"],
    "wrong_part": ["wrong", "doesn't fit", "doesn't match", "damaged part", "missing", "empty", "different model"],
    "return_label": ["label", "return the", "send back the old", "drop off", "return slip"],
    "schedule_onsite": ["book", "technician visit", "onsite", "appointment", "schedule", "technik", "técnico"],
    "reschedule_visit": ["reschedule", "move the", "change the time", "different slot", "push back", "rebook", "won't be home"],
    "technician_no_show": ["never showed", "nobody came", "no one came", "didn't arrive", "missed", "no-show", "waited"],
    "refund_status": ["refund", "money back", "reimbursement", "zwrot", "erstattung", "reembolso"],
    "invoice_copy": ["invoice", "receipt", "vat", "proof of purchase", "billing document"],
    "duplicate_charge": ["charged twice", "two payments", "duplicate", "double", "extra charge", "billed", "dwukrotnie", "doppelt", "dos veces"],
    "return_request": ["return my", "send it back", "return the", "return window", "changed my mind", "exchange"],
    "enterprise_outage": ["outage", "production", "server is down", "offline", "severity 1", "all our", "entire", "cluster"],
    "raid_degraded": ["raid", "degraded", "disk failed", "drive failure", "array", "rebuild", "predictive failure"],
    "data_loss": ["lost", "files disappeared", "data is gone", "data gone", "corrupted", "wiped", "missing files", "dane", "daten", "datos"],
    "battery_safety": ["swelling", "swollen", "smoke", "smoking", "burning", "sparks", "bulging", "melted", "fire", "puchnie", "rauch", "humo"],
    "security_incident": ["stolen", "hacked", "ransom", "tampered", "unauthorized", "rootkit", "remotely without"],
    "legal_threat": ["lawyer", "attorney", "court", "sue", "legal", "solicitor", "complaint"],
    "privacy_request": ["personal data", "gdpr", "ccpa", "delete my", "erase", "personal information"],
}


class RulesScorer(Scorer):
    name = "rules"

    def __init__(self, temperature=1.0):
        self.temperature = temperature
        self.kw = {k: [w.lower() for w in v] for k, v in RULE_KEYWORDS.items()}

    def logits(self, texts):
        out = np.zeros((len(texts), len(INTENT_NAMES)))
        for r, t in enumerate(texts):
            low = t.lower()
            for c, name in enumerate(INTENT_NAMES):
                out[r, c] = sum(1.0 for w in self.kw[name] if w in low)
        return out * 2.0


# --------------------------------------------------------------------------- tf-idf
class TfidfScorer(Scorer):
    name = "tfidf"

    def __init__(self, model: TfidfLinear, temperature=1.0):
        self.model, self.temperature = model, temperature

    def logits(self, texts):
        return self.model.logits(texts)

    def save(self, path: Path):
        blocks = [{"kind": b.kind, "ngram": list(b.ngram), "vocab": b.vocab, "idf": b.idf.tolist()} for b in self.model.blocks]
        np.savez_compressed(path.with_suffix(".npz"), coef=self.model.coef.astype(np.float32), intercept=self.model.intercept)
        path.with_suffix(".json").write_text(json.dumps({"blocks": blocks, "classes": self.model.classes,
                                                         "temperature": self.temperature}))

    @classmethod
    def load(cls, path: Path):
        meta = json.loads(path.with_suffix(".json").read_text())
        arr = np.load(path.with_suffix(".npz"))
        blocks = [Block(b["kind"], b["ngram"], b["vocab"], b["idf"]) for b in meta["blocks"]]
        return cls(TfidfLinear(blocks, arr["coef"], arr["intercept"], meta["classes"]), meta["temperature"])


# --------------------------------------------------------------------------- embeddings
class Embedder:
    """Mean-pooled WordLlama token embeddings, l2-normalized.

    Same math as wordllama.WordLlamaInference.embed(norm=True); runs on the
    `tokenizers` package plus numpy so it can be deployed without wordllama.
    """

    def __init__(self, tokenizer_json: str, matrix: np.ndarray):
        from tokenizers import Tokenizer
        self.tok = Tokenizer.from_str(tokenizer_json)
        self.tok.no_padding()
        self.tok.no_truncation()
        self.E = matrix.astype(np.float32)

    def embed(self, texts):
        out = np.zeros((len(texts), self.E.shape[1]), dtype=np.float32)
        for i, enc in enumerate(self.tok.encode_batch(list(texts), add_special_tokens=False)):
            ids = np.clip(np.array(enc.ids, dtype=np.int64), 0, self.E.shape[0] - 1)
            if len(ids):
                v = self.E[ids].mean(axis=0)
                n = np.linalg.norm(v)
                out[i] = v / n if n > 0 else v
        return out

    @classmethod
    def from_wordllama(cls, dim=256):
        """Load the weights and tokenizer shipped inside the wordllama wheel."""
        import wordllama
        from safetensors.numpy import load_file
        base = Path(wordllama.__file__).parent
        tok_cfg = json.loads((base / "tokenizers" / "l2_supercat_tokenizer_config.json").read_text())
        tok_json = json.dumps(tok_cfg) if "model" in tok_cfg else None
        if tok_json is None:  # config wraps the tokenizer
            tok_json = json.dumps(tok_cfg.get("tokenizer", tok_cfg))
        w = load_file(str(base / "weights" / "l2_supercat_256.safetensors"))
        mat = w["embedding.weight"][:, :dim]
        return cls(tok_json, mat)


class EmbedScorer(Scorer):
    name = "embed"

    def __init__(self, embedder: Embedder, coef, intercept, temperature=1.0):
        self.embedder = embedder
        self.coef = np.asarray(coef, dtype=np.float64)
        self.intercept = np.asarray(intercept, dtype=np.float64)
        self.temperature = temperature

    def logits(self, texts):
        X = self.embedder.embed(texts).astype(np.float64)
        return X @ self.coef.T + self.intercept


class EnsembleScorer(Scorer):
    name = "ensemble"

    def __init__(self, members, temperature=1.0):
        self.members, self.temperature = members, temperature

    def predict_proba(self, texts):
        mt = [model_text(t) for t in texts]
        ps = [softmax(m.logits(mt), m.temperature) for m in self.members]
        p = np.mean(ps, axis=0)
        if self.temperature != 1.0:
            p = softmax(np.log(np.clip(p, 1e-12, 1)), self.temperature)
        return p


class CriticalScorer:
    """Binary critical vs non-critical: TF-IDF LR and embedding LR, each Platt-scaled, averaged, Platt-scaled again."""

    def __init__(self, tf: TfidfScorer, emb: Embedder, ecoef, eint, cfg):
        self.tf, self.emb, self.ecoef, self.eint, self.cfg = tf, emb, np.asarray(ecoef, float), np.asarray(eint, float), cfg

    @staticmethod
    def _sig(z):
        return 1 / (1 + np.exp(-z))

    def predict(self, texts):
        mt = [model_text(t) for t in texts]
        zt = self.tf.model.logits(mt)[:, 0]
        ze = self.emb.embed(mt).astype(float) @ self.ecoef[0] + self.eint[0]
        a, b = self.cfg["platt_tfidf"]
        c, d = self.cfg["platt_embed"]
        p = (self._sig(a * zt + b) + self._sig(c * ze + d)) / 2
        e, f = self.cfg["platt_avg"]
        return self._sig(e * np.log(p / (1 - p + 1e-12) + 1e-12) + f)

    @classmethod
    def load(cls, art: Path, embedder):
        cfg = json.loads((art / "critical.json").read_text())
        z = np.load(art / "critical_embed.npz")
        return cls(TfidfScorer.load(art / "critical_tfidf"), embedder, z["coef"], z["intercept"], cfg)
