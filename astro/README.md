# Astro Documentation App

This directory contains a standalone plain Astro + MDX site for project documentation.

## Intended source of truth

- Source docs stay in `../src/docs`
- Synced Astro pages are written to `./src/pages`

## Local usage

```bash
cd astro
bun install
bun run dev
```

## Sync docs manually

```bash
cd astro
bun run sync-docs
```

The sync script copies the `../src/docs` tree into `src/pages/docs`, preserves nested `.md` and `.mdx` files, and injects the shared docs layout frontmatter when needed.
