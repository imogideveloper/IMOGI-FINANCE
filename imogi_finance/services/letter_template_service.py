from __future__ import annotations

from typing import Any, Dict, Optional

import frappe
from frappe import _

from imogi_finance.branching import resolve_branch
from imogi_finance.imogi_finance.doctype.letter_template_settings.letter_template_settings import (
    get_settings,
)


def _get_effective_branch(doc: Any) -> Optional[str]:
    company = getattr(doc, "company", None)
    cost_center = getattr(doc, "cost_center", None)
    if not cost_center:
        for item in getattr(doc, "items", []) or []:
            item_cost_center = getattr(item, "cost_center", None)
            if item_cost_center:
                cost_center = item_cost_center
                break

    explicit_branch = getattr(doc, "branch", None)
    return resolve_branch(company=company, cost_center=cost_center, explicit_branch=explicit_branch)


def _get_utils_attr(name: str, default):
    utils = getattr(frappe, "utils", None)
    return getattr(utils, name, default) if utils else default


fmt_money = _get_utils_attr(
    "fmt_money", lambda amount, currency=None: f"{amount} {currency}".strip()
)
formatdate = _get_utils_attr("formatdate", lambda value: value)
get_url = _get_utils_attr("get_url", lambda path: path)
money_in_words = _get_utils_attr(
    "money_in_words", lambda amount, currency=None: f"{amount} {currency}".strip()
)
today = _get_utils_attr("today", lambda: "")


def _get_effective_company_bank(branch: Optional[str], doc: Any | None = None) -> Dict[str, Any]:
    company = getattr(doc, "company", None)
    db = getattr(frappe, "db", None)
    db_exists = getattr(db, "exists", None)
    db_get_value = getattr(db, "get_value", None)
    db_has_column = getattr(db, "has_column", None)
    if (
        not company
        and branch
        and callable(db_exists)
        and db_exists("DocType", "Branch")
        and callable(db_has_column)
        and db_has_column("Branch", "company")
        and callable(db_get_value)
    ):
        company = db_get_value("Branch", branch, "company")

    company_name = ""
    company_address = ""
    if company and callable(db_exists) and db_exists("DocType", "Company"):
        getter = getattr(frappe, "get_cached_value", None)
        if callable(getter):
            company_name = getter("Company", company, "company_name") or company
        # Address handling can be extended later when a definitive source is available.

    return {
        "company_name": company_name or getattr(frappe.local, "company", "") or "",
        "company_address": company_address,
        "bank_name": "",
        "bank_branch": "",
        "account_name": "",
        "account_number": "",
        "header_image_url": "",
        "footer_image_url": "",
    }


def _get_template(branch: Optional[str], letter_type: str = "Payment Letter"):
    if branch:
        branch_templates = frappe.get_all(
            "Letter Template",
            filters={
                "branch": branch,
                "letter_type": letter_type,
                "is_active": 1,
            },
            order_by="is_default desc, creation desc",
            limit=1,
            pluck="name",
        )
        if branch_templates:
            return frappe.get_doc("Letter Template", branch_templates[0])

    settings = get_settings()
    default_template = getattr(settings, "default_template", None)
    if default_template:
        template = None
        try:
            template = frappe.get_doc("Letter Template", default_template)
        except Exception:
            template = None

        if (
            template
            and getattr(template, "is_active", 0)
            and getattr(template, "letter_type", None) == letter_type
        ):
            return template

    global_templates = frappe.get_all(
        "Letter Template",
        filters={
            "branch": ["is", "not set"],
            "letter_type": letter_type,
            "is_active": 1,
        },
        order_by="is_default desc, creation desc",
        limit=1,
        pluck="name",
    )
    if global_templates:
        return frappe.get_doc("Letter Template", global_templates[0])

    frappe.throw(_("No active letter template configured."))


def _resolve_amount(doc: Any) -> tuple[float, Optional[str]]:
    amount = getattr(doc, "amount", None)
    if amount is None:
        amount = (
            getattr(doc, "total_amount", None)
            or getattr(doc, "grand_total", None)
            or getattr(doc, "rounded_total", None)
            or getattr(doc, "net_total", None)
            or 0
        )
    currency = getattr(doc, "currency", None) or getattr(doc, "company_currency", None)
    return float(amount or 0), currency


def _resolve_customer_name(doc: Any) -> str:
    return (
        getattr(doc, "party_name", None)
        or getattr(doc, "customer_name", None)
        or getattr(doc, "customer", None)
        or getattr(doc, "supplier_name", None)
        or getattr(doc, "supplier", None)
        or getattr(doc, "party", None)
        or getattr(doc, "pay_to", None)
        or ""
    )


def _resolve_invoice_number(doc: Any) -> Optional[str]:
    return (
        getattr(doc, "invoice_number", None)
        or getattr(doc, "reference_name", None)
        or getattr(doc, "reference_no", None)
        or getattr(doc, "name", None)
        or getattr(doc, "sales_invoice", None)
        or getattr(doc, "sales_order", None)
    )


def build_payment_letter_context(doc: Any, letter_type: str = "Payment Letter") -> Dict[str, Any]:
    branch = _get_effective_branch(doc)
    company_bank = _get_effective_company_bank(branch, doc)

    posting_date = (
        getattr(doc, "posting_date", None)
        or getattr(doc, "transaction_date", None)
        or getattr(doc, "invoice_date", None)
    )
    letter_date = formatdate(posting_date) if posting_date else formatdate(today())

    amount, currency = _resolve_amount(doc)
    formatted_amount = fmt_money(amount, currency=currency) if amount is not None else ""
    amount_words = money_in_words(amount, currency) if amount else ""

    invoice_date = getattr(doc, "invoice_date", None) or posting_date
    due_date = getattr(doc, "due_date", None) or getattr(doc, "schedule_date", None)

    current_user = getattr(getattr(frappe, "session", None), "user", None)
    proof_email = getattr(doc, "proof_email", None) or getattr(doc, "contact_email", None)
    if not proof_email and current_user:
        proof_email = frappe.db.get_value("User", current_user, "email")

    return {
        **company_bank,
        "branch": branch,
        "company": getattr(doc, "company", None),
        "letter_place": getattr(doc, "company", None) or company_bank.get("company_name") or "",
        "letter_date": letter_date,
        "letter_number": getattr(doc, "name", ""),
        "letter_type": getattr(doc, "letter_type", None) or letter_type,
        "subject": _("Permintaan Pembayaran via Transfer"),
        "customer_name": _resolve_customer_name(doc),
        "customer_address": getattr(doc, "customer_address", None)
        or getattr(doc, "address", None)
        or getattr(doc, "address_display", None)
        or "",
        "customer_city": getattr(doc, "customer_city", None) or "",
        "transaction_type": getattr(doc, "transaction_type", None) or "pembelian barang/jasa",
        "invoice_number": _resolve_invoice_number(doc),
        "invoice_date": formatdate(invoice_date) if invoice_date else "",
        "amount": formatted_amount,
        "amount_in_words": amount_words,
        "due_date": formatdate(due_date) if due_date else "",
        "proof_email": proof_email or "",
        "proof_whatsapp": getattr(doc, "proof_whatsapp", None) or getattr(doc, "contact_mobile", None) or "",
        "signer_name": getattr(doc, "signer_name", None) or getattr(doc, "requester", None) or "",
        "signer_title": getattr(doc, "signer_title", None) or _("Authorized Signatory"),
    }


def render_payment_letter_html(doc: Any, letter_type: str = "Payment Letter") -> str:
    settings = get_settings()
    if not getattr(settings, "enable_payment_letter", 1):
        frappe.throw(_("Payment Letter is disabled in settings."))

    branch = _get_effective_branch(doc)
    template = _get_template(branch, letter_type=letter_type)
    ctx = build_payment_letter_context(doc, letter_type=letter_type)

    if getattr(template, "header_image", None):
        ctx["header_image_url"] = get_url(template.header_image)
    if getattr(template, "footer_image", None):
        ctx["footer_image_url"] = get_url(template.footer_image)

    return frappe.render_template(template.body_html or "", ctx)
