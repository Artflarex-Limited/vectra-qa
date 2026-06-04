"""Site-type -> test catalog mapping for the live QA engineer.

This module is the single source of truth for which tests we run against
each class of target site (landing page, e-commerce store, blog, SaaS
app, internal portal). It replaces the legacy ``chatbot.TEST_TYPES``
dictionary, which conflated test metadata with site-type dispatch and
is slated for removal in T23.

Design rules
------------
* ``SITE_TYPES`` is a ``str, Enum``. Members compare equal to and hash
  like their string value, so call-sites can pass either
  ``SITE_TYPES.ECOMMERCE`` or the plain string ``"ecommerce"`` and
  still match the same set / dict keys. This is the cleanest way to
  satisfy both the typed API (``Set[SiteType]``) and the string
  ergonomics demanded by the QA scenarios.
* The catalog is closed and exhaustive: every ``SITE_TYPES`` member
  MUST appear as a key of ``TEST_CATALOG`` and a member (True/False)
  of ``CREDENTIAL_REQUIRED``. This invariant is verified at import
  time so a missing or typo'd entry fails loud and early, not
  silently in production.
* ``get_default_plan`` returns a *copy* of the catalog list, so callers
  can mutate the result (e.g. drop tests the user declines) without
  poisoning the catalog for the next caller.
* Test names are closed vocabulary. Do NOT add a name that does not
  appear in the catalog for any site type; the vocabulary module (T4)
  treats unknown names as LLM hallucination.
"""

from enum import Enum
from typing import Dict, List, Set, Union


class SITE_TYPES(str, Enum):
    """The five site archetypes the live QA engineer can engage.

    The string value is the canonical wire format (lowercase,
    underscore-separated) and is what flows through the public API.
    Members are ``str, Enum`` mixed-in so that
    ``"ecommerce" in CREDENTIAL_REQUIRED`` works without an explicit
    translation step.

    Order is significant: it is the order the engineer greets the
    user with, the order summaries are presented, and the default
    display order in the command-center UI.
    """

    LANDING = "landing"
    ECOMMERCE = "ecommerce"
    BLOG = "blog"
    SAAS_APP = "saas_app"
    PORTAL = "portal"


# PEP-8 alias: callers and other modules (notably the T3 state machine
# and T11 planner) prefer the singular PascalCase form. ``SITE_TYPES``
# is the canonical name mandated by the live-qa-engineer plan; the
# ``SiteType`` alias exists for forward compatibility with those
# callers and is the form used in type hints throughout this module.
SiteType = SITE_TYPES


# ---------------------------------------------------------------------------
# Test catalog: site_type -> ordered list of test names to execute.
# Order = default execution order. Duplicates are rejected at import.
# ---------------------------------------------------------------------------
TEST_CATALOG: Dict[SiteType, List[str]] = {
    SiteType.LANDING: [
        "homepage",
        "accessibility",
        "responsive",
    ],
    SiteType.ECOMMERCE: [
        "homepage",
        "navigation",
        "product_search",
        "cart_flow",
        "checkout_flow",
        "auth_login",
        "responsive",
        "accessibility",
    ],
    SiteType.BLOG: [
        "homepage",
        "navigation",
        "content_links",
        "responsive",
        "accessibility",
    ],
    SiteType.SAAS_APP: [
        "auth_login",
        "dashboard_load",
        "navigation",
        "core_feature_smoke",
        "responsive",
    ],
    SiteType.PORTAL: [
        "auth_login",
        "dashboard_load",
        "navigation",
        "role_based_access",
        "data_table_render",
        "responsive",
    ],
}


# ---------------------------------------------------------------------------
# Which site types require a username / password before tests can run?
# Rule: any site that has an authenticated area or stores user state
# needs credentials. Landing pages and blogs are reader-only.
# ---------------------------------------------------------------------------
CREDENTIAL_REQUIRED: Set[SiteType] = {
    SiteType.ECOMMERCE,
    SiteType.SAAS_APP,
    SiteType.PORTAL,
}


# ---------------------------------------------------------------------------
# Plain-English descriptions.
# Used in the greeting, the recon summary, the plan preview, and the
# final report. The whole point of the live engineer is to speak to
# non-technical stakeholders — these strings are user-facing copy.
# ---------------------------------------------------------------------------
SITE_TYPE_DESCRIPTIONS: Dict[SiteType, str] = {
    SiteType.LANDING: (
        "A single-page marketing site. No login, no transactions \u2014 "
        "just messaging, calls to action, and a way to get in touch."
    ),
    SiteType.ECOMMERCE: (
        "An online store. Browse products, search the catalog, add to "
        "cart, check out, and log in to an account. May need a payment "
        "sandbox to test the full purchase flow."
    ),
    SiteType.BLOG: (
        "A content site with articles, categories, and links to related "
        "posts. Reader-only \u2014 no accounts or transactions."
    ),
    SiteType.SAAS_APP: (
        "A logged-in web application with a dashboard and core feature "
        "flows. Needs a real (or sandbox) user account to reach the "
        "areas that matter."
    ),
    SiteType.PORTAL: (
        "A role-based portal with dashboards, data tables, and gated "
        "sections. Needs at least one test account per role to verify "
        "that the right people see the right things."
    ),
}


# ---------------------------------------------------------------------------
# Import-time invariants.
# Fail loud here so a typo or missing entry is caught the first time
# anything imports this module \u2014 not three hours into a live run.
# ---------------------------------------------------------------------------
_missing_in_catalog = set(SiteType) - set(TEST_CATALOG)
if _missing_in_catalog:
    raise RuntimeError(
        f"TEST_CATALOG is missing entries for site types: "
        f"{sorted(_missing_in_catalog)}"
    )

_extra_in_catalog = set(TEST_CATALOG) - set(SiteType)
if _extra_in_catalog:
    raise RuntimeError(
        f"TEST_CATALOG has unknown site_type keys: "
        f"{sorted(_extra_in_catalog)}"
    )

for _st, _plan in TEST_CATALOG.items():
    if not isinstance(_plan, list) or not _plan:
        raise RuntimeError(
            f"TEST_CATALOG[{_st!r}] must be a non-empty list of test names"
        )
    if len(set(_plan)) != len(_plan):
        raise RuntimeError(
            f"TEST_CATALOG[{_st!r}] contains duplicate test names: {_plan}"
        )


def get_default_plan(site_type: Union[SiteType, str]) -> List[str]:
    """Return the default ordered test plan for ``site_type``.

    Accepts either a :class:`SITE_TYPES` member (e.g.
    ``SITE_TYPES.ECOMMERCE``) or its canonical string value (e.g.
    ``"ecommerce"``). The string is matched case-insensitively and
    with surrounding whitespace stripped.

    Returns a *new list* on every call \u2014 mutating the result (for
    example, dropping tests the user declined) does not affect
    ``TEST_CATALOG`` for subsequent callers.

    Raises
    ------
    ValueError
        If ``site_type`` is a string that does not correspond to a
        known :class:`SITE_TYPES` member.
    """
    if isinstance(site_type, str):
        normalized = site_type.strip().lower()
        # ``SITE_TYPES(<value>)`` raises ValueError for unknown strings,
        # which is the failure mode we want at the API edge.
        site_type = SITE_TYPES(normalized)
    return list(TEST_CATALOG[site_type])


__all__ = [
    "SITE_TYPES",
    "SiteType",
    "TEST_CATALOG",
    "CREDENTIAL_REQUIRED",
    "SITE_TYPE_DESCRIPTIONS",
    "get_default_plan",
]
