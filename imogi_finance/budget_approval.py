"""Budget approval helper functions - shared approval logic for budget requests."""

from __future__ import annotations

import frappe
from frappe import _


def get_budget_approval_route(cost_center: str) -> dict:
    """
    Get approval route for budget request based on cost center.
    
    Args:
        cost_center: Cost Center name
        
    Returns:
        dict with level_1_user, level_2_user, level_3_user, approval_setting
    """
    if not cost_center:
        frappe.throw(_("Cost Center is required for approval route resolution"))

    # Try to find specific setting for this cost center
    setting = frappe.db.get_value(
        "Budget Approval Setting",
        {"cost_center": cost_center, "is_active": 1},
        ["name", "cost_center"],
        as_dict=True
    )
    
    # Fallback to system default (no cost center)
    if not setting:
        setting = frappe.db.get_value(
            "Budget Approval Setting",
            {"cost_center": ["in", ["", None]], "is_active": 1},
            ["name", "cost_center"],
            as_dict=True
        )
    
    if not setting:
        frappe.throw(
            _("No active Budget Approval Setting found for Cost Center: {0} or System Default").format(cost_center)
        )

    # Get approval lines from setting
    lines = frappe.get_all(
        "Budget Approval Line",
        filters={"parent": setting.name},
        fields=["level_1_user", "level_2_user", "level_3_user"],
        limit=1
    )
    
    if not lines:
        frappe.throw(_("Budget Approval Setting {0} has no approval lines").format(setting.name))
    
    line = lines[0]
    
    return {
        "level_1_user": line.level_1_user,
        "level_2_user": line.level_2_user or None,
        "level_3_user": line.level_3_user or None,
        "approval_setting": setting.name
    }


def record_approval_timestamp(doc, level: int):
    """Record approval timestamp for specific level."""
    user = frappe.session.user
    now = frappe.utils.now()
    
    approved_by_field = f"level_{level}_approved_by"
    approved_at_field = f"level_{level}_approved_at"
    
    setattr(doc, approved_by_field, user)
    setattr(doc, approved_at_field, now)
    
    # Save to database
    if hasattr(doc, "db_set"):
        doc.db_set(approved_by_field, user)
        doc.db_set(approved_at_field, now)


def advance_approval_level(doc):
    """Advance to next approval level or mark as approved.
    
    Returns:
        str: 'Pending Approval' if more levels exist, 'Approved' if final approval
    """
    current_level = getattr(doc, "current_approval_level", 0) or 1
    
    # Record approval timestamp for current level
    record_approval_timestamp(doc, current_level)
    
    # Check if there's a next level
    next_level = current_level + 1
    next_user = getattr(doc, f"level_{next_level}_user", None)
    
    if next_user:
        # Move to next level
        doc.current_approval_level = next_level
        
        # Save changes to database
        if hasattr(doc, "db_set"):
            doc.db_set("current_approval_level", next_level)
        
        # Return state to stay at Pending Approval for next level
        return "Pending Approval"
    else:
        # No more levels, mark as approved
        doc.current_approval_level = 0
        
        # Save changes to database
        if hasattr(doc, "db_set"):
            doc.db_set("current_approval_level", 0)
        
        # Return Approved to move workflow to final state
        return "Approved"


def validate_approver_permission(doc, action: str):
    """Validate if current user can approve at current level."""
    if action not in ("Approve", "Reject"):
        return
    
    current_level = getattr(doc, "current_approval_level", 0) or 1
    required_approver = getattr(doc, f"level_{current_level}_user", None)
    
    current_user = frappe.session.user
    
    # System Manager can always approve
    if "System Manager" in frappe.get_roles():
        return
    
    # Check if current user is the required approver
    if required_approver and current_user != required_approver:
        frappe.throw(
            _("Only {0} can {1} at Level {2}").format(
                required_approver, action, current_level
            )
        )
