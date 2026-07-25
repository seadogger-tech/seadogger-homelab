#!/usr/bin/env python3
"""Fix a real gap in mealie-recipes/mealie PR #7618 ("Force OpenAI
Scraper" checkbox), confirmed present both in our pinned v3.21.0 base and
in current upstream mealie-next as of 2026-07-25.

The frontend checkbox's visibility guard (`v-if="$appInfo.enableOpenai"`
in create/url.vue and create/bulk.vue) references a field that does not
exist anywhere in the AppInfo schema or the /api/app/about route that
populates it - the checkbox is therefore permanently hidden regardless of
any AI provider configuration, even though the backend `use_openai` field
itself is correctly wired through create_from_html() by this same PR.

Add `enable_openai: bool` to AppInfo and populate it in the
(unauthenticated) /api/app/about route, using the same default-group
lookup the route already performs for default_group_slug.

Used by .github/workflows/mealie-rebuild.yaml, run from inside the
`upstream` checkout after PR #7618's real feature commit (b9e120bc,
NOT the branch tip - see the workflow's cherry-pick step comment for
why) has been applied.

Usage: python3 patch_mealie_force_openai.py
"""

ABOUT_SCHEMA = "mealie/schema/admin/about.py"
ABOUT_ROUTE = "mealie/routes/app/app_about.py"


def patch_app_info_schema():
    with open(ABOUT_SCHEMA) as f:
        content = f.read()

    marker = "    allowed_iframe_hosts: list[str] = []"
    if marker not in content:
        raise SystemExit(
            f"patch_app_info_schema: expected field not found in {ABOUT_SCHEMA} "
            "- AppInfo schema may have changed. Manual update needed."
        )
    if "enable_openai" in content:
        print(f"{ABOUT_SCHEMA}: enable_openai already present, skipping")
        return

    content = content.replace(
        marker,
        marker + "\n    enable_openai: bool = False",
    )
    with open(ABOUT_SCHEMA, "w") as f:
        f.write(content)
    print(f"Patched {ABOUT_SCHEMA}: added enable_openai field to AppInfo")


def patch_about_route():
    with open(ABOUT_ROUTE) as f:
        content = f.read()

    if "enable_openai" in content:
        print(f"{ABOUT_ROUTE}: enable_openai already wired, skipping")
        return

    # Insert the lookup right after the existing default_household_slug
    # block, reusing the same public_repos/default_group already computed
    # by this (unauthenticated) route for default_group_slug.
    anchor = (
        '    if default_group and default_group_slug:\n'
        '        group_repos = get_repositories(session, group_id=default_group.id, household_id=None)\n'
        '        default_household = group_repos.households.get_by_name(settings.DEFAULT_HOUSEHOLD)\n'
        '        if default_household and default_household.preferences and not default_household.preferences.private_household:\n'
        '            default_household_slug = default_household.slug\n'
    )
    if anchor not in content:
        raise SystemExit(
            f"patch_about_route: expected default_household_slug block not found in {ABOUT_ROUTE} "
            "- route may have changed. Manual update needed."
        )

    lookup = (
        "\n    enable_openai = False\n"
        "    if default_group:\n"
        "        group_repos = get_repositories(session, group_id=default_group.id, household_id=None)\n"
        "        ai_settings = group_repos.group_ai_provider_settings.get_one(default_group.id)\n"
        "        enable_openai = bool(ai_settings and ai_settings.ai_enabled)\n"
    )
    content = content.replace(anchor, anchor + lookup, 1)

    return_marker = "    return AppInfo(\n"
    if return_marker not in content:
        raise SystemExit(
            f"patch_about_route: 'return AppInfo(' not found in {ABOUT_ROUTE} "
            "- route may have changed. Manual update needed."
        )
    content = content.replace(
        return_marker,
        return_marker + "        enable_openai=enable_openai,\n",
        1,
    )

    with open(ABOUT_ROUTE, "w") as f:
        f.write(content)
    print(f"Patched {ABOUT_ROUTE}: enable_openai now reflects the default group's AI settings")


if __name__ == "__main__":
    patch_app_info_schema()
    patch_about_route()
