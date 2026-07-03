#!/usr/bin/env python3
"""
Stage a Weblate seed tree into `locales/` from a captured Transifex snapshot.

The snapshot (a `tx pull` / Transifex export) has language dirs at its top level
(`en/ pt_BR/ my/ ...`), each containing `content/**/*.md` + `site.json`. This
script copies a chosen source into `locales/` in the repo, optionally repairs
frontmatter corruption, and reports the resulting YAML health so you can commit a
clean seed to the `weblate` branch.

Two cases (decided by whether the RAW Transifex output is corrupt — see
doc/weblate-migration.md §3a):

    # Case A — raw export is clean (postprocess.py was the culprit):
    python3 scripts/stage-seed.py --from ../transifex-locales-raw

    # Case B — corruption is Transifex-side; repair while staging:
    python3 scripts/stage-seed.py --from ../transifex-locales-snapshot-2 --repair

Requires PyYAML for the health report. Run from the repo root.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys

try:
    import yaml
except ImportError:
    yaml = None


def parse_keys(path):
    m = re.match(r"^---\n(.*?)\n---", open(path, encoding="utf-8").read(), re.S)
    if not m:
        return None, "no frontmatter"
    try:
        d = yaml.safe_load(m.group(1))
        return (set(d.keys()) if isinstance(d, dict) else set()), None
    except Exception as e:
        return None, str(e).splitlines()[0][:50]


def health_report(dest, source_dir):
    if yaml is None:
        print("  (PyYAML not installed — skipping YAML health report)")
        return
    en = {}
    for f in glob.glob(os.path.join(source_dir, "*", "*.md")):
        k, _ = parse_keys(f)
        if k is not None:
            en[os.path.relpath(f, source_dir)] = k
    files = glob.glob(os.path.join(dest, "*", "content", "*", "*.md"))
    parsefail = missing = 0
    for f in files:
        rel = os.path.relpath(f, dest).split(os.sep + "content" + os.sep, 1)
        rel = rel[1] if len(rel) == 2 else None
        k, err = parse_keys(f)
        if k is None:
            parsefail += 1
            continue
        if rel and en.get(rel) and (en[rel] - k):
            missing += 1
    print(f"  YAML health: {len(files)} translation files | "
          f"parse failures: {parsefail} | files still missing keys: {missing}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="src", required=True,
                    help="snapshot dir with top-level language folders")
    ap.add_argument("--repair", action="store_true",
                    help="run scripts/repair-frontmatter.py on the staged tree")
    ap.add_argument("--dest", default="locales")
    ap.add_argument("--source", default="content",
                    help="English source dir (for repair + health report)")
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        sys.exit(f"error: --from '{args.src}' is not a directory")
    langs = [d for d in os.listdir(args.src)
             if os.path.isdir(os.path.join(args.src, d)) and not d.startswith(".")]
    if not langs:
        sys.exit(f"error: no language folders found in {args.src}")

    print(f"Staging {len(langs)} languages from {args.src} -> {args.dest}/")
    if os.path.exists(args.dest):
        shutil.rmtree(args.dest)
    shutil.copytree(args.src, args.dest)

    if args.repair:
        print("Repairing frontmatter (scripts/repair-frontmatter.py) ...")
        subprocess.run([sys.executable, "scripts/repair-frontmatter.py",
                        args.dest, "--source", args.source], check=True)

    langdirs = sorted(d for d in os.listdir(args.dest)
                      if os.path.isdir(os.path.join(args.dest, d)))
    print(f"Staged languages: {', '.join(langdirs)}")
    health_report(args.dest, args.source)
    print(f"\nDone. Review, then: git add {args.dest} && git commit")


if __name__ == "__main__":
    main()
