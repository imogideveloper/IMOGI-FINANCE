# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ExpenseApprovalLine(Document):
    """Child table to capture approval levels for expense accounts."""

    def validate(self):
        self.validate_level_amounts()

    def validate_level_amounts(self):
        """Validate level-specific amount ranges."""
        for level in (1, 2, 3):
            min_amt = getattr(self, f"level_{level}_min_amount", None)
            max_amt = getattr(self, f"level_{level}_max_amount", None)
            user = getattr(self, f"level_{level}_user", None)

            # Skip if level not configured
            if not user:
                continue

            # If level has approver, amount range is required
            if min_amt is None or max_amt is None:
                frappe.throw(
                    _("Level {0} requires both Min Amount and Max Amount when approver is configured.").format(level)
                )

            if min_amt > max_amt:
                frappe.throw(
                    _("Level {0} Min Amount cannot exceed Max Amount.").format(level)
                )