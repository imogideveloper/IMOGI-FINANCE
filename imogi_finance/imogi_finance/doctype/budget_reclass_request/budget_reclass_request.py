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


class BudgetReclassRequest(Document):
    """Request to reclassify budget between cost centers/accounts with multi-level approval."""

    def validate(self):
        if getattr(self, "amount", 0) is None or float(self.amount) <= 0:
            frappe.throw(_("Amount must be greater than zero."))

        if not getattr(self, "fiscal_year", None):
            frappe.throw(_("Fiscal Year must be specified."))

    def before_submit(self):
        """Resolve approval route before submission."""
        # Use from_cost_center for approval routing
        cost_center = getattr(self, "from_cost_center", None)
        if not cost_center:
            frappe.throw(_("From Cost Center is required"))
        
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

    def before_workflow_action(self, action, **kwargs):
        """Validate approver before workflow action."""
        if action == "Submit":
            return
        
        budget_approval.validate_approver_permission(self, action)

    def on_workflow_action(self, action, **kwargs):
        """Handle workflow state transitions."""
        if action == "Submit":
            self.workflow_state = "Pending Approval"
            self.status = "Pending Approval"
            return
        
        if action == "Approve":
            budget_approval.advance_approval_level(self)
            
            # Execute budget reclass only when fully approved
            if self.status == "Approved":
                self._execute_budget_reclass()
            
            # Don't modify workflow_state here, let advance_approval_level handle it
            return
        
        if action == "Reject":
            self.status = "Rejected"
            self.workflow_state = "Rejected"
            self.current_approval_level = 0
            return

    def _execute_budget_reclass(self):
        """Execute budget reclass after full approval."""
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
