"""
build_rules.py
--------------
Turns raw corpus (corpus/<city>.md) into structured, GROUNDED fence rules
(rules/<city>.json) using an LLM, then verifies every quote actually appears
in the source text before trusting it.

Place in compliance/, run from compliance/:
    python build_rules.py --file corpus/ca_fresno.md   # test one
    python build_rules.py                              # all

Needs OPENAI_API_KEY in .env. Model via OPENAI_MODEL (default gpt-4o-mini).
"""

import argparse
import difflib
import json
import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# build_rules.py
CORPUS_DIR = Path(__file__).parent / "corpus"
RULES_DIR = Path(__file__).parent / "rules"
WINDOW_CHARS = 9000
KEYWORDS = ("fence", "wall", "height", "feet", "foot", "inches", "yard",
            "setback", "corner", "sight", "barbed", "chain link", "solid", "open")

# Canonical vocab the rest of the app understands. Keep extraction inside this.
LOCATIONS = "front | side | back | street_side | any"
RESULTS = "fail | needs_permit | needs_review"


def find_fence_window(text: str) -> str:
    low = text.lower()
    if len(text) <= WINDOW_CHARS:
        return text
    best_start, best_score = 0, -1
    for start in range(0, len(text) - WINDOW_CHARS, 500):
        window = low[start:start + WINDOW_CHARS]
        score = sum(window.count(k) for k in KEYWORDS)
        if score > best_score:
            best_score, best_start = score, start
    return text[best_start:best_start + WINDOW_CHARS]


SYSTEM_PROMPT = f"""You extract residential fence rules from a zoning ordinance excerpt.
Output ONLY JSON.

For each rule:
{{
  "rule_id": "kebab-case",
  "schema_fields": ["height_ft","location","material","corner_lot","pct_open","near_pool"],  // only those used
  "location": one of [{LOCATIONS}],
  "rule_summary": "one plain sentence",
  "verbatim_text": "EXACT quote copied character-for-character from the excerpt (<=30 words)",
  "verdict_logic": "WHEN <field op value [and ...]> THEN <{RESULTS}>",
  "confidence": 0.0-1.0
}}

STRICT RULES:
- verbatim_text MUST be copied verbatim from the excerpt. Never paraphrase or write your
  own sentence. If you cannot find an exact supporting quote, DO NOT output that rule.
- "location" MUST be one of: {LOCATIONS}. Do not invent values like "interior" or "rear"
  (use "back"); "street_side" only for a corner street-facing side.
- Avoid contradictions. If there is a GENERAL maximum height AND specific lower limits for
  certain yards, output the specific ones with their exact location, and give the general
  one location "any" with rule_summary noting it is the default unless a specific yard applies.
- verdict_logic = exactly one WHEN/THEN with one result. Use parentheses if combining.
- Only residential dimensional rules a fence contractor checks. Invent nothing.

Return: {{"rules": [ ... ]}}"""


def extract_rules(section_text: str, jurisdiction: str) -> list:
    resp = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Jurisdiction: {jurisdiction}\n\nEXCERPT:\n{section_text}"},
        ],
    )
    return json.loads(resp.choices[0].message.content).get("rules", [])


# ---- GROUNDING: does the quote actually exist in the source? ----------------
def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", s.lower())).strip()


def is_grounded(quote: str, source: str, min_ratio: float = 0.6) -> bool:
    """True only if a long contiguous run of the quote appears in the source.
    Catches paraphrased / invented 'verbatim' text."""
    q, s = _norm(quote), _norm(source)
    if not q:
        return False
    if q in s:
        return True
    m = difflib.SequenceMatcher(None, q, s).find_longest_match(0, len(q), 0, len(s))
    return (m.size / len(q)) >= min_ratio


def parse_frontmatter(md: str):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", md, re.S)
    if not m:
        return {}, md
    return yaml.safe_load(m.group(1)) or {}, m.group(2)


def process_file(path: Path) -> dict:
    meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
    jurisdiction = meta.get("jurisdiction", path.stem)
    source_url = meta.get("source_url", "")

    window = find_fence_window(body)
    print(f"  isolated {len(window)} chars from {len(body)}")
    rules = extract_rules(window, jurisdiction)

    flags = []
    for r in rules:
        r["source_url"] = source_url
        grounded = is_grounded(r.get("verbatim_text", ""), window)
        r["grounded"] = grounded
        if not grounded:
            r["confidence"] = min(r.get("confidence", 0.5), 0.4)
            flags.append(f"UNGROUNDED quote: {r['rule_id']}")
        loc = r.get("location", "any")
        if loc not in [x.strip() for x in LOCATIONS.split("|")]:
            flags.append(f"BAD location '{loc}': {r['rule_id']}")

    return {
        "jurisdiction": jurisdiction,
        "jurisdiction_id": path.stem,
        "source_url": source_url,
        "rule_count": len(rules),
        "flags": flags,
        "rules": rules,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file")
    args = ap.parse_args()
    RULES_DIR.mkdir(exist_ok=True)
    files = [Path(args.file)] if args.file else sorted(CORPUS_DIR.glob("*.md"))
    for path in files:
        print(f"\nPROCESS {path.name}")
        try:
            result = process_file(path)
            out = RULES_DIR / f"{path.stem}.json"
            out.write_text(json.dumps(result, indent=2), encoding="utf-8")
            tag = f"{result['rule_count']} rules"
            if result["flags"]:
                tag += f", {len(result['flags'])} FLAGS"
            print(f"  -> {out}  ({tag})")
            for f in result["flags"]:
                print(f"     ! {f}")
        except Exception as e:
            print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()