# markjonleonard.github.io

Personal site and blog, built with [Zola](https://www.getzola.org) (0.23, Tera v2 templates) and deployed to GitHub Pages by `.github/workflows/deploy.yml` on every push to `main`.

## Writing

```sh
brew install zola
zola serve          # http://127.0.0.1:1111, live reload
```

New post: add `content/blog/YYYY-MM-DD-slug.md`:

```toml
+++
title = "Post title"
date = 2026-09-28

[taxonomies]
tags = ["dev"]
+++

Markdown here.
```

The date prefix in the filename is stripped from the URL (`/blog/slug/`).

## Layout

- `content/` — pages and posts (`_index.md` is the home page intro)
- `templates/` — `base.html` shell, `components.html` (Tera v2 components), one template per page type
- `sass/style.scss` — all styling; light/dark via `prefers-color-scheme`
- `scripts/import_blogger.py` — one-off import of the old weakspeak.blogspot.com posts from the public Blogger feed
