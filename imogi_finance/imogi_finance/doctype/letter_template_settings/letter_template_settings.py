from __future__ import annotations

import frappe
from frappe.model.document import Document

DEFAULT_SETTINGS = {
    "enable_payment_letter": 1,
    "default_template": None,
    "inherit_bank_from_branch": 1,
}


class LetterTemplateSettings(Document):
    """Configure global defaults for payment letters.

    Required fields (configure via Desk/Doctype UI):
        - enable_payment_letter (Check, default 1)
        - default_template (Link to "Letter Template", nullable)
        - inherit_bank_from_branch (Check, default 1)
    """

    pass


def get_settings():
    try:
        return frappe.get_cached_doc("Letter Template Settings")
    except Exception:
        try:
            return frappe.get_single("Letter Template Settings")
        except Exception:
            return frappe._dict(DEFAULT_SETTINGS)
