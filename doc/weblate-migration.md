# Migration plan: Transifex → Weblate (hosted `weblate.cloud`, git-native)

Status: proposed. Owner: localization workstream. Target: replace the Transifex
`tx` integration with Weblate while leaving the Gatsby build untouched.

## 1. Goal and hard constraint

Replace the Transifex toolchain (`tx` binary, `transifex-sync.sh`, `transifex.js`,
`postprocess.py`, `TX_TOKEN`) with Weblate, using the **git-native (Model A)**
integration: Weblate reads English source from the repo and **commits translated
files back into the repo itself**. The build then just checks out and runs
`gatsby build` — no translation API call at build time, no token in CI.

**Hard constraint — do not change the output contract.** Gatsby discovers
translations purely by file location (see `gatsby-node.js` `onCreateNode`, which
derives `langKey` from path depth). Weblate must produce exactly:

| File | Language | Format |
|---|---|---|
| `content/<type>/<name>.md` | English source (depth 2 → `en`) | Markdown |
| `locales/<lang>/content/<type>/<name>.md` | translation (depth 4 → `<lang>`) | Markdown |
| `locales/en/site.json` | English UI source | i18next JSON |
| `locales/<lang>/site.json` | UI translation | i18next JSON |

If Weblate writes these paths with these formats, `gatsby-config.js` and
`gatsby-node.js` need **zero** changes. Active languages remain `en, pt_BR, my, fr`
(defined in `gatsby-config.js` — that is the authoritative list, not
`i18next-parser.config.js`).

## 1a. Where translations live today (important)

Translation operates on **source files only**; HTML is downstream output that is
never an input to translation. Current flow:

```
Transifex (source of truth)
  ──tx pull──▶ locales/<lang>/**.md + locales/<lang>/site.json  (gitignored, regenerated every build)
  ──gatsby build──▶ public/ (compiled HTML)
  ──gh-pages──▶ `guide` branch  (deployed static site; compiled output, NOT source)
```

Consequences that shape the migration:

- `locales/` is **gitignored** and generated per build — the translated `.md`
  files are **not committed anywhere**. A local `locales/<lang>/` will look empty
  (only a stub `site.json`).
- The `guide` branch holds the **built site** (`public/`), not source markdown. It
  cannot be used to recover editable translations.
- The **only authoritative store of current translations is Transifex**. They
  exist as files only transiently inside a CI build (between `transifex-pull` and
  `gatsby build`).
- Therefore migrating existing work requires **one final `transifex-pull`** to
  extract translations as `locales/**` files (see Phase 0.1). That is the last use
  of `tx` and the moment all existing translation work is captured.

Weblate operates on the same source files (`locales/<lang>/**.md` + `site.json`),
never HTML — so this is a swap of the left-most box only; build and output are
unchanged.

## 2. Confirmed capabilities (de-risked)

- Weblate has a native **"Markdown files"** monolingual format with options
  `md_extract_frontmatter`, `md_frontmatter_translate_values`,
  `md_extract_code_blocks`. This is the direct replacement for Transifex's
  `GITHUBMARKDOWN` type — **no PO/translate-toolkit conversion required**.
- Weblate has a native **"i18next JSON"** monolingual format for `site.json`
  (also fixes the current mistype, where `site.json` is registered as
  `GITHUBMARKDOWN`).
- `wlc` verb semantics (important, differ from `tx`): `push`/`pull` sync Weblate
  with **its own git remote**; `download`/`upload` move files to/from **local
  disk**. `wlc` **cannot create components** — creation is REST API or the
  Component Discovery addon. In Model A none of these run at build time; `wlc` is
  only a maintainer/admin convenience.
- `wlc` is a pip package (cross-platform) — resolves the current problem that the
  vendored `tx` is a Linux-only ELF that will not run on macOS.

Refs: https://docs.weblate.org/en/latest/formats.html ,
https://docs.weblate.org/en/latest/wlc.html

## 3. Frontmatter handling (verified against the snapshot)

`src/helpers/useAllGuideData.js` and `src/pages/guide-builder.js` assemble the
guide by joining content on `frontmatter.title` (`id: frontmatter.title`); a
method's `activities:`/`references:` arrays are lists of titles resolved via
`find(a => a.id === id)`, and the GraphQL queries have **no `langKey` filter** (all
languages merged into one title-keyed map).

**What the snapshot proved (corrects an earlier assumption):** in current
production output, the join keys are **translated**, not English —
`title: Pesquisa de Contexto`, `activities:` and `references:` all in Portuguese.
So Transifex localizes the whole frontmatter, and the site ships that way. The
guide-builder's title-keyed, language-mixed map is a **pre-existing** quirk,
independent of this migration and out of scope.

**Directive: replicate current behavior — translate all frontmatter.** Forcing
join keys to English (the previously-proposed read-only approach) would *regress*
translated method/activity pages, which display the translated title. Therefore:

- Set `md_extract_frontmatter=true`, `md_frontmatter_translate_values=true`
  (translate everything — this is what Transifex does today).
- `md_frontmatter_translate_values` is all-or-nothing (boolean), which is now
  **fine**, because we want all values translated.
- The **only** fields to protect as **`read-only`** (via the Bulk edit addon
  `weblate.flags.bulk`) are the **image-path / literal string** fields a translator
  could break: `method_icon`, `the_flow_of_information`. In the snapshot these
  correctly stayed as `/img/...` paths — keep it that way.
- Integer fields (`position`, `organization_size_under`, `time_required_minutes`)
  are not scalar strings, so `md_frontmatter_translate_values` won't expose them —
  no action needed.

### 3a. Pre-existing Transifex corruption (a reason to migrate, and a seed hazard)

The snapshot revealed that Transifex's `GITHUBMARKDOWN` export damages frontmatter
in **two distinct ways**, measured across all 12 languages by comparing each
translation's YAML key set to its English source (`scripts/repair-frontmatter.py`):

1. **Swallowed keys (structural corruption).** A translated `|` block scalar
   collapses to one line and the **next key glues onto its end without a newline**
   (`…Entrevista.short_summary:`, `…parecidas?authors:`). `js-yaml`/gray-matter
   reads the swallowed key as literal text → field silently lost. `postprocess.py`
   cannot fix mid-line merges.
2. **Dropped keys.** Transifex sometimes omits a field entirely (e.g. a `zh_HK`
   activity with no `title:` at all, or a missing `tools:`).

Measured extent: **215 of 2695 translated files** were missing ≥1 key present in
their English source (524 key-instances total).

**Source confirmed Transifex-side (not `postprocess.py`).** The raw Transifex ZIP
export (flat `content_<slug>-<lang>.md`, no postprocess applied) shows the *same*
corruption — 182/3048 content files with the swallowed-key signature, e.g.
`content_methods_context_research-pt_br.md` has `short_summary`/`authors`/
`info_required`/`info_provided`/`preparation` swallowed. So no whole-file export
avoids it; the repair script is required (Case B).

**Seed base = postprocessed `tx pull` output + repair** (confirmed by the CI
raw-vs-postprocessed diff). `postprocess.py` is **not** the culprit — it only
*indents* block-scalar content so `key: |` blocks are valid YAML. Without it (raw
`tx pull`), the content is unindented, so YAML parses `summary` as **empty** and
promotes the block text to a garbage top-level key — i.e. raw is *worse*. Correct
pipeline: Transifex → `postprocess.py` (indent) → `repair-frontmatter.py`
(swallowed keys) → valid YAML. So seed from `transifex-locales-snapshot-2`
(postprocessed) with `--repair`; do **not** seed from raw. `postprocess.py` stays
as a one-time seed pre-step and retires only after cutover (Weblate serializes
correctly). The ZIP export (flat, lowercase langs, also unindented+swallowed) is a
cross-check only.

Repair + handling:
- `scripts/repair-frontmatter.py` (source-driven, PyYAML-validated) recovers
  **swallowed** keys by re-inserting the newline, then re-parses and **reverts any
  split that doesn't validate** — so it never writes broken YAML. A fallback also
  repairs files that don't parse at all (keys glued after a quoted value, e.g.
  `..."png)"guiding_questions:`). Measured on the seed: **136 files repaired, and
  the full 2695-file tree parses with 0 YAML errors** (including the one
  previously-unparseable file).
- **Dropped** keys need no repair: in a Weblate monolingual component an
  untranslated/absent unit **falls back to the English source template**, so those
  fields correctly show English until translated. (These currently render broken
  on the live site — another thing the migration fixes.)
- Residual manual items: 1 pre-existing unparseable file
  (`pt_BR/.../organizational_device_assessment.md`) and a malformed EN-source key
  (`` Considerations` `` with a stray backtick, propagated to 11 languages) — both
  pre-date this work and want a one-line source fix.

**Net:** migration is a real data-quality upgrade; the repaired tree is the clean
seed. Decision confirmed: **repair before import.**

### 3b. Seed translated-state accuracy (untranslated must import as untranslated)

The snapshot `.md` files are **fully resolved**: `tx pull` fills every untranslated
segment with the English source (a `GITHUBMARKDOWN` file must render completely).
Weblate monolingual formats count "unit has a value" as **translated**, so seeding
as-is would mark **everything translated** — including English-fallback strings.
That inflates completion, hides remaining work from translators, and (worst)
prevents Weblate from flagging those strings when the English source later changes.
The translated/untranslated distinction is **not recoverable from the files
alone.**

Fix (chosen): **seed as-is, then bulk-clear same-as-source.** After import, use
Weblate's built-in **"Unchanged translation"** check (`check:unchanged`) + the
**Bulk edit** addon to set every unit whose translation equals its source to
*untranslated / needs-editing*, in one pass. This uses Weblate's own segmentation
(exact), needs no offline work, and errs safe (a legitimately identical
translation just gets re-confirmed). **Exclude read-only units**
(`method_icon`, `the_flow_of_information`) from the bulk-clear — they correctly
equal source. Authoritative alternative if exact day-one stats are needed: pull
per-string `translated/reviewed` status from the Transifex API. The spike verifies
this: post-seed completion looks inflated, drops to the true figure after the
bulk-clear.

## 4. Target architecture (Model A)

```
Weblate cloud project "safetag"
  ├─ anchor component (Markdown)  ── real git creds ──▶ GitHub repo, branch `development`
  │     template  = content/methods/preparation.md   (example)
  │     filemask  = locales/*/content/methods/preparation.md
  ├─ ~244 more Markdown components  ── linked repo weblate://safetag/anchor ──▶ same clone
  │     (created + maintained by Component Discovery addon or a REST script)
  └─ site component (i18next JSON) ── linked repo ──▶ same clone
        template = locales/en/site.json
        filemask = locales/*/site.json

Translator edits in Weblate UI
  → Weblate commits to `development` (Squash addon keeps it to one commit/lang/push)
  → push to `development` triggers existing staging deploy workflow → staging site
  → normal promotion development → main publishes to production
```

Source updates flow the other way via a GitHub → Weblate webhook
(`https://<org>.weblate.cloud/hooks/github/`) so new/changed English content and
`site.json` keys are re-scanned by Weblate.

## 5. Phase 0 — Early validation spike (do this first; it gates everything)

Goal: prove Weblate ingests the (repaired) translations, re-serializes **valid**
YAML with all frontmatter translated, and that Gatsby builds correctly — using
read-only public clone + download, **no repo write access needed** (see auth
section).

Reference language: **`pt_BR`** — most complete pair and most corruption, so it
exercises both the prose fields and the repair path.

Status: step 1 ✅ done (snapshot captured to
`transifex-locales-snapshot-2/`, 12 languages). Steps 2+ below.

1. ✅ **Snapshot captured** via `.github/workflows/capture-translations.yml`
   (delete the workflow once seeding is done). 12 languages, 245 md + `site.json`
   each; `en` has only `site.json` (English content lives in `content/`).
2. **Repair + stage the seed.** Run the repair script (Phase 1) over the snapshot
   to fix swallowed-key corruption, then commit the repaired `locales/` (en source
   + all 12 langs) onto the **`weblate` branch** of the public fork so Weblate can
   read source *and* existing translations directly. (`locales/en/site.json` is the
   i18next template.)
3. **Create the trial components** (Appendix A) against `https://github.com/blazman/SAFETAG.git`,
   branch `weblate`: `context_research.md` (method) + ≥2 of its activities so a
   translated join is visible, plus the `site.json` i18next component.
4. **Frontmatter config = translate-all + narrow read-only.** Set
   `md_extract_frontmatter=true`, `md_frontmatter_translate_values=true`; use the
   Bulk edit addon to mark only `method_icon` / `the_flow_of_information` read-only
   (see §3). No read-only on title/activities/references — they are translated in
   production.
5. **Language codes.** Confirm Weblate writes `pt_BR` (not `pt-BR`), and that all
   12 codes (`ar es fr id my pt_BR ru th zh zh_HK zh_TW`) map to the directory
   names `gatsby-config.js` expects for the 4 active langs at minimum.
6. **Round-trip + build.** Download Weblate's serialization (`wlc download` / UI),
   drop into `locales/`, `gatsby build`.

**Exit criteria (revised — golden is corrupt, so no byte-equality):**
- Weblate output is **valid YAML** for the trial files — the swallowed keys
  (`short_summary`, `authors`, `preparation`, …) are present as real keys, i.e.
  Weblate *fixes* the corruption rather than propagating it.
- All frontmatter is translated (matching production intent), except
  `method_icon` / `the_flow_of_information` which stay as `/img/...` paths.
- `gatsby build` succeeds; the pt_BR method page renders **with** the
  previously-lost fields, and the method resolves its activities/references.
- Compare **rendered** pt_BR pages (or YAML parsed to field values), not raw bytes,
  against the current site — Weblate output should be equal-or-better.
- **Translated-state check (§3b):** right after seeding, pt_BR completion looks
  inflated (≈100%); after the "Unchanged translation" bulk-clear it drops to the
  true figure, with English-fallback units now showing as untranslated.

If any exit criterion fails, stop and reassess format strategy before scaling.

## 6. Phases 1–6 — Implementation (after a green spike)

**Phase 1 — Repo prep + seed repair.**  *(tooling built)*
- **`.gitignore`**: `locales/` un-ignored (done) so translations are tracked;
  `.tx/` still ignored.
- **`scripts/stage-seed.py`**: lays a chosen snapshot into `locales/` and reports
  YAML health. Case A (raw clean): `--from ../transifex-locales-raw`. Case B
  (Transifex-side corruption): `--from ../transifex-locales-snapshot-2 --repair`.
- **`scripts/repair-frontmatter.py`** (used by `--repair`; retire if Case A):
  source-driven, PyYAML-validated, reverts any split that doesn't parse.
- **Seed repair rationale** (replaces the role of `postprocess.py`): walk the
  snapshot `locales/**/content/**/*.md`, detect any known frontmatter key that
  appears mid-line (glued after non-whitespace) and re-insert a newline before it,
  yielding valid YAML. Validate each repaired file parses (js-yaml/PyYAML) and that
  the swallowed keys reappear. Manually review the ~13 pt_BR files. This produces
  the clean seed imported into Weblate.
- **Languages: migrate all 12** (`ar es fr id my pt_BR ru th zh zh_HK zh_TW` + en)
  to preserve existing work; keep the site's **active set at 4** (`en pt_BR my fr`
  in `gatsby-config.js`). Extra languages sit in Weblate/`locales/` but are not
  built until added to the config.
- Un-ignore translations so Weblate's commits are tracked: remove `locales/` (and
  `.tx/`) handling from `.gitignore`; commit the golden `locales/` tree as the
  translation baseline.
- Decide committed vs generated source for `locales/en/site.json`: commit it, and
  add a GitHub Action (on push to `development`, `paths: [src/**]`) that runs
  `npm run extract` and commits changes to `locales/en/site.json`. Scope paths and
  use a skip-ci marker to avoid a Weblate-commit ↔ extract-commit feedback loop.

**Phase 2 — Weblate project + anchor.**
- Create/confirm project `safetag` on `weblate.cloud`.
- Create the anchor Markdown component with real GitHub credentials (add Weblate's
  SSH key as a **write** deploy key on the repo; branch `development`; enable
  "Push on commit" + the **Squash** addon).
- Create the `site.json` i18next component as a **linked** repo
  (`weblate://safetag/<anchor>`) so the repo is cloned once.

**Phase 3 — Scale out the 245 content components.**
- Preferred: attach the **Component Discovery** addon
  (`weblate.discovery.discovery`) with a `match` over `content/**/*.md`, templates
  mapping `content/{path}.md` → filemask `locales/*/content/{path}.md`, so
  components auto-create and stay in sync as content files are added/removed.
- Alternative if Discovery's regex can't express the source-in-`content/`,
  translations-in-`locales/` split cleanly: a REST script that walks
  `content/**/*.md` and `POST`s a component per file (linked repo, explicit
  template + filemask). Replaces `transifex-sync.sh`. Keep it runnable to re-sync
  after content additions.

**Phase 4 — npm scripts.**
- Keep `extract` (i18next-parser; unrelated to Transifex).
- Remove `transifex-push`, `transifex-pull`, `postproc` (unless Phase 0 shows
  frontmatter still needs repair — then keep a slimmed `postprocess.py` run by
  Weblate as an addon or a CI step, not by the removed pull).
- Optionally add `weblate:*` helper scripts using `wlc` (lock/commit/download for
  admin), plus a `.weblate` config (`url = https://<org>.weblate.cloud/api/`,
  `[keys]` section). API key via `WEBLATE_API_KEY`, never committed.

**Phase 5 — GitHub workflows.**
- `deploy-to-gh-pages.yml` and `deploy-staging.yml`: delete the `TX_TOKEN`
  secret-writing block and the extract/push/pull steps; the build becomes
  `npm ci && npm run build` (Node 20). No translation token needed.
- Add the GitHub → Weblate webhook so source pushes re-scan.
- Fix `lint-and-test.yml`: bump Node 16 → 20 to match `engines` and the deploy
  jobs.

**Phase 6 — Cutover + cleanup.**
- Freeze Transifex; do the final golden pull (Phase 0.1) if not already current.
- Verify staging built from Weblate matches production, then promote.
- Delete `tx` (10 MB binary), `transifex-sync.sh`, `src/helpers/transifex.js`
  (already dead code), and the `transifex` npm dependency.
- Rewrite the translation sections of `README.md` (currently documents the old
  Python `transifex-client` + `tx init`, both obsolete).
- Update `CLAUDE.md` localization section to describe the Weblate flow.

## 7. File-by-file change summary

| Path | Action |
|---|---|
| `tx` (binary) | delete |
| `transifex-sync.sh` | delete (replaced by Discovery addon / REST script) |
| `src/helpers/transifex.js` | delete (dead code) |
| `src/helpers/postprocess.py` | delete, or keep slimmed if Phase 0 requires |
| `package.json` scripts | drop `transifex-*`/`postproc`; keep `extract`; add `weblate:*` (optional) |
| `package.json` deps | remove `transifex` |
| `.gitignore` | stop ignoring `locales/` and `.tx/`; track translations |
| `.github/workflows/deploy-*.yml` | remove TX_TOKEN + push/pull; plain build |
| `.github/workflows/lint-and-test.yml` | Node 16 → 20 |
| `.weblate` (new) | wlc/API config (url only; key via env) |
| `README.md`, `CLAUDE.md` | rewrite localization docs |
| `gatsby-config.js`, `gatsby-node.js`, `src/**` | **no change** |

## 8. Open questions / risks

1. **Frontmatter selective translation** (Phase 0.4) — the single biggest
   unknown. Whether `md_frontmatter_translate_values` supports per-key scoping vs
   needing read-only flags decides how join keys are protected.
2. **Component sprawl (246)** — Discovery vs scripted REST creation; validate
   Discovery can maintain them as Decap editors add content.
3. **Commit-loop hygiene** — Weblate commits vs the extract-commit action must not
   trigger each other indefinitely (path filters + squash + skip-ci).
4. **Language code mapping** — ensure `pt_BR` / `my` output directory names match
   `gatsby-config.js` exactly.
5. **Decap CMS** (`static/admin/config.yml`) is **not currently in use** — out of
   scope for the migration. Backlog item: restore it after migration and confirm
   its `content/` edits interact cleanly with the source→Weblate webhook.
6. **`network_mapping.svg`** under `content/methods/` is not a translatable unit —
   Discovery/`match` must exclude non-`.md` files (the old `tx` glob already did).
7. **Repo write-access at cutover** — the shared instance SSH key can't be a deploy
   key on both fork and upstream; production needs the GitHub App + org/instance
   admin coordination. See "Repo write-access / auth" above. Line up early.

## Repo write-access / auth (spike vs production)

Weblate must push translations to a GitHub repo. On the dedicated
`localizationlab.weblate.cloud` instance there is a **single shared instance SSH
key** (ed25519). GitHub only allows a given SSH key as a **deploy key on one repo
across all of GitHub**, so the same key cannot simultaneously serve the fork and
upstream.

- **Spike — no write access needed (deploy key confirmed blocked).** Adding the
  shared ed25519 key to `blazman/SAFETAG` returns GitHub's *"Key is already in
  use"* (it's a deploy key on another LL repo; a key is allowed on only one repo).
  Deploy keys are therefore out. The spike does **not** need push access anyway:
  - **Read** source via the **public HTTPS URL** `https://github.com/blazman/SAFETAG.git`
    (public fork → no credentials to clone), branch `weblate`.
  - **Seed** by committing the snapshot `locales/` (en source + pt_BR + langs) onto
    the `weblate` branch; Weblate ingests source + existing translations on
    component creation.
  - **Round-trip check** via `wlc download` / UI per-file Download (project-admin
    scope, uses the API token — not git write), then `diff` vs the seed and
    `gatsby build` locally.
  All self-service with project-admin + repo-owner rights.
- **Production — `SAFETAG/SAFETAG` (upstream):** the same deploy key **cannot** be
  reused while it's on the fork. Plan to use the **Weblate GitHub App** (scales
  across repos, can push via PRs). This needs permissions **above project-admin**:
  - **SAFETAG org admin** — install the GitHub App / add write access on upstream.
  - **Localization Lab instance admin** — enable the GitHub App integration on the
    instance (project admins cannot configure instance-level SSH/HTTPS creds).
  Line this coordination up early; it is a cutover dependency independent of the
  spike. (Per-project SSH keys, if the instance can be configured for them, would
  sidestep the one-key limit — a question for the LL admins.)

## Appendix A — Trial component settings (Phase 0)

Project slug: `safetag`. Source language: `en`. Format IDs confirmed from Weblate
docs: Markdown = `markdown`, i18next JSON = `i18next` (both monolingual).

Trial content set (exercises the title→title join fully):

| Role | Source file (template) | Title (= join id) |
|---|---|---|
| method | `content/methods/context_research.md` | Context Research |
| activity | `content/activities/regional_context_research.md` | Regional Context Research |
| activity | `content/activities/technical_context_research.md` | Technical Context Research |
| activity | `content/activities/assessing-legal-threats.md` | Assessing legal threats |
| reference | `content/references/context_research.md` | Other Context Analysis Methodologies |
| reference | `content/references/comm_infrastructure_research.md` | Communications infrastructure research |

Per-file Markdown component (one per file above):

```
name/slug   : content_methods_context_research   (mirror the old tx resource slug)
file_format : markdown
vcs         : github            # anchor component only; others link the repo
repo        : git@github.com:blazman/SAFETAG.git     # anchor only (origin fork)
push        : git@github.com:blazman/SAFETAG.git     # anchor only
repo (rest) : weblate://safetag/content_methods_context_research   # linked comps
branch      : weblate            # existing dedicated branch on origin
template    : content/methods/context_research.md          # English source
filemask    : locales/*/content/methods/context_research.md   # * = language code
new_base    : content/methods/context_research.md
source_language : en
# format options
md_extract_frontmatter          : true
md_frontmatter_translate_values : true
md_extract_code_blocks          : false
```

`site.json` component:

```
name/slug   : site
file_format : i18next
repo        : weblate://safetag/content_methods_context_research   # linked
template    : locales/en/site.json
filemask    : locales/*/site.json
source_language : en
```

Bulk edit addon (protect join keys) — apply `read-only` to units whose key/context
matches the join/structural fields, e.g. a search like
`key:title OR key:activities OR key:references OR key:approaches OR key:authors OR key:method_icon`
(confirm the exact context syntax Weblate assigns to frontmatter units during the
spike).

## Appendix B — `.weblate` config + REST component creation

`.weblate` (repo root; URL only — key via env, never commit the key):

```ini
[weblate]
url = https://localizationlab.weblate.cloud/api/
```

`wlc` reads the key from `~/.config/weblate` `[keys]` or `WEBLATE_API_KEY`. `wlc`
cannot create components — use the REST API. Example (anchor component):

```bash
curl -H "Authorization: Token $WEBLATE_API_KEY" \
  -H "Content-Type: application/json" \
  -X POST "https://localizationlab.weblate.cloud/api/projects/safetag/components/" \
  -d '{
    "name": "content_methods_context_research",
    "slug": "content_methods_context_research",
    "vcs": "github",
    "repo": "git@github.com:blazman/SAFETAG.git",
    "push": "git@github.com:blazman/SAFETAG.git",
    "branch": "weblate",
    "file_format": "markdown",
    "template": "content/methods/context_research.md",
    "filemask": "locales/*/content/methods/context_research.md",
    "new_base": "content/methods/context_research.md",
    "source_language": "en"
  }'
```

Linked components reuse the clone: set `"repo": "weblate://safetag/content_methods_context_research"`
and omit `push`/`vcs`. A production creation script (Phase 3) walks
`content/**/*.md`, derives slug (`path` with `/`→`_`) + template + filemask, and
POSTs each as a linked component. The frontmatter format options above must be set
on every content component (component defaults / a template component can carry
them).

## 9. Rollback

Until Phase 6 deletes the Transifex assets, both systems can coexist: Weblate
writes the same `locales/` files the `tx` flow did, so reverting is checking out
the pre-migration workflow files and re-adding `TX_TOKEN`. Keep the final Transifex
golden export archived.
