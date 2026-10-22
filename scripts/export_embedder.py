"""Export the WordLlama tokenizer and embedding matrix into artifacts/<pilot>/embedder.npz
so the API can run without the wordllama package (needs only numpy + tokenizers).

    python scripts/export_embedder.py --pilot pilot2
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from sopilot.scorers import Embedder  # noqa: E402


def main(pilot):
    import wordllama
    from safetensors.numpy import load_file
    base = Path(wordllama.__file__).parent
    tok = json.loads((base / "tokenizers" / "l2_supercat_tokenizer_config.json").read_text())
    mat = load_file(str(base / "weights" / "l2_supercat_256.safetensors"))["embedding.weight"].astype(np.float16)
    out = ROOT / "artifacts" / pilot / "embedder.npz"
    np.savez_compressed(out, tokenizer=np.array(json.dumps(tok)), matrix=mat)
    a = Embedder(json.dumps(tok), mat.astype(np.float32)).embed(["swollen battery on my Aero 15", "Gdzie jest moja część?"])
    b = Embedder.from_wordllama().embed(["swollen battery on my Aero 15", "Gdzie jest moja część?"])
    print(out, round(out.stat().st_size / 1e6, 1), "MB; max abs diff vs wordllama:", float(np.abs(a - b).max()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", default="pilot2")
    main(ap.parse_args().pilot)
