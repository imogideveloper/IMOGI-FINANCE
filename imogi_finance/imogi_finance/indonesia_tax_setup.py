from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import frappe


class AccountResolver:
    """Resolve or create tax accounts per company with prioritized sources."""

    def __init__(self, company: str, abbr: str | None, payroll_accounts: set[str] | None = None):
        self.company = company
        self.abbr = abbr
        self.payroll_accounts = payroll_accounts or set()
        self.log: list[dict[str, str]] = []

    def resolve(
        self,
        label: str,
        preferred_names: Iterable[str],
        *,
        keywords: Iterable[str] = (),
        root_type: str | None = None,
        account_type: str | None = None,
    ) -> str | None:
        """Return the best-fit account for the label, creating when needed.

        Priority order:
        1) Payroll Indonesia default account matches (with suffix)
        2) Explicit preferred names (Odoo-style) with/without suffix
        3) Keyword search on account name
        4) Creation using the first preferred name
        """

        preferred_names = list(preferred_names)

        for name in preferred_names:
            account = self._find_existing(name, root_type=root_type, payroll_only=True)
            if account:
                return self._record(label, account, "payroll")

        for name in preferred_names:
            account = self._find_existing(name, root_type=root_type)
            if account:
                source = "odoo" if name in preferred_names else "existing"
                return self._record(label, account, source)

        for name in preferred_names:
            account = self._find_existing(name)
            if account:
                return self._record(label, account, "existing")

        for keyword in keywords:
            account = self._find_by_keyword(keyword, root_type=root_type)
            if account:
                return self._record(label, account, "keyword")

        if preferred_names:
            account = self._create_account(preferred_names[0], root_type=root_type, account_type=account_type)
            if account:
                return self._record(label, account, "created")
        return None

    def _record(self, label: str, account: str, source: str) -> str:
        self.log.append({"label": label, "account": account, "source": source, "company": self.company})
        return account

    def _find_existing(self, base_name: str, *, root_type: str | None = None, payroll_only: bool = False) -> str | None:
        candidates = {base_name}
        if self.abbr:
            candidates.add(f"{base_name} - {self.abbr}")

        filters = {"company": self.company, "is_group": 0, "name": ["in", list(candidates)]}
        if root_type:
            filters["root_type"] = root_type

        match = frappe.get_all("Account", filters=filters, fields=["name", "account_name", "root_type"], limit=1)
        if match:
            if payroll_only and base_name not in self.payroll_accounts and match[0].get("account_name") not in self.payroll_accounts:
                return None
            return match[0]["name"]

        filters = {"company": self.company, "is_group": 0, "account_name": ["in", list(candidates)]}
        if root_type:
            filters["root_type"] = root_type

        match = frappe.get_all("Account", filters=filters, fields=["name", "account_name", "root_type"], limit=1)
        if match and (not payroll_only or match[0].get("account_name") in self.payroll_accounts):
            return match[0]["name"]
        return None

    def _find_by_keyword(self, keyword: str, *, root_type: str | None = None) -> str | None:
        conditions: dict[str, object] = {"company": self.company, "is_group": 0, "account_name": ["like", f"%{keyword}%"]}
        if root_type:
            conditions["root_type"] = root_type

        match = frappe.get_all(
            "Account",
            filters=conditions,
            fields=["name", "account_name", "root_type"],
            order_by="modified desc",
            limit=1,
        )
        return match[0]["name"] if match else None

    def _get_parent(self, root_type: str | None) -> str | None:
        if not root_type:
            return None

        parent_name = "Current Assets" if root_type == "Asset" else "Current Liabilities"
        candidates = {parent_name}
        if self.abbr:
            candidates.add(f"{parent_name} - {self.abbr}")

        match = frappe.get_all(
            "Account",
            filters={"company": self.company, "name": ["in", list(candidates)]},
            fields=["name"],
            limit=1,
        )
        if match:
            return match[0]["name"]

        match = frappe.get_all(
            "Account",
            filters={"company": self.company, "account_name": ["in", list(candidates)]},
            fields=["name"],
            limit=1,
        )
        if match:
            return match[0]["name"]
        return None

    def _create_account(self, account_name: str, *, root_type: str | None, account_type: str | None = None) -> str | None:
        if not root_type:
            return None

        parent_account = self._get_parent(root_type)
        doc = frappe.get_doc(
            {
                "doctype": "Account",
                "company": self.company,
                "account_name": account_name,
                "root_type": root_type,
                "report_type": "Balance Sheet",
                "parent_account": parent_account,
            }
        )
        if account_type and doc.meta.has_field("account_type"):
            doc.account_type = account_type

        doc.insert(ignore_permissions=True)
        return doc.name


def load_payroll_account_names() -> set[str]:
    """Return default account names shipped by Payroll Indonesia if available."""
    try:
        path = Path(frappe.get_app_path("payroll_indonesia", "payroll_indonesia", "setup", "default_gl_accounts.json"))
    except Exception:
        return set()

    if not path.exists():
        return set()

    try:
        data = json.loads(path.read_text())
    except Exception:
        return set()

    names: set[str] = set()
    if isinstance(data, list):
        for row in data:
            if isinstance(row, dict):
                name = row.get("account_name") or row.get("account") or row.get("name")
                if name:
                    names.add(str(name))
    return names


def ensure_tax_template(
    *, title: str, company: str, account: str, rate: float, template_type: str, description: str | None = None
) -> str:
    doctype = "Sales Taxes and Charges Template" if template_type.lower() == "sales" else "Purchase Taxes and Charges Template"
    if not frappe.db.table_exists(doctype):
        return ""

    template_name = frappe.db.get_value(doctype, {"title": title, "company": company}, "name")
    if template_name:
        doc = frappe.get_doc(doctype, template_name)
    else:
        doc = frappe.get_doc({"doctype": doctype, "title": title, "company": company})

    row = {
        "charge_type": "On Net Total",
        "account_head": account,
        "rate": rate,
        "description": description or title,
    }

    taxes_field = "taxes"
    existing_rows = getattr(doc, taxes_field, []) or []
    if existing_rows:
        existing_rows[0].update(row)
        setattr(doc, taxes_field, [existing_rows[0]])
    else:
        doc.set(taxes_field, [row])

    doc.save(ignore_permissions=True)
    return doc.name


def _get_child_table_field(meta, child_field: str) -> str | None:
    for field in meta.fields:
        if field.fieldtype == "Table":
            child_meta = frappe.get_meta(field.options)
            if child_meta and child_meta.has_field(child_field):
                return field.fieldname
    return None


def ensure_withholding_tax(company: str, name: str, account: str, rate: float) -> str | None:
    if not frappe.db.table_exists("Withholding Tax"):
        return None

    existing = frappe.db.exists("Withholding Tax", {"name": name, "company": company}) or frappe.db.exists(
        "Withholding Tax", {"company": company, "rate": rate, "account": account}
    )
    doc = frappe.get_doc("Withholding Tax", existing) if existing else frappe.new_doc("Withholding Tax")

    if not existing:
        doc.name = name
    if doc.meta.has_field("company"):
        doc.company = company

    if doc.meta.has_field("rate"):
        doc.rate = rate

    account_fields = ["account", "withholding_account", "payable_account"]
    for field in account_fields:
        if doc.meta.has_field(field):
            doc.set(field, account)
            break

    doc.save(ignore_permissions=True)
    return doc.name


def ensure_withholding_category(company: str, category_name: str, withholding_names: list[str]) -> str | None:
    if not frappe.db.table_exists("Tax Withholding Category"):
        return None

    existing = frappe.db.exists("Tax Withholding Category", {"name": category_name, "company": company})
    doc = frappe.get_doc("Tax Withholding Category", existing) if existing else frappe.new_doc("Tax Withholding Category")
    doc.name = category_name
    if doc.meta.has_field("company"):
        doc.company = company

    child_field = _get_child_table_field(doc.meta, "withholding_tax")
    if child_field:
        existing_links = {row.get("withholding_tax") for row in getattr(doc, child_field, []) or []}
        for wt_name in withholding_names:
            if wt_name and wt_name not in existing_links:
                doc.append(child_field, {"withholding_tax": wt_name})

    doc.save(ignore_permissions=True)
    return doc.name
