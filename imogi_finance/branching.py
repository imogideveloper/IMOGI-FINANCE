from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

import frappe
from frappe import _

BRANCH_SETTING_DEFAULTS = {
    "enable_multi_branch": 0,
    "inherit_branch_from_cost_center": 1,
    "default_branch": None,
    "enforce_branch_on_links": 1,
}


def _get_settings_doc():
    try:
        return frappe.get_cached_doc("Finance Control Settings")
    except Exception:
        try:
            return frappe.get_single("Finance Control Settings")
        except Exception:
            return None


@lru_cache()
def get_branch_settings():
    settings = frappe._dict(BRANCH_SETTING_DEFAULTS.copy())
    if not getattr(frappe, "db", None):
        return settings

    if not frappe.db.exists("DocType", "Finance Control Settings"):
        return settings

    record = _get_settings_doc()
    if not record:
        return settings

    for key in settings.keys():
        settings[key] = getattr(record, key, settings[key])

    return settings


def clear_branch_settings_cache():
    get_branch_settings.cache_clear()


def _has_branch_field(doctype: str) -> bool:
    try:
        if not frappe.db or not frappe.db.exists("DocType", doctype):
            return False
        return bool(frappe.db.has_column(doctype, "branch"))
    except Exception:
        return False


def resolve_branch(
    *,
    company: Optional[str] = None,
    cost_center: Optional[str] = None,
    explicit_branch: Optional[str] = None,
) -> Optional[str]:
    """Resolve the branch to apply based on global settings and context."""

    settings = get_branch_settings()
    if not settings.enable_multi_branch:
        return None

    if explicit_branch:
        return explicit_branch

    resolved = None

    if settings.inherit_branch_from_cost_center and cost_center:
        if _has_branch_field("Cost Center"):
            resolved = frappe.db.get_value("Cost Center", cost_center, "branch")
        if not resolved and frappe.db.exists("DocType", "Branch") and frappe.db.has_column("Branch", "cost_center"):
            resolved = frappe.db.get_value("Branch", {"cost_center": cost_center}, "name")

    if resolved:
        return resolved

    if settings.default_branch:
        return settings.default_branch

    if company and _has_branch_field("Company"):
        return frappe.db.get_value("Company", company, "default_branch")

    return None


def apply_branch(doc: Any, branch: Optional[str]) -> None:
    """Set branch on document if supported and provided."""

    if not branch or not _has_branch_field(getattr(doc, "doctype", "")):
        return

    setattr(doc, "branch", branch)


def validate_branch_alignment(current_branch: Optional[str], expected_branch: Optional[str], *, label: str) -> None:
    """Raise if branches mismatch when enforcement is enabled."""

    settings = get_branch_settings()
    if not settings.enable_multi_branch or not settings.enforce_branch_on_links:
        return

    if not current_branch or not expected_branch or current_branch == expected_branch:
        return

    frappe.throw(
        _("Branch mismatch for {0}. Expected {1} but found {2}.").format(
            label, expected_branch, current_branch
        ),
        title=_("Branch Mismatch"),
    )


def doc_supports_branch(doctype: str) -> bool:
    return _has_branch_field(doctype)
