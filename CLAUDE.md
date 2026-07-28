# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A [Gatsby](https://www.gatsbyjs.com) (v5) static site that publishes the SAFETAG guide
(Security Auditing Framework and Evaluation Template for Advocacy Groups) at
https://safetag.org. Content is authored as Markdown, translated via Weblate, and
the site's marquee feature is a client-side **guide builder** that assembles a custom
PDF from selected content.

Note: the project root is the `SAFETAG/` subdirectory (this is the git repo). Run all
commands from there.

## Commands

```bash
npm install          # Node 20.x required (see .nvmrc / engines)
npm run develop      # dev server at http://localhost:8000 (alias: npm start)
npm run build        # production build to public/
npm run serve        # serve a production build locally
npm run clean        # gatsby clean — run this when GraphQL/schema changes don't take effect
npm run lint         # eslint over **/*.{js,jsx}
npm run format       # prettier --write
```

There is **no test suite** — `npm run test` is a placeholder that just echoes a message.
CI (`.github/workflows/lint-and-test.yml`) only runs lint + that placeholder.

### Translation workflow (Weblate)

**Translations are committed to this repo** under `locales/` — they are not fetched at
build time. A build needs no translation credentials and makes no API calls:
`npm ci && npm run build`.

```bash
npm run extract   # i18next-parser scans JS for t()/Trans strings -> locales/en/site.json
```

That is the only translation-related command. Weblate reads the English source
(`content/**/*.md` and `locales/en/site.json`) straight from the repository and commits
translations back to `locales/<lang>/`. Saving a translation in Weblate therefore
produces a commit here, which triggers a rebuild.

Consequences worth knowing:

- **Weblate owns `locales/`.** Editing those files in git risks being overwritten;
  corrections belong in the Weblate API/UI.
- **Files can lag Weblate's database.** Weblate only re-serializes a file when a unit
  *inside it* changes, and it ignores no-op writes — so a stale value can persist on
  disk after Weblate's own data is correct. Verify against the API before concluding a
  translation is damaged.
- Fixing a defect in the **English source** often repairs the translations
  automatically, via Weblate's "Cleanup translation files" add-on.

The production deploy (`deploy-to-gh-pages.yml`, on push to `main`) is now just
`npm ci` → lint → `npm run build`, publishing `public/` to the `guide` branch via
GitHub Pages.

## Architecture

### Content is the data model

All guide content lives as Markdown-with-YAML-frontmatter under `content/`, organized by
type: `methods/`, `activities/`, `approaches/`, `references/`, `tools/`, `guide_sections/`,
`posts/` (blog), plus taxonomy lists (`authors/`, `skills/`, `infos/`, `remote-options/`).
English files sit at the top level of each dir; translations are layered in at
`locales/<lang>/content/...` at build time.

The SAFETAG taxonomy is hierarchical and expressed through frontmatter cross-references
(by **title string**, not file path): **methods** group **activities**, which reference
**approaches**, **references**, and **tools**. Frontmatter drives both filtering and PDF
assembly — fields like `position` (ordering), `organization_size_under`, `remote_options`,
`time_required_minutes`, `approaches`, `walk_through`, `recommendations`, `overview`.

### Page generation (`gatsby-node.js`)

- `createSchemaCustomization` declares the `Frontmatter` type so optional fields don't
  break the schema when absent from some files.
- `onCreateNode` derives three fields on each MarkdownRemark node from its file path:
  `slug`, `content_type` (method/activity/reference/approach/section/tool/blog post), and
  `langKey`. **Language is inferred from path depth** — a 2-segment relative path is `en`,
  a 4-segment path uses its first segment as the language code. Content type is matched by
  substring in the absolute path.
- `createPages` runs one GraphQL query per content type and renders each via the matching
  layout in `src/components/layouts/` (`method-layout.js`, `activity-layout.js`,
  `tool-layout.js`, `section-layout.js`, `post-layout.js`).

### Guide builder + client-side PDF (the distinctive part)

This is the feature most likely to need care. `src/pages/guide-builder.js` lets users
filter activities/methods and select content; state is serialized into URL query params.
PDF generation happens **entirely in the browser** with PDFKit:

- `src/helpers/useAllGuideData.js` — `useStaticQuery` hook that joins methods with their
  activities into a single object consumed by the builder.
- `src/helpers/generate-guide.js` — converts selected Markdown (via `marked`) into a
  styled PDFKit document, streaming the result to a downloadable blob (`blob-stream` +
  `file-saver`). Fonts are fetched at runtime from `static/fonts/`.
- `src/helpers/pdf-document.js` — PDFKit document/styling layer.
- `src/helpers/footnotes.js` — `loadAllFootnotes` / `processSections` for footnote handling.

Running PDFKit in-browser is why `gatsby-node.js` configures webpack fallbacks
(`stream-browserify`, `process/browser`) and nulls out the `canvas` module during
`build-html`. Touching the PDF path often means revisiting that webpack config.

### Other notable wiring

- **i18n**: `gatsby-plugin-react-i18next`. Active languages are listed in **two** places
  that must stay in sync — `gatsby-config.js` (`languages: [...]`) and
  `i18next-parser.config.js` (`locales: [...]`). Adding a language requires editing both.
- **Search**: `gatsby-plugin-flexsearch` builds a client-side index (English only) over
  frontmatter fields; UI in `src/components/search-*.js` and `src/pages/search.js`.
- **CMS**: Decap CMS (`static/admin/config.yml`, GitHub backend with editorial workflow)
  for editing `content/` through a web UI.
- **Styling**: styled-components with a custom theme system under `src/styles/`
  (`theme/`, `utils/`, etc.). Use the existing `themeVal`/`media` helpers.

## Conventions

- Marking strings translatable: wrap JS strings as `t("unique-key", "English text")`; in
  JSX use `<Trans i18nKey="...">English text</Trans>` (keep `Trans` tight around text,
  avoid nesting non-link elements inside it). See README.md for the full guide.
- ESLint enforces `eslint-plugin-inclusive-language` — flagged terms will fail lint.
- Cross-references in content frontmatter are by human-readable **title**, so renaming a
  method/activity/tool title means updating every file that references it.
