# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

from imogi_finance import accounting
from imogi_finance.approval import get_active_setting_meta, get_approval_route, log_route_resolution_error
from imogi_finance.budget_control import service, utils
from imogi_finance.events.utils import get_approved_expense_request

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

        expense_request = get_approved_expense_request(
            self.expense_request,
            _("Internal Charge Request"),
            allowed_statuses={"Approved", "Linked"},
        )
        _, expense_accounts = accounting.summarize_request_items(expense_request.get("items"), skip_invalid_items=True)

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
