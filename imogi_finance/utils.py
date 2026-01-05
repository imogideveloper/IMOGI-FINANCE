# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""Compatibility module for app hooks.

The app's Python package lives in ``imogi_finance/imogi_finance``. Frappe hook
paths expect ``imogi_finance.utils`` to resolve, so re-export the helpers here.
"""

from __future__ import annotations

from .imogi_finance.utils import ensure_coretax_export_doctypes

__all__ = ["ensure_coretax_export_doctypes"]
