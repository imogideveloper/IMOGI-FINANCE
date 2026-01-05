# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

from imogi_finance.budget_control import service, utils

try:
    from frappe.model.document import Document
except Exception:  # pragma: no cover - fallback for test stubs
    class Document:  # type: ignore
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)


class BudgetReclassRequest(Document):
    """Request to reclassify budget between cost centers/accounts."""

    def validate(self):
        if getattr(self, "amount", 0) is None or float(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than zero."))

        if not getattr(self, "fiscal_year", None):
            frappe.throw(_("Fiscal Year must be specified."))

    def on_submit(self):
        settings = utils.get_settings()
        if not settings.get("enable_budget_reclass"):
            return

        from_dims = service.resolve_dims(
            company=getattr(self, "company", None),
            fiscal_year=getattr(self, "fiscal_year", None),
            cost_center=getattr(self, "from_cost_center", None),
            account=getattr(self, "from_account", None),
            project=getattr(self, "project", None),
            branch=getattr(self, "branch", None),
        )
        to_dims = service.resolve_dims(
            company=getattr(self, "company", None),
            fiscal_year=getattr(self, "fiscal_year", None),
            cost_center=getattr(self, "to_cost_center", None),
            account=getattr(self, "to_account", None),
            project=getattr(self, "project", None),
            branch=getattr(self, "branch", None),
        )

        override_role = settings.get("allow_reclass_override_role")
        if override_role and override_role in frappe.get_roles():
            override_allowed = True
        else:
            override_allowed = False

        if not override_allowed:
            result = service.check_budget_available(from_dims, float(getattr(self, "amount", 0) or 0))
            if not result.ok:
                frappe.throw(result.message)

        service.record_reclass(
            from_dims=from_dims,
            to_dims=to_dims,
            amount=float(getattr(self, "amount", 0) or 0),
            ref_doctype="Budget Reclass Request",
            ref_name=getattr(self, "name", None),
        )

        if not getattr(self, "status", None):
            self.status = "Approved"
