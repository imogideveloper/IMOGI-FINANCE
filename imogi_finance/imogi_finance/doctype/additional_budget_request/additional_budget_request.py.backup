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
        frappe.logger().debug(f"[ABR] on_workflow_action called: {self.name}, action={action}")
        
        if action == "Submit":
            self.workflow_state = "Pending Approval"
            self.status = "Pending Approval"
            if hasattr(self, "db_set"):
                self.db_set("workflow_state", "Pending Approval")
                self.db_set("status", "Pending Approval")
            return
        
        if action == "Approve":
            frappe.logger().debug(f"[ABR] Before advance: current_level={self.current_approval_level}, level_2_user={self.level_2_user}")
            
            # Validate approver permission
            budget_approval.validate_approver_permission(self, action)
            
            # Advance approval level and get next state
            next_state = budget_approval.advance_approval_level(self)
            frappe.logger().debug(f"[ABR] advance_approval_level returned: {next_state}")
            
            # For intermediate levels: manually set workflow_state and prevent transition
            if next_state == "Pending Approval":
                frappe.logger().debug(f"[ABR] Setting workflow_state to Pending Approval and returning False")
                if hasattr(self, "db_set"):
                    self.db_set("workflow_state", "Pending Approval", update_modified=False)
                    self.reload()
                # Return False to prevent Frappe from executing transition
                return False
            
            # For final level (Approved): let workflow execute the transition
            # Execute budget supplement before workflow completes
            if next_state == "Approved":
                frappe.logger().debug(f"[ABR] Executing budget supplement and allowing Frappe transition")
                self._execute_budget_supplement()
            
            frappe.logger().debug(f"[ABR] Returning None to allow Frappe to handle transition")
            # Don't return False - let workflow execute Pending → Approved transition
            return
        
        if action == "Reject":
            # Validate approver permission
            budget_approval.validate_approver_permission(self, action)
            
            self.status = "Rejected"
            self.workflow_state = "Rejected"
            self.current_approval_level = 0
            
            if hasattr(self, "db_set"):
                self.db_set("status", "Rejected")
                self.db_set("workflow_state", "Rejected")
                self.db_set("current_approval_level", 0)
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
