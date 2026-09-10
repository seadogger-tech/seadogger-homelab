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

The `>>>>>>>` marker's commit hash is matched as [0-9a-f]+ rather than a
fixed 8-char abbreviation: git auto-scales the abbreviation length by the
repo's object count, so a full CI checkout emits e.g. `b9e120bce` (10)
while a shallow local clone emits `b9e120bc` (8). Hardcoding the length
made this step fail only in CI.

If a future upstream change touches the same call sites again, the
patterns below may stop matching; this raises SystemExit with a clear
message rather than silently doing nothing, so the workflow step fails
loudly.
"""

import re

SCRAPER_PY = "mealie/services/scraper/scraper.py"
BULK_SCRAPER_PY = "mealie/services/scraper/recipe_bulk_scraper.py"
CRUD_ROUTES_PY = "mealie/routes/recipe/recipe_crud_routes.py"

# Trailing conflict marker, abbreviation-length agnostic.
END = r">>>>>>> [0-9a-f]+ \(feat: add Force OpenAI Scraper option to URL and bulk import\)"


def _resolve(path, pattern, new, label):
    with open(path) as f:
        content = f.read()
    if not pattern.search(content):
        raise SystemExit(
            f"{label}: expected conflict pattern not found in {path} - upstream "
            "code may have changed around this call site, or the conflict marker "
            "shape changed. Manual rebase needed."
        )
    content = pattern.sub(lambda _m: new, content)
    _write_and_verify(content, path)


def resolve_scraper_py():
    pattern = re.compile(
        r"<<<<<<< HEAD\n"
        r"    scraper = RecipeScraper\(repos, translator\)\n"
        r"=======\n"
        r"    scrapers = \[RecipeScraperOpenAITranscription, RecipeScraperOpenAI\] if use_openai else None\n"
        r"    scraper = RecipeScraper\(translator, scrapers=scrapers\)\n"
        + END
    )
    new = (
        "    scrapers = [RecipeScraperOpenAITranscription, RecipeScraperOpenAI] if use_openai else None\n"
        "    scraper = RecipeScraper(repos, translator, scrapers=scrapers)"
    )
    _resolve(SCRAPER_PY, pattern, new, "resolve_scraper_py")


def resolve_bulk_scraper_py():
    pattern = re.compile(
        r"<<<<<<< HEAD\n"
        r"                    recipe, _ = await create_from_html\(url, self\.repos, self\.translator\)\n"
        r"=======\n"
        r"                    recipe, _ = await create_from_html\(url, self\.translator, use_openai=urls\.use_openai\)\n"
        + END
    )
    new = "                    recipe, _ = await create_from_html(url, self.repos, self.translator, use_openai=urls.use_openai)"
    _resolve(BULK_SCRAPER_PY, pattern, new, "resolve_bulk_scraper_py")


def resolve_crud_routes_py():
    pattern = re.compile(
        r"<<<<<<< HEAD\n"
        r"                recipe, extras = await create_from_html\(url, self\.repos, self\.translator, html, on_progress=on_progress\)\n"
        r"=======\n"
        r"                recipe, extras = await create_from_html\(url, self\.translator, html, on_progress=on_progress, use_openai=use_openai\)\n"
        + END
    )
    new = "                recipe, extras = await create_from_html(url, self.repos, self.translator, html, on_progress=on_progress, use_openai=use_openai)"
    _resolve(CRUD_ROUTES_PY, pattern, new, "resolve_crud_routes_py")


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
