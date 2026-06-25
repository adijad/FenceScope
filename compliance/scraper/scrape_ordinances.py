"""
scrape_ordinances.py
--------------------
Chromium (Playwright) scraper for municipal fence ordinances on Municode.

WHY CHROMIUM: Municode is a JavaScript single-page app. A plain requests.get()
returns an empty shell. Playwright runs the JS so the ordinance text renders.

MODES:
  --discover : for each city, search the keyword, RANK the candidate sections,
               auto-write the best fence_url into cities.yaml (original backed up
               to cities.yaml.bak), and flag any city it wasn't confident about.
  (default)  : for each city that now has a fence_url, open it, extract the
               rendered section text, and save corpus/<state>_<city>.md.

WORKFLOW:
    python scrape_ordinances.py --discover    # fills fence_url in cities.yaml
    # review the flagged cities, fix any wrong picks by hand
    python scrape_ordinances.py               # extract the text
"""

import argparse
import re
import shutil
import time
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

# ---- config ----------------------------------------------------------------
CITIES_FILE = "cities.yaml"
OUT_DIR = Path("../corpus")        # write into compliance/corpus/ (one level up)
DELAY_SECONDS = 3
PAGE_TIMEOUT_MS = 30_000
HEADLESS = False                   # watch the browser on first runs; flip to True later
CONTENT_SELECTOR = "div.chunks, mcc-codes-content, section.chunk-content, div[ng-bind-html]"
SEARCH_INPUT_SELECTOR = "input[type='search'], input[placeholder*='Search']"

# ---- candidate ranking ------------------------------------------------------
# We want the DIMENSIONAL zoning fence rule (height/setback/yard), NOT nuisance,
# criminal, electric, or definition sections. Score candidates accordingly.
GOOD_PHRASES = ("fences and walls", "fences, walls", "walls and fences",
                "fence requirements", "fence regulations", "fences, walls, arbors")
ZONING_TOKENS = ("zoning", "zoor", "_zo_", "ch36.2zo", "tit20zo", "blzoor",
                 "planning_code", "tit17pl", "plde", "ch3zo")
BAD_WORDS = ("electric", "electrified", "charged", "barbed", "pointed",
             "pulling down", "removal", "repair", "defacement", "obstruction",
             "nuisance", "traffic", "hazard", "spite", "dangerous", "restricted")
CONFIDENCE_THRESHOLD = 4           # don't write a pick weaker than this


def score_candidate(label, url):
    t, n = label.lower(), url.lower()
    s = 0
    if any(g in t for g in GOOD_PHRASES):
        s += 6
    elif "fence" in t:
        s += 1
    if any(z in n for z in ZONING_TOKENS):
        s += 4
    if "zoning" in t:
        s += 2
    for b in BAD_WORDS:
        if b in t:
            s -= 6
    if t.strip().rstrip(".") == "fence" or "ch20.200de" in n or "_de_" in n:
        s -= 4
    if t.startswith(("chapter", "title", "appendix")):
        s -= 2
    return s


def collect_candidates(page):
    out, seen = [], set()
    for a in page.query_selector_all("a[href*='nodeId=']")[:15]:
        href = a.get_attribute("href") or ""
        label = (a.inner_text() or "").strip().replace("\n", " ")
        if not href or href in seen:
            continue
        if re.search(r"(fence|zoning|site dev|accessory|wall)", label, re.I):
            seen.add(href)
            full = href if href.startswith("http") else "https://library.municode.com" + href
            out.append((label, full))
    return out


def discover(cities, browser):
    page = browser.new_page()
    summary = []
    for c in cities:
        state, city = c["state"], c["city"]
        term = c.get("search_term", "fence")
        print(f"\n=== {state.upper()} / {city}  (search: '{term}') ===")

        if c.get("fence_url"):
            print(f"  KEEP (already set): {c['fence_url']}")
            summary.append((state, city, "kept", c["fence_url"]))
            continue

        try:
            root = f"https://library.municode.com/{state}/{city}/codes/code_of_ordinances"
            page.goto(root, timeout=PAGE_TIMEOUT_MS, wait_until="networkidle")
            page.wait_for_selector(SEARCH_INPUT_SELECTOR, timeout=10000)
            box = page.query_selector(SEARCH_INPUT_SELECTOR)
            box.fill(term)
            box.press("Enter")
            page.wait_for_timeout(4000)

            cands = collect_candidates(page)
            ranked = sorted(((score_candidate(l, u), l, u) for l, u in cands), reverse=True)
            for sc, l, u in ranked:
                print(f"  [{sc:>3}] {l[:55]!r}\n        {u}")

            if ranked and ranked[0][0] >= CONFIDENCE_THRESHOLD:
                best = ranked[0][2]
                c["fence_url"] = best
                print(f"  --> CHOSEN (score {ranked[0][0]}): {best}")
                summary.append((state, city, "auto", best))
            else:
                top = ranked[0][0] if ranked else "none"
                print(f"  --> NO CONFIDENT PICK (best score {top}). Set fence_url by hand.")
                summary.append((state, city, "REVIEW", ""))
        except Exception as e:
            print(f"  ERROR: {e}")
            summary.append((state, city, "ERROR (not on Municode?)", ""))
        time.sleep(DELAY_SECONDS)
    page.close()
    return summary


def write_cities(cfg):
    shutil.copy(CITIES_FILE, CITIES_FILE + ".bak")
    with open(CITIES_FILE, "w", encoding="utf-8") as f:
        f.write("# Auto-updated by scrape_ordinances.py --discover.\n")
        f.write("# Original backed up to cities.yaml.bak.\n")
        f.write("# Review any city marked REVIEW/ERROR in the run summary before extracting.\n\n")
        yaml.safe_dump(cfg, f, sort_keys=False, default_flow_style=False, allow_unicode=True)


def print_summary(summary):
    print("\n" + "=" * 60 + "\nSUMMARY\n" + "=" * 60)
    for state, city, status, url in summary:
        print(f"  {status:<28} {state}/{city}")
    print(f"\n  cities.yaml updated. Backup at {CITIES_FILE}.bak")
    print("  Next: review REVIEW/ERROR rows, then run:  python scrape_ordinances.py")


def extract_text(page):
    for sel in CONTENT_SELECTOR.split(", "):
        try:
            page.wait_for_selector(sel, timeout=8000)
            nodes = page.query_selector_all(sel)
            text = "\n\n".join(n.inner_text() for n in nodes if n.inner_text().strip())
            if len(text) > 200:
                return text
        except Exception:
            continue
    return page.inner_text("body")


def extract(cities, browser):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    page = browser.new_page()
    for c in cities:
        url = c.get("fence_url")
        name = f"{c['state']}_{c['city']}"
        if not url:
            print(f"SKIP {name}: no fence_url (run --discover, or set it by hand).")
            continue
        print(f"FETCH {name} ...")
        try:
            page.goto(url, timeout=PAGE_TIMEOUT_MS, wait_until="networkidle")
            page.wait_for_timeout(2500)
            text = extract_text(page)
            out = OUT_DIR / f"{name}.md"
            out.write_text(
                f"---\n"
                f"jurisdiction: \"{c['city'].replace('_',' ').title()}, {c['state'].upper()}\"\n"
                f"source_url: \"{url}\"\n"
                f"retrieved: \"{time.strftime('%Y-%m-%d')}\"\n"
                f"disclaimer: \"Informational pre-check only. Not the definitive authority. Verify with the municipality.\"\n"
                f"---\n\n# {c['city'].replace('_',' ').title()} — Fence / Zoning Provisions\n\n{text}\n",
                encoding="utf-8",
            )
            print(f"   saved {out}  ({len(text)} chars)")
        except Exception as e:
            print(f"   ERROR {name}: {e}")
        time.sleep(DELAY_SECONDS)
    page.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true",
                    help="search, rank candidates, and write best fence_url into cities.yaml")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(CITIES_FILE).read_text())
    cities = [c for group in cfg.values() for c in group]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        try:
            if args.discover:
                summary = discover(cities, browser)
                write_cities(cfg)
                print_summary(summary)
            else:
                extract(cities, browser)
        finally:
            browser.close()


if __name__ == "__main__":
    main()