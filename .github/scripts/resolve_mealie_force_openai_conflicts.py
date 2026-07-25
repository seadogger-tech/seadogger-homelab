#!/usr/bin/env python3
"""Resolve a known, expected cherry-pick conflict when adopting the real
feature commit from mealie-recipes/mealie PR #7618 ("Force OpenAI
Scraper" checkbox) on top of our pinned v3.21.0 tag.

Used by .github/workflows/mealie-rebuild.yaml. Run from inside the
`upstream` checkout, after `git cherry-pick b9e120bc` has stopped on a
conflict in scraper.py / recipe_bulk_scraper.py / recipe_crud_routes.py.

Why the conflict happens: PR #7618's feature commit was written against
an older `RecipeScraper(translator, scrapers=...)` constructor. Our
pinned v3.21.0 tag already has a newer
`RecipeScraper(repos, translator, scrapers=...)` signature - `repos` was
added independently sometime after this PR branch forked from upstream.
The conflict is pure adjacency (both sides touch the same call site),
not a real logic disagreement: resolve by keeping the newer repos-aware
constructor/function calls while applying the PR's actual behavioral
change (build a conditional `scrapers` list based on `use_openai`).

If a future upstream change touches the same call sites again, the
patterns below may stop matching; this raises SystemExit with a clear
message rather than silently doing nothing, so the workflow step fails
loudly.
"""

SCRAPER_PY = "mealie/services/scraper/scraper.py"
BULK_SCRAPER_PY = "mealie/services/scraper/recipe_bulk_scraper.py"
CRUD_ROUTES_PY = "mealie/routes/recipe/recipe_crud_routes.py"


def resolve_scraper_py():
    with open(SCRAPER_PY) as f:
        content = f.read()

    old = (
        "<<<<<<< HEAD\n"
        "    scraper = RecipeScraper(repos, translator)\n"
        "=======\n"
        "    scrapers = [RecipeScraperOpenAITranscription, RecipeScraperOpenAI] if use_openai else None\n"
        "    scraper = RecipeScraper(translator, scrapers=scrapers)\n"
        ">>>>>>> b9e120bc (feat: add Force OpenAI Scraper option to URL and bulk import)"
    )
    if old not in content:
        raise SystemExit(
            f"resolve_scraper_py: expected conflict pattern not found in {SCRAPER_PY} "
            "- upstream code may have changed around RecipeScraper's constructor call. "
            "Manual rebase needed."
        )

    new = (
        "    scrapers = [RecipeScraperOpenAITranscription, RecipeScraperOpenAI] if use_openai else None\n"
        "    scraper = RecipeScraper(repos, translator, scrapers=scrapers)"
    )
    content = content.replace(old, new)
    _write_and_verify(content, SCRAPER_PY)


def resolve_bulk_scraper_py():
    with open(BULK_SCRAPER_PY) as f:
        content = f.read()

    old = (
        "<<<<<<< HEAD\n"
        "                    recipe, _ = await create_from_html(url, self.repos, self.translator)\n"
        "=======\n"
        "                    recipe, _ = await create_from_html(url, self.translator, use_openai=urls.use_openai)\n"
        ">>>>>>> b9e120bc (feat: add Force OpenAI Scraper option to URL and bulk import)"
    )
    if old not in content:
        raise SystemExit(
            f"resolve_bulk_scraper_py: expected conflict pattern not found in {BULK_SCRAPER_PY} "
            "- upstream code may have changed around the bulk-scrape create_from_html call. "
            "Manual rebase needed."
        )

    new = "                    recipe, _ = await create_from_html(url, self.repos, self.translator, use_openai=urls.use_openai)"
    content = content.replace(old, new)
    _write_and_verify(content, BULK_SCRAPER_PY)


def resolve_crud_routes_py():
    with open(CRUD_ROUTES_PY) as f:
        content = f.read()

    old = (
        "<<<<<<< HEAD\n"
        "                recipe, extras = await create_from_html(url, self.repos, self.translator, html, on_progress=on_progress)\n"
        "=======\n"
        "                recipe, extras = await create_from_html(url, self.translator, html, on_progress=on_progress, use_openai=use_openai)\n"
        ">>>>>>> b9e120bc (feat: add Force OpenAI Scraper option to URL and bulk import)"
    )
    if old not in content:
        raise SystemExit(
            f"resolve_crud_routes_py: expected conflict pattern not found in {CRUD_ROUTES_PY} "
            "- upstream code may have changed around _create_recipe_from_web's create_from_html call. "
            "Manual rebase needed."
        )

    new = "                recipe, extras = await create_from_html(url, self.repos, self.translator, html, on_progress=on_progress, use_openai=use_openai)"
    content = content.replace(old, new)
    _write_and_verify(content, CRUD_ROUTES_PY)


def _write_and_verify(content, path):
    # Only check the actual git conflict markers (<<<<<<< / >>>>>>>), not a
    # bare "=======" - that 7-char run is common in code/docstrings as a
    # plain divider and produces false positives here.
    if "<<<<<<<" in content or ">>>>>>>" in content:
        raise SystemExit(f"conflict markers remain in {path} after patch - manual rebase needed.")
    with open(path, "w") as f:
        f.write(content)
    print(f"Resolved conflict in {path}")


if __name__ == "__main__":
    resolve_scraper_py()
    resolve_bulk_scraper_py()
    resolve_crud_routes_py()
