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

        cleaned: list[dict] | None = None
        original_count: int | None = None
        if isinstance(data, list):
            original_count = len(data)
            cleaned = [doc for doc in data if isinstance(doc, dict) and doc.get("name")]
        elif isinstance(data, dict):
            original_count = 1
            cleaned = [data] if data.get("name") else []

        if cleaned is None or cleaned == data:
            continue

        fixture_path.write_text(json.dumps(cleaned, indent=2, ensure_ascii=False) + "\n")
        frappe.logger().warning(
            "Removed %s malformed fixture rows from %s",
            original_count - len(cleaned),
            fixture_path.name,
        )
