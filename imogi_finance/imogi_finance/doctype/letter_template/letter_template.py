from __future__ import annotations

from typing import List

import frappe
from frappe import _
from frappe.model.document import Document


class LetterTemplate(Document):
    """HTML/Jinja templates for payment letters.

    Expected fields configured on the DocType:
        - template_name (Data, required)
        - letter_type (Select, default "Payment Letter")
        - is_default (Check, default 0)
        - branch (Link to Branch, optional for global templates)
        - is_active (Check, default 1)
        - header_image (Attach Image)
        - footer_image (Attach Image)
        - body_html (Code or Text Editor with HTML/Jinja content)
    """

    def validate(self):
        if getattr(self, "is_default", 0):
            self._ensure_single_default()

    def _ensure_single_default(self) -> None:
        letter_type = getattr(self, "letter_type", "Payment Letter")
        filters: List[list] = [["letter_type", "=", letter_type]]
        if getattr(self, "branch", None):
            filters.append(["branch", "=", self.branch])
        else:
            filters.append(["branch", "is", "not set"])

        if getattr(self, "name", None):
            filters.append(["name", "!=", self.name])

        existing_defaults = frappe.get_all(
            "Letter Template",
            filters=filters + [["is_default", "=", 1]],
            pluck="name",
        )

        for template_name in existing_defaults:
            frappe.db.set_value("Letter Template", template_name, "is_default", 0)
            frappe.msgprint(
                _("Unset as default for {0} ({1})").format(template_name, letter_type),
                alert=True,
            )
