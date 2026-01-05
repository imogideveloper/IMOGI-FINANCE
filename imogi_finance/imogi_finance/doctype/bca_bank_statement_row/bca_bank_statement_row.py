# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.model.document import Document


class BCABankStatementRow(Document):
    """Child table storing parsed CSV rows before conversion to Bank Transaction."""

    pass
