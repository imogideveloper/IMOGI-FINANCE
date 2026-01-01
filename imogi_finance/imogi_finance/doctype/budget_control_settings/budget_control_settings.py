# Copyright (c) 2024, Imogi and contributors
# For license information, please see license.txt

from __future__ import annotations

try:
    from frappe.model.document import Document
except Exception:  # pragma: no cover - fallback for test stubs
    class Document:  # type: ignore
        def __init__(self, *args, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)


class BudgetControlSettings(Document):
    """Single settings doctype to toggle budget control features."""

    pass
