"""Probe G: ReportVectorStore.query indexing of empty Chroma result.

If Chroma returns {"ids": []} (no nesting), the line
    res.get("ids", [[]])[0]
becomes [][0] → IndexError. The default `[[]]` only kicks in if "ids" is
absent entirely. Verify behaviour.
"""
from __future__ import annotations


def main() -> int:
    # Simulate Chroma's actual return shape for "no documents in collection".
    # In practice Chroma returns nested empty lists like {"ids": [[]]} but a
    # corrupted/old DB may return {"ids": []}. Either way, we audit defensively.
    issues = 0
    for label, res in [
        ("standard empty",     {"ids": [[]],   "documents": [[]],   "metadatas": [[]]}),
        ("flattened empty",    {"ids": [],     "documents": [],     "metadatas": []}),
        ("missing keys",       {}),
    ]:
        try:
            ids = res.get("ids", [[]])[0]
            docs = res.get("documents", [[]])[0]
            metas = res.get("metadatas", [[]])[0]
            print(f"[probe_g] {label:20s}: ok ids={ids} docs={docs} metas={metas}")
        except Exception as e:
            print(f"[probe_g] {label:20s}: CRASH {type(e).__name__}: {e}")
            issues = 1
    if issues:
        print("[probe_g] CONFIRMED: query() can IndexError on flattened empty result")
    return issues


if __name__ == "__main__":
    raise SystemExit(main())
