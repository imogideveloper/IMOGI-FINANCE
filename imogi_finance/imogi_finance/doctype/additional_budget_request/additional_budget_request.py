# Copyright (c) 2024, Imogi and contributors
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


class AdditionalBudgetRequest(Document):
    """Request to top-up budget allocation."""

    def validate(self):
        if getattr(self, "amount", 0) is None or float(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than zero."))

    def on_submit(self):
        settings = utils.get_settings()
        if not settings.get("enable_additional_budget"):
            return

        dims = service.resolve_dims(
            company=getattr(self, "company", None),
            fiscal_year=getattr(self, "fiscal_year", None),
            cost_center=getattr(self, "cost_center", None),
            account=getattr(self, "account", None),
            project=getattr(self, "project", None),
            branch=getattr(self, "branch", None),
        )
        service.record_supplement(
            dims=dims,
            amount=float(getattr(self, "amount", 0) or 0),
            ref_doctype="Additional Budget Request",
            ref_name=getattr(self, "name", None),
        )

        if not getattr(self, "status", None):
            self.status = "Approved"
