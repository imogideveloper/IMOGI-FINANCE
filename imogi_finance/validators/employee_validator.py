from __future__ import annotations

import frappe
from frappe import _


class EmployeeValidator:
    """Employee-related validations."""

    @staticmethod
    def require_employee(doc, enabled: bool = False):
        if enabled and not getattr(doc, "employee", None):
            frappe.throw(_("Employee is required for this request."))
