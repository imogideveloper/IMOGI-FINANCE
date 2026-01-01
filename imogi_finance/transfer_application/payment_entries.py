from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import today

from erpnext.accounts.doctype.payment_entry.payment_entry import get_party_account
from erpnext.accounts.utils import get_company_default

from imogi_finance.transfer_application.settings import get_transfer_application_settings


def create_payment_entry_for_transfer_application(
    transfer_application: Document,
    *,
    submit: bool = False,
    posting_date: str | None = None,
    paid_amount: float | None = None,
    ignore_permissions: bool = False,
) -> Document:
    if transfer_application.payment_entry:
        existing_status = frappe.db.get_value("Payment Entry", transfer_application.payment_entry, "docstatus")
        if existing_status is not None and existing_status != 2:
            frappe.msgprint(
                _("Payment Entry {0} already exists for this Transfer Application.").format(
                    transfer_application.payment_entry
                )
            )
            return frappe.get_doc("Payment Entry", transfer_application.payment_entry)

    settings = get_transfer_application_settings()

    paid_from = _resolve_paid_from_account(transfer_application.company, settings=settings)
    if not paid_from:
        frappe.throw(
            _("Please configure a default bank/cash account for {0} or in Transfer Application Settings.").format(
                transfer_application.company
            )
        )

    paid_to = _resolve_paid_to_account(transfer_application, settings=settings)
    if not paid_to:
        frappe.throw(
            _("Could not determine the destination account. Please set a party or a default payable account."),
            title=_("Missing Target Account"),
        )

    target_amount = paid_amount or transfer_application.expected_amount or transfer_application.amount
    posting_date = posting_date or transfer_application.requested_transfer_date or transfer_application.posting_date or today()

    payment_entry = frappe.new_doc("Payment Entry")
    payment_entry.payment_type = "Pay"
    payment_entry.company = transfer_application.company
    payment_entry.posting_date = posting_date
    payment_entry.paid_from = paid_from
    payment_entry.paid_to = paid_to
    payment_entry.paid_amount = target_amount
    payment_entry.received_amount = target_amount
    if transfer_application.transfer_method and frappe.db.exists(
        "Mode of Payment", transfer_application.transfer_method
    ):
        payment_entry.mode_of_payment = transfer_application.transfer_method
    payment_entry.reference_no = transfer_application.name
    payment_entry.reference_date = posting_date
    payment_entry.remarks = _(
        "Transfer Application {0} | Purpose: {1}"
    ).format(transfer_application.name, transfer_application.transfer_purpose or "-")

    if transfer_application.party_type and transfer_application.party:
        payment_entry.party_type = transfer_application.party_type
        payment_entry.party = transfer_application.party
        if hasattr(payment_entry, "party_account"):
            payment_entry.party_account = paid_to

    if transfer_application.reference_doctype and transfer_application.reference_name:
        payment_entry.append(
            "references",
            {
                "reference_doctype": transfer_application.reference_doctype,
                "reference_name": transfer_application.reference_name,
                "allocated_amount": target_amount,
            },
        )

    if hasattr(payment_entry, "transfer_application"):
        payment_entry.transfer_application = transfer_application.name

    if hasattr(payment_entry, "set_missing_values"):
        payment_entry.set_missing_values()

    payment_entry.flags.ignore_permissions = ignore_permissions
    payment_entry.insert(ignore_permissions=ignore_permissions)

    if submit:
        payment_entry.submit()

    transfer_application.db_set("payment_entry", payment_entry.name)
    return payment_entry


def _resolve_paid_from_account(company: str, *, settings=None):
    settings = settings or get_transfer_application_settings()
    account = getattr(settings, "default_paid_from_account", None)
    if account:
        return account

    bank_account = _get_default_bank_cash_account(company, account_type="Bank")
    if bank_account and bank_account.get("account"):
        return bank_account.get("account")

    cash_account = _get_default_bank_cash_account(company, account_type="Cash")
    if cash_account and cash_account.get("account"):
        return cash_account.get("account")

    return None


def _get_default_bank_cash_account(company: str, *, account_type: str):
    get_default = None
    try:
        get_default = frappe.get_attr("erpnext.accounts.utils.get_default_bank_cash_account")
    except Exception:
        get_default = None

    if get_default:
        return get_default(company, account_type=account_type)

    field_map = {
        "Bank": "default_bank_account",
        "Cash": "default_cash_account",
    }
    default_field = field_map.get(account_type)
    if not default_field:
        return None

    account = get_company_default(company, default_field)
    if not account:
        return None

    return {"account": account}


def _resolve_paid_to_account(transfer_application: Document, *, settings=None):
    settings = settings or get_transfer_application_settings()
    party_type = getattr(transfer_application, "party_type", None)
    party = getattr(transfer_application, "party", None)

    if party_type and party:
        try:
            return get_party_account(party_type, party, transfer_application.company)
        except Exception:
            pass

    default_setting = getattr(settings, "default_paid_to_account", None)
    if default_setting:
        return default_setting

    company_default = get_company_default(transfer_application.company, "default_payable_account")
    if company_default:
        return company_default

    expense_default = get_company_default(transfer_application.company, "default_expense_account")
    if expense_default:
        return expense_default

    return None
