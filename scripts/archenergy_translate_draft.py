# SPDX-License-Identifier: GPL-3.0-or-later
# © 2026 ArchEnergy s.r.o.
"""Prepare OFFLINE Czech candidates for review; never installs cs.json.

Run with .venv/translation-runtime/Scripts/python.exe. Optional development
dependencies: ctranslate2, sacremoses, subword-nmt. Model stays in .venv and
is not bundled with EnergySketch. Protected format fields, HTML, URLs and
newlines are copied literally. All wording still needs editorial review.
"""
import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_czech_translation import load_catalog, placeholders

PROTECTED = re.compile(r"(\{[^{}\r\n]*\}|\n|<[^>]*>|https?://[^\s<>]+|\.[a-zA-Z0-9]{2,5}\b)")


def pieces(text):
    result = []
    for part in PROTECTED.split(text):
        if not part:
            continue
        if PROTECTED.fullmatch(part) or not re.search(r"[a-zA-Z]", part):
            result.append((False, part))
        else:
            match = re.fullmatch(r"(\s*)(.*?)(\s*)", part, re.S)
            result.extend(((False, match[1]), (True, match[2]), (False, match[3])))
    return result


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=root / ".venv/translation-model/translate-en_cs-1_9_6")
    parser.add_argument("--output", type=Path, default=root / "output/archenergy/cs-machine-draft.json")
    args = parser.parse_args()
    import ctranslate2
    from sacremoses import MosesTokenizer, MosesDetokenizer, MosesPunctNormalizer
    from subword_nmt.apply_bpe import BPE
    keys = set()
    for path in sorted((root / "i18n").glob("*.json")):
        if path.stem not in {"en", "cs"}:
            keys.update(load_catalog(path))
    templates = {key: pieces(key) for key in sorted(keys)}
    fragments = sorted({part for parts in templates.values() for translate, part in parts if translate and part})
    cache_path = args.output.with_name("cs-machine-fragments.json")
    cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.is_file() else {}
    pending = [part for part in fragments if part not in cache]
    normalizer, tokenizer, detokenizer = MosesPunctNormalizer("en"), MosesTokenizer("en"), MosesDetokenizer("cs")
    with (args.model / "bpe.model").open(encoding="utf-8") as stream:
        bpe = BPE(stream)
    translator = ctranslate2.Translator(str(args.model / "model"), device="cpu", intra_threads=3, inter_threads=1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for start in range(0, len(pending), 24):
        batch = pending[start:start + 24]
        tokens = [bpe.segment_tokens(tokenizer.tokenize(normalizer.normalize(part), escape=False)) for part in batch]
        results = translator.translate_batch(tokens, beam_size=4, max_decoding_length=768)
        for part, result in zip(batch, results):
            cache[part] = detokenizer.detokenize(" ".join(result.hypotheses[0]).replace("@@ ", "").split())
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Fragments {len(cache)}/{len(fragments)}", flush=True)
    draft = {"_comment": "UNREVIEWED machine draft; not an installed application catalog.",
             "_license": "GPL-3.0-or-later", "_copyright": "© 2026 ArchEnergy s.r.o."}
    for key, parts in templates.items():
        draft[key] = "".join(cache[part] if translate and part else part for translate, part in parts)
    args.output.write_text(json.dumps(draft, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    errors = [key for key in keys if placeholders(key) != placeholders(draft[key]) or
              key.count("\n") != draft[key].count("\n") or (key.strip() and not draft[key].strip())]
    report = {"installed": False, "reviewed": False, "keys": len(keys), "fragments": len(fragments),
              "structural_errors": errors, "identical": [key for key in sorted(keys) if key == draft[key]],
              "model": str(args.model), "reference": "https://data.argosopentech.com/argospm/v1/translate-en_cs-1_9_6.argosmodel"}
    args.output.with_suffix(".review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Draft: {len(keys)} keys, {len(errors)} structural errors. Editorial review REQUIRED.")


if __name__ == "__main__":
    main()
