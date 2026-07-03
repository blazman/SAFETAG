# Weblate spike runbook (Phase 0 execution)

Click-by-click steps to run the validation spike on `localizationlab.weblate.cloud`.
Companion to `weblate-migration.md` (see §3, §3a, §3b, Appendix A/B). Goal: prove
Weblate ingests the repaired seed, re-serializes valid YAML with all frontmatter
translated, restores true translated-state, and Gatsby builds — using public read
+ download (no repo write access).

## Prerequisites

- Seed committed to branch **`weblate`** of **`github.com/blazman/SAFETAG`** (public):
  run `python3 scripts/stage-seed.py --from <snapshot> --repair`, review, commit
  `locales/`. Must include `locales/en/site.json` (the i18next template).
- Weblate project **`safetag`** exists; you are **project admin**.
- API token exported for any REST/`wlc` steps:
  `export WEBLATE_API_KEY=…` (from `…/accounts/profile/#api`).
- `.weblate` at repo root: `[weblate]\nurl = https://localizationlab.weblate.cloud/api/`

## 1. Anchor Markdown component — `context_research` (method)

UI: **Projects → safetag → Add new translation component**.
- **Source code repository:** `https://github.com/blazman/SAFETAG.git` (public HTTPS,
  no auth for the spike). **Branch:** `weblate`.
- **File format:** `Markdown files`.
- **File mask:** `locales/*/content/methods/context_research.md`
- **Monolingual base language file (template):** `content/methods/context_research.md`
- **Template for new translations / new base:** same as template.
- **Source language:** English (`en`).
- **Name/slug:** `content_methods_context_research`.

(Equivalent REST call in migration doc Appendix B.) On save, Weblate clones and
imports the existing `locales/<lang>/…` translations for all 12 languages.

## 2. Two activity components (linked repo, so the clone is shared)

Repeat step 1 for these, but set **Source code repository** to the Weblate
internal URL `weblate://safetag/content_methods_context_research` (no repo/branch
re-entry, no second clone):

| slug | template | file mask |
|---|---|---|
| `content_activities_regional_context_research` | `content/activities/regional_context_research.md` | `locales/*/content/activities/regional_context_research.md` |
| `content_activities_technical_context_research` | `content/activities/technical_context_research.md` | `locales/*/content/activities/technical_context_research.md` |

(`technical_context_research` is largely untranslated in pt_BR — deliberately kept
to test source-fallback for dropped fields.)

## 3. `site.json` component (i18next, linked repo)

- **Repository:** `weblate://safetag/content_methods_context_research`
- **File format:** `i18next JSON`
- **File mask:** `locales/*/site.json`
- **Template:** `locales/en/site.json`
- **Source language:** `en`; **slug:** `site`.

## 4. Frontmatter options (each Markdown component)

Component → **Manage → Settings → Format** (the Markdown format options):
- `md_extract_frontmatter` = **on**
- `md_frontmatter_translate_values` = **on**  (translate all — matches production)
- `md_extract_code_blocks` = **off**

## 5. Protect image-path fields as read-only (Bulk edit addon)

Per Markdown component → **Manage → Add-ons → Bulk edit** (id `weblate.flags.bulk`):
- **Query (q):** `key:method_icon OR key:the_flow_of_information`
- **Translation flags to add:** `read-only`

(Confirm the unit key/context by opening one translation and checking how Weblate
labels the frontmatter units; adjust `key:` accordingly.)

## 6. Verify the seed imported

- Component shows 12 languages; pt_BR shows a **high completion %** — expected and
  *wrong* (it counts English-fallback as translated). We fix that next.
- Open `context_research` pt_BR: the previously-swallowed keys (`short_summary`,
  `authors`, `preparation`) should now be real, translated units.

## 7. Restore true translated-state (same-as-source bulk-clear) — §3b

Per component → **Bulk edit** add-on (a second instance, or run once):
- **Query (q):** `check:unchanged AND state:translated AND NOT flag:read-only`
- **State to set:** `Needs editing` (value `10`)

This flips every unit whose translation equals its source (English fallback) to
needs-editing, excluding the read-only image paths. pt_BR completion should now
**drop to the true figure**. If it doesn't drop, Weblate is treating
same-as-source differently than assumed — stop and re-check.

## 8. Round-trip: download + local build (no write access needed)

- Download Weblate's serialization: `wlc download safetag/content_methods_context_research`
  (or component → **Files → Download translated files** → ZIP). Repeat per component,
  or `wlc download safetag` for all.
- Place the downloaded `locales/<lang>/…` files into the repo working tree and
  `npm run build` (or parse the YAML) for pt_BR.

## 9. Exit criteria (from migration doc §5)

- [ ] Weblate output is **valid YAML**; swallowed keys are present as real keys
      (corruption fixed, not propagated).
- [ ] All frontmatter translated except `method_icon` / `the_flow_of_information`
      (still `/img/...` paths).
- [ ] `gatsby build` succeeds; pt_BR `context_research` page renders **with** the
      recovered fields and resolves its activities/references.
- [ ] After step 7, pt_BR completion reflects the true translated figure (English
      fallbacks now show as needs-editing / untranslated).
- [ ] Rendered pt_BR pages are equal-or-better than the current live site.

If all pass → the format + seed + state approach is proven; proceed to Phase 1–6
(scale to 245 components via Discovery/REST, workflows, cutover).
