#!/usr/bin/env python3
"""
Create Weblate components for every translatable content Markdown file.

Loops over content/{activities,approaches,authors,guide_sections,infos,methods,
references,skills,tools}/*.md (the same set Transifex translated) and creates one
monolingual Markdown component per file, all sharing the anchor component's clone
via a linked repo. The anchor (content_methods_context_research) and the site.json
component must already exist.

Uses the payload proven in the Phase 0 spike:
  manage_units=false, edit_template=false, new_base + new_lang=add,
  file_format_params (md_extract_frontmatter/…) set AT creation.

Dry-run by default (prints the plan). Pass --apply to create. Idempotent: skips
components that already exist.

  python3 scripts/weblate-create-components.py            # dry run
  python3 scripts/weblate-create-components.py --apply
  python3 scripts/weblate-create-components.py --apply --limit 5   # test a few

Reads the API token from --token-file (default: the scratchpad weblate-token) or
the WEBLATE_API_KEY env var.
"""

import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

URL = "https://localizationlab.weblate.cloud/api"
PROJECT = "safetag"
ANCHOR = "content_methods_context_research"          # holds the real git repo
LINKED_REPO = f"weblate://{PROJECT}/{ANCHOR}"
CONTENT_DIRS = ["activities", "approaches", "authors", "guide_sections",
                "infos", "methods", "references", "skills", "tools"]
FF_PARAMS = {"md_extract_frontmatter": True,
             "md_frontmatter_translate_values": True,
             "md_extract_code_blocks": False}
DEFAULT_TOKEN_FILE = ("/private/tmp/claude-501/-Users-mantra-sites-safetag-weblate/"
                      "a557233f-e8fc-4942-8c57-e0f19ffaaadb/scratchpad/weblate-token")


def load_token(path):
    if os.environ.get("WEBLATE_API_KEY"):
        return os.environ["WEBLATE_API_KEY"].strip()
    if path and os.path.exists(path):
        return open(path).read().strip()
    sys.exit("error: no token (set WEBLATE_API_KEY or provide --token-file)")


def api(token, method, path, body=None):
    req = urllib.request.Request(
        URL + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Token " + token,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.load(e)
        except Exception:
            return e.code, {"raw": e.read().decode()[:300]}


def existing_slugs(token):
    slugs, path = set(), f"/projects/{PROJECT}/components/?format=json&page_size=100"
    while path:
        st, d = api(token, "GET", path)
        if st != 200:
            sys.exit(f"error listing components: HTTP {st} {d}")
        slugs.update(c["slug"] for c in d.get("results", []))
        nxt = d.get("next")
        path = nxt.replace(URL, "") if nxt else None
    return slugs


def title_of(md_path):
    try:
        m = re.match(r"^---\n(.*?)\n---", open(md_path, encoding="utf-8").read(), re.S)
        import yaml
        return (yaml.safe_load(m.group(1)) or {}).get("title")
    except Exception:
        return None


def specs():
    out = []
    for d in CONTENT_DIRS:
        for f in sorted(glob.glob(f"content/{d}/*.md")):
            rel = f  # content/<type>/<name>.md, repo-relative
            slug = rel[:-3].replace("/", "_")            # content_<type>_<name>
            title = title_of(f) or os.path.basename(f)[:-3]
            out.append({
                "name": f"{d.rstrip('s').title()}: {title}"[:100],
                "slug": slug,
                "vcs": "git",
                "repo": LINKED_REPO,
                "file_format": "markdown",
                "filemask": f"locales/*/{rel}",
                "template": rel,
                "new_base": rel,
                "new_lang": "add",
                "source_language": "en",
                "manage_units": False,
                "edit_template": False,
                "file_format_params": FF_PARAMS,
            })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually create (default: dry run)")
    ap.add_argument("--limit", type=int, default=0, help="only process the first N new components")
    ap.add_argument("--token-file", default=DEFAULT_TOKEN_FILE)
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between POSTs")
    args = ap.parse_args()

    token = load_token(args.token_file)
    have = existing_slugs(token)
    allspecs = specs()
    todo = [s for s in allspecs if s["slug"] not in have]
    if args.limit:
        todo = todo[:args.limit]

    print(f"content files: {len(allspecs)} | already in Weblate: "
          f"{len([s for s in allspecs if s['slug'] in have])} | to create: {len(todo)}")
    if not args.apply:
        print("\nDRY RUN — would create (first 10 shown):")
        for s in todo[:10]:
            print(f"  {s['slug']:52} <- {s['template']}")
        if len(todo) > 10:
            print(f"  … and {len(todo)-10} more")
        print("\nRe-run with --apply to create.")
        return

    ok = fail = 0
    for i, s in enumerate(todo, 1):
        st, d = api(token, "POST", f"/projects/{PROJECT}/components/", s)
        if st in (200, 201):
            ok += 1
            print(f"  [{i}/{len(todo)}] OK  {s['slug']}")
        else:
            fail += 1
            print(f"  [{i}/{len(todo)}] ERR {s['slug']} -> HTTP {st}: {json.dumps(d)[:160]}")
        time.sleep(args.delay)
    print(f"\ncreated: {ok} | failed: {fail}")


if __name__ == "__main__":
    main()
