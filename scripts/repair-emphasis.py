#!/usr/bin/env python3
"""Repair bullet lines that were split through a markdown emphasis span.

An earlier bulk pass un-collapsed Transifex's flattened bullet lists, but treated
the closing ``*`` of ``*italic*`` and the second ``*`` of ``**bold**`` as a bullet
marker. One bullet therefore became two, mid-phrase::

    * Créez une matrice des risques en plaçant les *impacts
    * par rapport à une fourchette de probabilité.

The repair is to merge the following bullet line back on, which restores the
emphasis span::

    * Créez une matrice des risques en plaçant les *impacts* par rapport à une
      fourchette de probabilité.

Detection is emphasis balance: a well-formed bullet has an even number of ``*``
characters (outside inline code). An odd count means a span was cut. We merge the
next bullet line and repeat until balanced.

Three independent checks gate every repair; a unit failing any of them is
reported for manual review and never written:

1. **No character loss.** Stripping all whitespace, the repaired field must equal
   the pre-damage seed (default ``be351ce50``) field exactly. This proves the
   merge only removed a newline.
2. **Emphasis balances.** Every bullet in the repaired field has even ``*``.
3. **Structure is plausible.** The repaired field must not have more bullet lines
   than its English source.

Dry run by default -- prints every proposed change and writes nothing.

    python3 scripts/repair-emphasis.py                # report
    python3 scripts/repair-emphasis.py --lang fr      # one language
    python3 scripts/repair-emphasis.py --verbose      # show full before/after
"""

import argparse
import glob
import os
import re
import subprocess
import sys

import yaml

SEED = "be351ce50"
BULLET = re.compile(r"^(\s*)\*\s+(.*)$")
INLINE_CODE = re.compile(r"`[^`]*`")


# --------------------------------------------------------------------------- io

def git_show(rev, path):
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    return r.stdout if r.returncode == 0 else None


def split_frontmatter(text):
    m = re.match(r"^(---\n)(.*?\n)(---\n?)(.*)$", text, re.S)
    return list(m.groups()) if m else None


def load_frontmatter(text):
    parts = split_frontmatter(text)
    if not parts:
        return None
    try:
        d = yaml.safe_load(parts[1])
    except Exception:
        return None
    return d if isinstance(d, dict) else None


# ---------------------------------------------------------------- emphasis math

def star_count(s):
    """Number of '*' outside inline code."""
    return sum(len(r) for r in re.findall(r"\*+", INLINE_CODE.sub("", s)))


def unbalanced(item):
    return star_count(item) % 2 == 1


def bullet_lines(value):
    return sum(1 for ln in value.split("\n") if BULLET.match(ln))


def repair_value(value):
    """Merge lines whose emphasis was cut by a bad bullet split.

    Applies to *any* line with unbalanced emphasis followed by a bullet line —
    not only to bullets. A paragraph ending in a bold run-in heading is a common
    victim: the splitter ate the heading's closing ``*`` and turned the prose
    that followed into a spurious list item::

        ...em questão.**Estratégia pré-mortem: (30 minutos)*
        * A estratégia pré-mortem foi criada...

    Merging restores ``**...(30 minutos)** A estratégia...`` as one paragraph,
    and the bullet correctly disappears.

    Returns (new_value, n_merges).
    """
    lines = value.split("\n")
    out, merges, i = [], 0, 0
    while i < len(lines):
        m = BULLET.match(lines[i])
        indent, item, is_bullet = ("", lines[i], False)
        if m:
            indent, item = m.groups()
            is_bullet = True
        # keep pulling the following bullet up while this line's emphasis is cut
        while unbalanced(item) and i + 1 < len(lines):
            nxt = BULLET.match(lines[i + 1])
            if not nxt:
                break
            item = f"{item}* {nxt.group(2)}"
            merges += 1
            i += 1
        out.append(f"{indent}* {item}" if is_bullet else item)
        i += 1
    return "\n".join(out), merges


# -------------------------------------------------------------------- checks

def strip_ws(s):
    """Whitespace-free form for character-fidelity comparison.

    Two transformations Weblate applied legitimately after the seed are
    normalised away, so they don't masquerade as character loss:
      * ``&`` was re-escaped to ``&amp;`` (invisible when rendered)
      * stray leading/trailing ``"`` left inside block scalars by Transifex
        were stripped
    """
    s = s.replace("&amp;", "&")
    s = re.sub(r"\s+", "", s)
    return s.strip('"')


def check(repaired, seed_value, en_value):
    """Return list of failure reasons (empty == all checks pass)."""
    fails = []
    if seed_value is None:
        fails.append("no seed value to compare against")
    elif strip_ws(repaired) != strip_ws(seed_value):
        fails.append("character loss vs seed")
    bad = [ln for ln in repaired.split("\n")
           if BULLET.match(ln) and unbalanced(BULLET.match(ln).group(2))]
    if bad:
        fails.append(f"{len(bad)} bullet(s) still unbalanced")
    if isinstance(en_value, str) and bullet_lines(repaired) > bullet_lines(en_value):
        fails.append(f"more bullets than EN source "
                     f"({bullet_lines(repaired)} > {bullet_lines(en_value)})")
    return fails


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", default=SEED, help=f"pre-damage rev (default {SEED})")
    ap.add_argument("--lang", action="append", help="restrict to language(s)")
    ap.add_argument("--verbose", action="store_true", help="show full field text")
    args = ap.parse_args()

    # English sources, keyed by "<type>/<name>.md"
    en = {}
    for f in glob.glob(os.path.join("content", "*", "*.md")):
        d = load_frontmatter(open(f, encoding="utf-8").read())
        if d:
            en[os.path.relpath(f, "content").replace(os.sep, "/")] = d

    proposals, blocked = [], []
    seed_cache = {}

    for f in sorted(glob.glob(os.path.join("locales", "*", "content", "*", "*.md"))):
        parts = f.replace(os.sep, "/").split("/")
        lang, rel = parts[1], "/".join(parts[3:])
        if args.lang and lang not in args.lang:
            continue
        cur = load_frontmatter(open(f, encoding="utf-8").read())
        if not cur:
            continue

        for key, value in cur.items():
            if not isinstance(value, str) or "*" not in value:
                continue
            repaired, merges = repair_value(value)
            if not merges:
                continue

            if f not in seed_cache:
                raw = git_show(args.seed, f)
                seed_cache[f] = load_frontmatter(raw) if raw else None
            seed_d = seed_cache[f]
            seed_value = seed_d.get(key) if isinstance(seed_d, dict) else None
            en_value = (en.get(rel) or {}).get(key)

            fails = check(repaired, seed_value if isinstance(seed_value, str) else None,
                          en_value)
            rec = dict(file=f, lang=lang, rel=rel, key=key, merges=merges,
                       before=value, after=repaired, fails=fails)
            (blocked if fails else proposals).append(rec)

    # ------------------------------------------------------------------ report
    print("=" * 78)
    print("DRY RUN — no changes written")
    print("=" * 78)
    print(f"  proposed repairs : {len(proposals)} fields "
          f"({sum(p['merges'] for p in proposals)} merges)")
    print(f"  blocked (review) : {len(blocked)} fields")

    bylang = {}
    for p in proposals:
        bylang.setdefault(p["lang"], [0, 0])
        bylang[p["lang"]][0] += 1
        bylang[p["lang"]][1] += p["merges"]
    if bylang:
        print("\n  by language:")
        for l in sorted(bylang):
            print(f"    {l:10} {bylang[l][0]:4} fields, {bylang[l][1]:4} merges")

    print("\n" + "=" * 78)
    print("PROPOSED REPAIRS")
    print("=" * 78)
    for p in proposals:
        print(f"\n  {p['lang']}  {p['rel']}  [{p['key']}]   {p['merges']} merge(s)")
        if args.verbose:
            print("  --- before ---"); print(p["before"])
            print("  --- after ----"); print(p["after"])
        else:
            for b, a in zip(p["before"].split("\n"), p["after"].split("\n")):
                if b != a:
                    print(f"      - {b.strip()[:110]}")
                    print(f"      + {a.strip()[:110]}")
                    break

    if blocked:
        print("\n" + "=" * 78)
        print("BLOCKED — needs manual review, will NOT be written")
        print("=" * 78)
        for b in blocked:
            print(f"\n  {b['lang']}  {b['rel']}  [{b['key']}]")
            print(f"      reason: {'; '.join(b['fails'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
