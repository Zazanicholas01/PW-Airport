# Astro Documentation App

This directory contains a standalone Astro + Starlight site for project documentation.

## Intended source of truth

- Source Markdown stays in `../src/docs`
- Generated Starlight content is written to `./src/content/docs/generated`

## Local usage

```bash
cd astro
npm install
npm run dev
```

## Sync docs manually

```bash
cd astro
npm run sync-docs
```

The sync script copies each `README.md` from `../src/docs/*` into Starlight content and adds a basic title frontmatter when missing.
