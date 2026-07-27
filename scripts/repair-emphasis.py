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
import configparser
import glob
import html
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

import yaml

SEED = "be351ce50"
BULLET = re.compile(r"^(\s*)\*\s+(.*)$")
INLINE_CODE = re.compile(r"`[^`]*`")

# A bullet that lost the space after its marker: "*Domains + IP addresses".
# BULLET does not match it, so it reads as prose with unbalanced emphasis and
# would wrongly absorb the real bullet beneath it. These exist in the English
# source too (e.g. content/activities/dns_enumeration.md), so translations are
# faithfully mirroring a source defect -- leave them alone rather than "repair"
# two list items into one.
MALFORMED_BULLET = re.compile(r"^\s*\*[^\s*]")


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


# Collateral from typos in the *English source*, where a stray "* " was
# indistinguishable from a bullet marker and the splitting pass broke the line.
# Fixing the source alone does not repair translations already split, and the
# generic rule cannot see these: "**Network Setting" has an even number of
# asterisks, so parity reads it as balanced even though the bold is unclosed.
# Each entry names the commit that fixed the corresponding source file.
SOURCE_TYPO_COLLATERAL = [
    # content/activities/web_vulnerability_assessment.md, fixed in 26ec2748f:
    # "**Network Setting*" -> "**Network Settings**"
    # First form is the split as it appears now; second is the seed's collapsed
    # form, so applying this to the seed too keeps the fidelity check honest
    # rather than reading the correction itself as character loss.
    (re.compile(r"\*\*Network Setting\n\s*\*\s+windows in Kali"),
     "**Network Settings** windows in Kali"),
    (re.compile(r"\*\*Network Setting\*\s+windows in Kali"),
     "**Network Settings** windows in Kali"),
]


def fix_collateral(value):
    """Apply the source-typo collateral corrections. Returns (new_value, n)."""
    n = 0
    for pat, repl in SOURCE_TYPO_COLLATERAL:
        value, k = pat.subn(repl, value)
        n += k
    return value, n


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
        # A malformed bullet is not prose with cut emphasis -- never merge into it
        if not is_bullet and MALFORMED_BULLET.match(lines[i]):
            out.append(item)
            i += 1
            continue
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

    Weblate re-serialised HTML entities in both directions since the seed --
    ``&`` became ``&amp;`` and ``>`` became ``&gt;``, while ``&ast;`` was decoded
    to a literal ``*``. None of that is character loss, so decode entities on
    both sides before comparing. Stray leading/trailing ``"`` that Transifex left
    inside block scalars, and that Weblate stripped, are ignored likewise.
    """
    s = html.unescape(s)
    s = re.sub(r"\s+", "", s)
    return s.strip('"')


def check(repaired, seed_value, en_value):
    """Return (blocking_failures, warnings).

    Blocking -- these are correctness guarantees:
      * no character loss vs the pre-damage seed (the merge only removed a
        newline), and
      * every bullet's emphasis balances afterwards.

    Bullet count vs the English source is read directionally:

      * **fewer** bullets than English blocks -- a merge that leaves the list
        shorter than its source has eaten list items, which is damage, not
        repair;
      * **more** bullets only warns -- a translator may legitimately split a
        sentence differently or add an item.

    Both directions earn their keep as diagnostics: "more" exposed the
    run-in-heading gap in ``repair_value``, and "fewer" caught the over-merge on
    malformed bullets.
    """
    fails, warns = [], []
    if seed_value is None:
        fails.append("no seed value to compare against")
    elif strip_ws(repaired) != strip_ws(seed_value):
        fails.append("character loss vs seed")
    bad = [ln for ln in repaired.split("\n")
           if BULLET.match(ln) and unbalanced(BULLET.match(ln).group(2))]
    if bad:
        fails.append(f"{len(bad)} bullet(s) still unbalanced")
    if isinstance(en_value, str):
        got, want = bullet_lines(repaired), bullet_lines(en_value)
        if got < want:
            fails.append(f"repair LOST list items ({got} bullets vs EN {want})")
        elif got > want:
            warns.append(f"more bullets than EN ({got} vs {want})")
    return fails, warns


# -------------------------------------------------------------- weblate api

PROJECT = "safetag"
CONFIG = os.path.expanduser("~/.config/weblate")


class Weblate:
    """Thin read/write client. Credentials come from ~/.config/weblate."""

    def __init__(self):
        # configparser's default delimiters include ':', which would split the
        # https:// URL used as the key name in [keys]. Restrict to '='.
        cp = configparser.ConfigParser(delimiters=("=",))
        if not cp.read(CONFIG):
            sys.exit(f"no Weblate config at {CONFIG}")
        self.url = cp.get("weblate", "url").strip().rstrip("/")
        keys = dict(cp.items("keys")) if cp.has_section("keys") else {}
        self.token = next((v.strip() for k, v in keys.items()
                           if k.strip().rstrip("/") == self.url), None)
        if self.token is None and len(keys) == 1:
            self.token = list(keys.values())[0].strip()
        if not self.token:
            sys.exit("no API token found in [keys] matching the configured url")
        self._translations = {}   # component slug -> {filename: translation url}

    def _request(self, path, method="GET", payload=None):
        url = path if path.startswith("http") else self.url + path
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={
            "Authorization": f"Token {self.token}",
            "User-Agent": "safetag-repair-emphasis",
            **({"Content-Type": "application/json"} if data else {}),
        })
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=90) as r:
                    return json.loads(r.read().decode() or "{}")
            except urllib.error.HTTPError as e:
                if e.code == 429:                       # rate limited
                    wait = int(e.headers.get("Retry-After", 10)) + 1
                    print(f"    rate limited, waiting {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                raise
        raise RuntimeError(f"gave up after rate limiting: {path}")

    def get(self, path):
        return self._request(path)

    def patch(self, path, payload):
        return self._request(path, method="PATCH", payload=payload)

    def translations(self, slug):
        """{filename: translation api url} for one component, cached."""
        if slug not in self._translations:
            out, page = {}, f"/components/{PROJECT}/{slug}/translations/"
            while page:
                d = self.get(page)
                for t in d.get("results", []):
                    if t.get("filename"):
                        out[t["filename"]] = t["url"]
                page = d.get("next")
            self._translations[slug] = out
        return self._translations[slug]

    def find_unit(self, slug, filename, source_text):
        """Locate a unit by its SOURCE string.

        Frontmatter units carry an empty ``context``, so the English value is
        the only stable identifier. Compared with whitespace collapsed, since
        Weblate and PyYAML disagree about trailing newlines.
        """
        turl = self.translations(slug).get(filename)
        if not turl:
            return None, f"no translation for {filename}"
        want = re.sub(r"\s+", " ", source_text).strip()
        page = turl + "units/"
        while page:
            d = self.get(page)
            for u in d.get("results", []):
                src = (u.get("source") or [""])[0]
                if re.sub(r"\s+", " ", src).strip() == want:
                    return u, None
            page = d.get("next")
        return None, "no unit matched the English source"


def component_slug(rel):
    """'activities/self_doxing.md' -> 'content_activities_self_doxing'."""
    return "content_" + rel[:-3].replace("/", "_")


# ---------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", default=SEED, help=f"pre-damage rev (default {SEED})")
    ap.add_argument("--lang", action="append", help="restrict to language(s)")
    ap.add_argument("--verbose", action="store_true", help="show full field text")
    ap.add_argument("--resolve", action="store_true",
                    help="map each proposal to its Weblate unit (still no writes)")
    ap.add_argument("--apply", action="store_true",
                    help="WRITE the repairs to Weblate (implies --resolve)")
    ap.add_argument("--limit", type=int,
                    help="only act on the first N proposals (use for a canary)")
    args = ap.parse_args()
    if args.apply:
        args.resolve = True

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
            staged, collateral = fix_collateral(value)
            repaired, merges = repair_value(staged)
            if not merges and not collateral:
                continue

            if f not in seed_cache:
                raw = git_show(args.seed, f)
                seed_cache[f] = load_frontmatter(raw) if raw else None
            seed_d = seed_cache[f]
            seed_value = seed_d.get(key) if isinstance(seed_d, dict) else None
            en_value = (en.get(rel) or {}).get(key)

            seed_cmp = (fix_collateral(seed_value)[0]
                        if isinstance(seed_value, str) else None)
            fails, warns = check(repaired, seed_cmp, en_value)
            rec = dict(file=f, lang=lang, rel=rel, key=key, merges=merges,
                       collateral=collateral, before=value, after=repaired,
                       fails=fails, warns=warns)
            (blocked if fails else proposals).append(rec)

    # ------------------------------------------------------------------ report
    print("=" * 78)
    print("APPLYING — writes to Weblate" if args.apply else "DRY RUN — no changes written")
    print("=" * 78)
    warned = [p for p in proposals if p["warns"]]
    print(f"  proposed repairs : {len(proposals)} fields "
          f"({sum(p['merges'] for p in proposals)} merges)")
    print(f"    of which warn  : {len(warned)} (bullet count differs from EN — "
          f"worth a spot-check, not blocking)")
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

    if not args.resolve:
        print("\nRe-run with --resolve to map these to Weblate units, "
              "then --apply to write.")
        return 0

    # --------------------------------------------------- resolve / apply
    wl = Weblate()
    todo = proposals[:args.limit] if args.limit else proposals
    print("\n" + "=" * 78)
    print(f"{'APPLYING' if args.apply else 'RESOLVING'} {len(todo)} of "
          f"{len(proposals)} proposals")
    print("=" * 78)

    en_src = {}
    for rel, d in en.items():
        en_src[rel] = d

    ok = written = 0
    problems = []
    for p in todo:
        slug = component_slug(p["rel"])
        source_text = (en_src.get(p["rel"]) or {}).get(p["key"])
        if not isinstance(source_text, str):
            problems.append((p, "no English source value")); continue
        try:
            unit, err = wl.find_unit(slug, p["file"], source_text)
        except urllib.error.HTTPError as e:
            problems.append((p, f"HTTP {e.code} on {slug}")); continue
        if unit is None:
            problems.append((p, err)); continue
        ok += 1
        cur_target = (unit.get("target") or [""])[0]
        if re.sub(r"\s+", " ", cur_target).strip() != re.sub(r"\s+", " ", p["before"]).strip():
            problems.append((p, "unit target differs from the file on disk "
                                "(Weblate moved on — re-run the dry run)"))
            continue
        if not args.apply:
            print(f"  ok  {p['lang']:6} {p['rel']:52} [{p['key']}] unit={unit['id']}")
            continue
        wl.patch(f"/units/{unit['id']}/",
                 {"target": [p["after"]], "state": unit.get("state", 20)})
        written += 1
        print(f"  WROTE {p['lang']:6} {p['rel']:52} [{p['key']}] unit={unit['id']}",
              flush=True)

    print(f"\n  resolved: {ok}/{len(todo)}"
          + (f"   written: {written}" if args.apply else ""))
    if problems:
        print(f"\n  could not resolve ({len(problems)}):")
        for p, why in problems[:25]:
            print(f"    {p['lang']:6} {p['rel']} [{p['key']}]: {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
