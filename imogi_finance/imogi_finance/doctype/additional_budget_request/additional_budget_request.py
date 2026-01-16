# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe
from frappe import _

from imogi_finance.budget_control import service, utils
from imogi_finance import budget_approval

try:
    from frappe.model.document import Document
except Exception:  # pragma: no cover - fallback for test stubs
    class Document:  # type: ignore
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)


class AdditionalBudgetRequest(Document):
    """Request to top-up budget allocation with multi-level approval."""

    def validate(self):
        if getattr(self, "amount", 0) is None or float(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than zero."))

    def before_submit(self):
        """Resolve approval route before submission."""
        cost_center = getattr(self, "cost_center", None)
        if not cost_center:
            frappe.throw(_("Cost Center is required"))
        
        # Resolve approval route
        route = budget_approval.get_budget_approval_route(cost_center)
        
        # Store approval route
        self.approval_setting = route["approval_setting"]
        self.level_1_user = route["level_1_user"]
        self.level_2_user = route.get("level_2_user")
        self.level_3_user = route.get("level_3_user")
        
        # Initialize approval level
        self.current_approval_level = 1
        
        # Set initial status
        self.status = "Pending Approval"

    def on_workflow_action(self, action, **kwargs):
        """Handle workflow state transitions."""
        if action == "Submit":
            self.workflow_state = "Pending Approval"
            self.status = "Pending Approval"
            return
        
        if action == "Approve":
            # Validate approver permission
            budget_approval.validate_approver_permission(self, action)
            
            # Advance approval level
            budget_approval.advance_approval_level(self)
            
            # Execute budget supplement only when fully approved
            if self.status == "Approved":
                self._execute_budget_supplement()
            
            # Don't modify workflow_state here, let advance_approval_level handle it
            return
        
        if action == "Reject":
            # Validate approver permission
            budget_approval.validate_approver_permission(self, action)
            
            self.status = "Rejected"
            self.workflow_state = "Rejected"
            self.current_approval_level = 0
            return

    def _execute_budget_supplement(self):
        """Execute budget supplement after full approval."""
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
