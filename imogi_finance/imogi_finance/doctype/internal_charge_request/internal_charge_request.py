# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

from imogi_finance import accounting
from imogi_finance.approval import get_active_setting_meta, get_approval_route, log_route_resolution_error
from imogi_finance.budget_control import service, utils
from imogi_finance.budget_control.workflow import _parse_route_snapshot

try:
    from frappe.model.document import Document
except Exception:  # pragma: no cover - fallback for test stubs
    class Document:  # type: ignore
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)


class InternalChargeRequest(Document):
    """Request to allocate an Expense Request across multiple cost centers."""

    def validate(self):
        settings = utils.get_settings()
        if not settings.get("enable_internal_charge"):
            return

        self._validate_amounts()
        self._populate_line_routes()
        self._sync_status()

    def before_submit(self):
        settings = utils.get_settings()
        if not settings.get("enable_internal_charge"):
            return

        self._populate_line_routes()
        self._sync_status()

    def before_workflow_action(self, action, **kwargs):
        settings = utils.get_settings()
        if not settings.get("enable_internal_charge"):
            return

        if action != "Approve":
            return

        approvable_lines = []
        session_user = getattr(getattr(frappe, "session", None), "user", None)
        session_roles = set(frappe.get_roles())

        for line in getattr(self, "internal_charge_lines", []) or []:
            if getattr(line, "line_status", None) not in {"Pending L1", "Pending L2", "Pending L3"}:
                continue

            snapshot = _parse_route_snapshot(getattr(line, "route_snapshot", None))
            current_level = getattr(line, "current_approval_level", 0) or 0
            level_key = f"level_{current_level}"
            level_meta = snapshot.get(level_key, {}) if snapshot else {}
            expected_role = level_meta.get("role") or getattr(line, f"{level_key}_role", None)
            expected_user = level_meta.get("user") or getattr(line, f"{level_key}_approver", None)

            role_allowed = not expected_role or expected_role in session_roles
            user_allowed = not expected_user or expected_user == session_user
            if role_allowed and user_allowed:
                approvable_lines.append(line)

        if not approvable_lines:
            frappe.throw(_("You are not authorized to approve any pending lines."))

        for line in approvable_lines:
            _advance_line_status(line, session_user=session_user)

        self._sync_status()
        if self.status == "Approved":
            self.approved_by = session_user
            self.approved_on = frappe.utils.now_datetime()

    def _validate_amounts(self):
        lines = getattr(self, "internal_charge_lines", []) or []
        if not lines:
            frappe.throw(_("Please add at least one Internal Charge Line."))

        total = sum(float(getattr(line, "amount", 0) or 0) for line in lines)
        if getattr(self, "total_amount", 0) and abs(total - float(self.total_amount)) > 0.0001:
            frappe.throw(_("Sum of line amounts ({0}) must equal Total Amount ({1}).").format(total, self.total_amount))

        for line in lines:
            if getattr(line, "amount", 0) is None or float(line.amount) <= 0:
                frappe.throw(_("Line amount must be greater than zero."))

    def _populate_line_routes(self):
        if not getattr(self, "expense_request", None):
            return

        try:
            expense_request = frappe.get_doc("Expense Request", self.expense_request)
        except Exception:
            expense_request = None

        items = expense_request.get("items") if expense_request else []
        _, expense_accounts = accounting.summarize_request_items(items, skip_invalid_items=True)
        if not expense_accounts:
            return

        for line in getattr(self, "internal_charge_lines", []) or []:
            try:
                setting_meta = get_active_setting_meta(line.target_cost_center)
                route = get_approval_route(
                    line.target_cost_center,
                    expense_accounts,
                    float(getattr(line, "amount", 0) or 0),
                    setting_meta=setting_meta,
                )
            except (frappe.DoesNotExistError, frappe.ValidationError) as exc:
                log_route_resolution_error(
                    exc,
                    cost_center=line.target_cost_center,
                    accounts=expense_accounts,
                    amount=getattr(line, "amount", None),
                )
                frappe.throw(
                    _("Approval route could not be determined for target cost center {0}.").format(line.target_cost_center)
                )

            line.route_snapshot = service.serialize_route(route)
            line.level_1_role = route.get("level_1", {}).get("role")
            line.level_1_approver = route.get("level_1", {}).get("user")
            line.level_2_role = route.get("level_2", {}).get("role")
            line.level_2_approver = route.get("level_2", {}).get("user")
            line.level_3_role = route.get("level_3", {}).get("role")
            line.level_3_approver = route.get("level_3", {}).get("user")

            if route.get("level_1", {}).get("role") or route.get("level_1", {}).get("user"):
                line.line_status = "Pending L1"
                line.current_approval_level = 1
            elif route.get("level_2", {}).get("role") or route.get("level_2", {}).get("user"):
                line.line_status = "Pending L2"
                line.current_approval_level = 2
            elif route.get("level_3", {}).get("role") or route.get("level_3", {}).get("user"):
                line.line_status = "Pending L3"
                line.current_approval_level = 3
            else:
                line.line_status = "Approved"
                line.current_approval_level = 0

    def _sync_status(self):
        lines = getattr(self, "internal_charge_lines", []) or []
        if not lines:
            return

        all_statuses = {getattr(line, "line_status", None) for line in lines}
        if all_statuses == {"Approved"}:
            self.status = "Approved"
        elif "Rejected" in all_statuses:
            self.status = "Rejected"
        elif any(status in {"Pending L1", "Pending L2", "Pending L3"} for status in all_statuses):
            self.status = "Pending Approval"
        else:
            self.status = "Partially Approved"


def _advance_line_status(line, *, session_user=None):
    level = getattr(line, "current_approval_level", 0) or 0
    if level == 1:
        line.line_status = "Pending L2" if (getattr(line, "level_2_role", None) or getattr(line, "level_2_approver", None)) else "Approved"
        line.current_approval_level = 2 if line.line_status == "Pending L2" else 0
    elif level == 2:
        line.line_status = "Pending L3" if (getattr(line, "level_3_role", None) or getattr(line, "level_3_approver", None)) else "Approved"
        line.current_approval_level = 3 if line.line_status == "Pending L3" else 0
    elif level == 3:
        line.line_status = "Approved"
        line.current_approval_level = 0
    else:
        line.line_status = "Approved"
        line.current_approval_level = 0

    if line.line_status == "Approved":
        line.approved_by = session_user
        try:
            line.approved_on = frappe.utils.now_datetime()
        except Exception:
            line.approved_on = None
