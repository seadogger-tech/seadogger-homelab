#!/usr/bin/env python3
"""One V01 API observation against an already authorized, closed synthetic target."""

import argparse
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import ssl
import sys
from datetime import datetime, timezone
from urllib.parse import quote, urlsplit

SOURCE_URL = "https://recipes.test/ordinary-web.html"
CANDIDATE_SOURCE = "9552df62118224a377d9c9b0a62706a62220ab86"
CANDIDATE_INDEX = "sha256:90f83da6f3ab0a421efc827118a556168573930105f13fa3321768f42163d784"
CANDIDATE_ARM64 = "sha256:8dbe3fd73896e77c797f7029201823fa8b1ddbc725059f496cf884f06c9916da"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class CheckFailure(Exception):
    """Only fixed, secret-free diagnostic labels may be raised."""


def request_json(target, token, method, path, expected_status, payload=None):
    """One request, verified TLS, no redirects, ambient proxies or retries."""
    connection = http.client.HTTPSConnection(
        target.hostname, target.port or 443, timeout=60,
        context=ssl.create_default_context(),
    )
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        if response.status != expected_status:
            raise CheckFailure("unexpected_http_status_" + str(response.status))
        data = response.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise CheckFailure("response_exceeds_client_read_limit")
        return json.loads(data)
    except CheckFailure:
        raise
    except (OSError, ValueError, http.client.HTTPException):
        # Exception messages and bodies may contain credentials or source content.
        raise CheckFailure("transport_or_json_error") from None
    finally:
        connection.close()


def text(value):
    """Normalize whitespace only; never strip markup or discard recipe words."""
    return " ".join(value.split()) if isinstance(value, str) else None


def ingredient_text(value):
    value = text(value)
    if value is None:
        return None
    # Equivalent spellings of the fixture's half teaspoon; keep all other facts.
    return re.sub(r"^(?:0[.]5|½|1⁄2)(?=\s)", "1/2", value)


def duration_matches(recipe, text_key, seconds_key, expected_iso):
    # This single fixture supplies whole-minute durations, independently in JSON.
    minutes = int(re.fullmatch(r"PT(\d+)M", expected_iso).group(1))
    acceptable = {expected_iso, str(minutes), f"{minutes}m",
                  f"{minutes} min", f"{minutes} minute", f"{minutes} minutes"}
    legacy = recipe.get(text_key)
    seconds = recipe.get(seconds_key)
    if seconds is not None:
        return (
            type(seconds) in (int, float)
            and seconds == minutes * 60
            and (legacy in (None, "") or text(legacy) in acceptable)
        )
    return text(legacy) in acceptable


def compare_saved_recipe(recipe, expected):
    """Compare the reopened API representation with the pre-authored oracle."""
    checks = {
        "title": text(recipe.get("name")) == expected["name"],
        "provenance": recipe.get("orgURL") == expected["source_url"],
        "prep_time": duration_matches(recipe, "prepTime", "prepTimeSeconds", expected["prep_time"]),
        "cook_time": duration_matches(recipe, "performTime", "performTimeSeconds", expected["cook_time"]),
        "total_time": duration_matches(recipe, "totalTime", "totalTimeSeconds", expected["total_time"]),
    }
    # Upstream exposes servings separately from a non-serving yield (e.g. loaves).
    # A retained literal is also acceptable, but contradictory nonzero fields fail.
    serving_count = int(expected["recipe_yield"].split()[0])
    yield_text = text(recipe.get("recipeYield"))
    servings = recipe.get("recipeServings")
    quantity = recipe.get("recipeYieldQuantity")
    checks["yield"] = (
        (servings == serving_count and yield_text in (None, "", "servings"))
        or yield_text == expected["recipe_yield"]
        or (quantity == serving_count and yield_text == "servings")
    ) and servings in (None, 0, serving_count) and quantity in (None, 0, serving_count)
    # cookTime is a legacy API field. If populated, it must not contradict the
    # current performTime/performTimeSeconds representation checked above.
    if recipe.get("cookTime") not in (None, ""):
        checks["cook_time"] = checks["cook_time"] and duration_matches(
            recipe, "cookTime", "unusedSeconds", expected["cook_time"]
        )
    ingredients = recipe.get("recipeIngredient")
    checks["ingredients"] = (
        isinstance(ingredients, list)
        and all(isinstance(item, dict) for item in ingredients)
        and [ingredient_text(item.get("display")) for item in ingredients]
        == [ingredient_text(item) for item in expected["ingredients"]]
    )
    steps = recipe.get("recipeInstructions")
    checks["instruction_order"] = (
        isinstance(steps, list)
        and all(isinstance(item, dict) for item in steps)
        and [text(item.get("text")) for item in steps] == expected["instructions"]
    )
    checks["no_added_notes"] = recipe.get("notes") in (None, [])
    # "no image" is the candidate's no-source-image placeholder, not a URL.
    checks["no_added_image"] = recipe.get("image") in (None, "", "no image")
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true",
                        help="Send one mutating import; requires prior target authorization")
    parser.add_argument("--base-url", required=True, help="Approved synthetic HTTPS target origin")
    parser.add_argument("--source-ref", required=True, help="Exact reviewed Core source SHA")
    parser.add_argument("--authorization-ref", required=True)
    parser.add_argument("--controls-ref", required=True, help="Protected P0 enforcement receipt reference")
    parser.add_argument("--identity-ref", required=True, help="Reverified image/runtime identity receipt reference")
    parser.add_argument("--config-ref", required=True, help="Reviewed synthetic target configuration revision")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required; this writes one recipe")
    if not re.fullmatch(r"[0-9a-f]{40}", args.source_ref):
        parser.error("--source-ref must be a full commit SHA")
    # References are opaque metadata. Do not put secrets or URLs in these fields.
    for name in ("authorization_ref", "controls_ref", "identity_ref", "config_ref"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,199}", getattr(args, name)):
            parser.error("receipt references must be nonempty opaque identifiers")
    try:
        target = urlsplit(args.base_url)
        valid_target = (
            target.scheme == "https" and target.hostname
            and target.username is None and target.password is None
            and not target.query and not target.fragment and target.path in ("", "/")
        )
        target.port  # Validate the port before touching the network.
    except ValueError:
        valid_target = False
    if not valid_target:
        parser.error("--base-url must be an HTTPS origin without credentials, path, query or fragment")
    token = os.environ.get("MEALIE_TEST_TOKEN", "")
    if not token or not token.isascii() or any(char.isspace() for char in token):
        parser.error("MEALIE_TEST_TOKEN must contain the protected synthetic-account token")

    try:
        oracle_bytes = (FIXTURES / "ordinary-web.expected.json").read_bytes()
        html_bytes = (FIXTURES / "ordinary-web.html").read_bytes()
        expected = json.loads(oracle_bytes)
        if expected["source_url"] != SOURCE_URL or expected["case"] != "V01":
            raise CheckFailure("unexpected_fixture_identity")
    except (OSError, ValueError, KeyError, TypeError, CheckFailure):
        print('{"case":"V01","api_observation":"not_run","reason":"invalid_fixture"}')
        return 2

    receipt = {
        "case": "V01", "seam": "S1", "source_ref": args.source_ref,
        "candidate_expected": {"source": CANDIDATE_SOURCE, "index": CANDIDATE_INDEX, "arm64": CANDIDATE_ARM64},
        "authorization_ref": args.authorization_ref, "controls_ref": args.controls_ref,
        "identity_ref": args.identity_ref, "config_ref": args.config_ref,
        "fixture_sha256": hashlib.sha256(html_bytes).hexdigest(),
        "oracle_sha256": hashlib.sha256(oracle_bytes).hexdigest(),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "requested_mode": "ordinary_url",
        "acceptance": "pending_ui_provider_and_environment_evidence",
        "post_attempted": False,
    }
    exit_code = 1
    try:
        receipt["post_attempted"] = True
        slug = request_json(target, token, "POST", "/api/recipes/create/url", 201, {
            "url": SOURCE_URL, "includeTags": False, "includeCategories": False,
        })
        if not isinstance(slug, str) or not slug or len(slug) > 250:
            raise CheckFailure("invalid_created_slug")
        recipe = request_json(target, token, "GET", "/api/recipes/" + quote(slug, safe=""), 200)
        if not isinstance(recipe, dict) or not recipe.get("id") or recipe.get("slug") != slug:
            raise CheckFailure("invalid_reopened_recipe")
        receipt["checks"] = compare_saved_recipe(recipe, expected)
        matched = all(receipt["checks"].values())
        receipt["api_observation"] = "matched" if matched else "mismatch"
        exit_code = 0 if matched else 1
    except CheckFailure as exc:
        receipt["api_observation"] = "inconclusive"
        receipt["reason"] = str(exc)
    except (KeyError, TypeError, ValueError, AttributeError):
        receipt["api_observation"] = "inconclusive"
        receipt["reason"] = "unexpected_recipe_or_oracle_shape"
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    receipt["follow_up"] = "retain_run_state_no_automatic_retry_or_cleanup"
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
