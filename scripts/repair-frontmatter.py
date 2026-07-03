#!/usr/bin/env python3
"""
Repair Transifex `GITHUBMARKDOWN` frontmatter corruption in a locales/ tree.

Transifex's markdown export collapses translated `|` block scalars onto one line
and glues the FOLLOWING key onto the end without a newline, e.g.

    summary: |
      ...na atividade Entrevista.short_summary: Identificar o contexto...

`js-yaml`/gray-matter then reads `short_summary` as literal text and the field is
silently lost. `postprocess.py` cannot fix an already-merged key.

Approach (ground-truth driven, to avoid false positives): a translated file must
have the SAME frontmatter key set as its English source. So the keys to recover
are exactly `en_keys - translation_keys` — the swallowed ones. For each such key
we split its glued occurrence, then re-validate with a YAML parse and REVERT the
split if it fails or doesn't actually restore the key. Files we cannot fully
repair (or that were already unparseable) are flagged for manual review, never
written broken.

Requires PyYAML. Usage:
    python3 scripts/repair-frontmatter.py <locales_dir> [--source content] [--check]
    --check : report only, do not write.
"""

import sys
import re
import glob
import os
import yaml


def frontmatter(text):
    m = re.match(r"^(---\n)(.*?\n)(---\n?)(.*)$", text, re.S)
    if not m:
        return None
    return list(m.groups())  # [open, fm, close, body]


def parse_keys(fm):
    try:
        d = yaml.safe_load(fm)
        return set(d.keys()) if isinstance(d, dict) else set(), None
    except Exception as e:
        return None, str(e).splitlines()[0][:60]


def key_at_line_start(fm, key):
    return re.search(r"(?m)^" + re.escape(key) + r":", fm) is not None


def split_key(fm, key):
    """Split the first glued (mid-line) occurrence of `key:` onto its own line."""
    glued = re.compile(r"(?<=\S)" + re.escape(key) + r":(?=[ \t\r\n]|$|\||>|\[|\"|')")
    return glued.subn("\n" + key + ":", fm, count=1)


def build_source_keys(source_dir):
    src = {}
    for f in glob.glob(os.path.join(source_dir, "*", "*.md")):
        parts = frontmatter(open(f, encoding="utf-8").read())
        if not parts:
            continue
        keys, err = parse_keys(parts[1])
        if keys is not None:
            rel = os.path.relpath(f, source_dir)  # <type>/<name>.md
            src[rel] = keys
    return src


def process(path, src_keys, root, write):
    """Return dict: status, recovered[], note."""
    parts = frontmatter(open(path, encoding="utf-8").read())
    if not parts:
        return None
    open_d, fm, close_d, body = parts
    rel = os.path.relpath(path, root).split(os.sep + "content" + os.sep, 1)
    rel = rel[1] if len(rel) == 2 else None
    expected = src_keys.get(rel)

    fallback_fixed = False
    trans_keys, err = parse_keys(fm)

    # Fallback for files that don't parse at all: a key glued after a quoted or
    # inline value (e.g. `..."png)"guiding_questions:`) is a hard YAML error, not
    # just a swallowed field. Greedily split every EN-expected key that appears
    # glued mid-line, keeping only splits that leave the file parseable.
    if trans_keys is None:
        if not expected:
            return {"status": "unparseable", "recovered": [], "note": err}
        candidate = fm
        for key in expected:
            if key_at_line_start(candidate, key):
                continue
            c2, n = split_key(candidate, key)
            if n:
                candidate = c2
        # accept the accumulated splits only if the file now parses cleanly
        parsed, _ = parse_keys(candidate)
        if parsed is None:
            return {"status": "unparseable", "recovered": [], "note": err}
        fm, trans_keys = candidate, parsed
        fallback_fixed = True

    if not expected:
        return {"status": "ok", "recovered": [], "note": "no source match"}

    missing = expected - trans_keys
    recovered = []
    for key in missing:
        if key_at_line_start(fm, key):
            continue  # present but maybe as non-dict edge; skip
        candidate, n = split_key(fm, key)
        if not n:
            continue
        new_keys, e2 = parse_keys(candidate)
        # accept only if it parses AND the key is now a real top-level key AND we
        # didn't lose anything else
        if new_keys is not None and key in new_keys and trans_keys <= new_keys:
            fm, trans_keys = candidate, new_keys
            recovered.append(key)

    still_missing = expected - trans_keys
    if (recovered or fallback_fixed) and write:
        open(path, "w", encoding="utf-8").write(open_d + fm + close_d + body)
    if still_missing:
        return {"status": "partial", "recovered": recovered,
                "note": "still missing: " + ",".join(sorted(still_missing))}
    return {"status": "repaired" if (recovered or fallback_fixed) else "ok",
            "recovered": recovered, "note": ""}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    root = sys.argv[1]
    argv = sys.argv[2:]
    write = "--check" not in argv
    source_dir = "content"
    if "--source" in argv:
        source_dir = argv[argv.index("--source") + 1]

    src_keys = build_source_keys(source_dir)
    files = glob.glob(os.path.join(root, "*", "content", "*", "*.md"))
    repaired = partial = unparseable = 0
    flags = []
    for f in sorted(files):
        r = process(f, src_keys, root, write)
        if not r:
            continue
        if r["status"] == "repaired":
            repaired += 1
        elif r["status"] == "partial":
            partial += 1
            flags.append((f, r["note"]))
        elif r["status"] == "unparseable":
            unparseable += 1
            flags.append((f, "UNPARSEABLE: " + str(r["note"])))
    print(f"{'(check) ' if not write else ''}source keys from {len(src_keys)} EN files; "
          f"scanned {len(files)} translations")
    print(f"  repaired (fully): {repaired}")
    print(f"  partial/needs-review: {partial}")
    print(f"  unparseable (manual): {unparseable}")
    if flags:
        print("\nFlagged for manual review:")
        for f, note in flags:
            print(f"  {os.path.relpath(f, root)}: {note}")


if __name__ == "__main__":
    main()
