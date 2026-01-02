from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import frappe
from frappe import _

from imogi_finance import approval


class ApprovalRouteService:
    """Service wrapper for approval route resolution and logging."""

    @staticmethod
    def normalize_accounts(accounts: str | Iterable[str]) -> tuple[str, ...]:
        return approval._normalize_accounts(accounts)  # type: ignore[attr-defined]

    @staticmethod
    def get_route(cost_center: str, accounts: Iterable[str], amount: float, *, setting_meta: dict | None = None) -> dict:
        return approval.get_approval_route(cost_center, accounts, amount, setting_meta=setting_meta)

    @staticmethod
    def record_setting_meta(doc: Any, setting_meta: dict | None):
        if not setting_meta or not doc:
            return
        if isinstance(setting_meta, str):
            doc.approval_setting = setting_meta
            return
        if not isinstance(setting_meta, dict):
            doc.approval_setting = str(setting_meta)
            return
        doc.approval_setting = setting_meta.get("name") or getattr(doc, "approval_setting", None)
        if setting_meta.get("modified") is not None:
            doc.approval_setting_last_modified = setting_meta.get("modified")

    @staticmethod
    def log_resolution_error(exc: Exception, *, cost_center: str | None = None, accounts=None, amount=None):
        approval.log_route_resolution_error(exc, cost_center=cost_center, accounts=accounts, amount=amount)

    @staticmethod
    def approval_setting_required_message(cost_center: str | None = None) -> str:
        return approval.approval_setting_required_message(cost_center)
