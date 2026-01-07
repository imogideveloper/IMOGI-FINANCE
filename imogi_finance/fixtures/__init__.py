"""Fixtures package."""

from __future__ import annotations

import json
from pathlib import Path

import frappe

FIXTURES_DIR = Path(__file__).resolve().parent


def sanitize_fixture_files() -> None:
    """Remove malformed fixture records missing a name field.

    Frappe expects each fixture record to include a primary key stored in
    the ``name`` field. If a fixture record is missing that field, migrations
    will error during import. We defensively filter out invalid records and
    log what was updated.
    """

    for fixture_path in FIXTURES_DIR.glob("*.json"):
        try:
            data = json.loads(fixture_path.read_text())
        except json.JSONDecodeError:
            continue

        if not isinstance(data, list):
            continue

        cleaned = [doc for doc in data if isinstance(doc, dict) and "name" in doc]
        if cleaned == data:
            continue

        fixture_path.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n")
        frappe.logger().warning(
            "Removed %s malformed fixture rows from %s",
            len(data) - len(cleaned),
            fixture_path.name,
        )
