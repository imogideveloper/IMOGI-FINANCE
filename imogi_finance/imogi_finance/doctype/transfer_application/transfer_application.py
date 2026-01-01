from __future__ import annotations

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, money_in_words, now_datetime, today

from imogi_finance.transfer_application.payment_entries import (
    create_payment_entry_for_transfer_application,
)
from imogi_finance.transfer_application.settings import get_reference_doctype_options


class TransferApplication(Document):
    def validate(self):
        self.apply_defaults()
        self.validate_reference_fields()
        self.update_amount_in_words()
        self.sync_payment_details()

    def apply_defaults(self):
        if not self.status:
            self.status = "Draft"
        if not self.posting_date:
            self.posting_date = today()
        if not self.requested_transfer_date:
            self.requested_transfer_date = self.posting_date

        if self.payee_type in {"Supplier", "Employee"} and not self.party_type:
            self.party_type = self.payee_type

        if self.party_type in {None, "", "None"}:
            self.party = None

        if not self.currency:
            company_currency = None
            if self.company:
                company_currency = frappe.db.get_value("Company", self.company, "default_currency")
            self.currency = company_currency or frappe.db.get_default("currency")

        if self.amount and not self.expected_amount:
            self.expected_amount = self.amount

        if not self.workflow_state:
            self.workflow_state = self.status or "Draft"

    def validate_reference_fields(self):
        if self.reference_name and not self.reference_doctype:
            frappe.throw(_("Please choose a Reference Doctype when Reference Name is set."))
        if self.reference_doctype and not self.reference_name:
            # Allow empty name for Other/manual
            if self.reference_doctype != "Other":
                frappe.throw(_("Please select a Reference Name for the chosen Reference Doctype."))

        allowed = set(get_reference_doctype_options())
        if self.reference_doctype and self.reference_doctype not in allowed:
            frappe.throw(_("Reference Doctype {0} is not available in this site.").format(self.reference_doctype))

    def update_amount_in_words(self):
        if flt(self.amount) and self.currency:
            self.amount_in_words = money_in_words(self.amount, self.currency)
        else:
            self.amount_in_words = None

    def sync_payment_details(self):
        if not self.payment_entry:
            self.paid_date = None
            self.paid_amount = None
            if self.workflow_state and self.status != "Paid":
                self.status = self.workflow_state
            return

        payment_info = frappe.db.get_value(
            "Payment Entry",
            self.payment_entry,
            ["docstatus", "posting_date", "paid_amount"],
            as_dict=True,
        )
        if not payment_info:
            return

        if payment_info.docstatus == 1:
            self.paid_amount = payment_info.paid_amount
            self.paid_date = payment_info.posting_date
            self.status = "Paid"
            self.workflow_state = "Paid"
        elif payment_info.docstatus == 2:
            self.payment_entry = None
            self.paid_amount = None
            self.paid_date = None
            if self.workflow_state == "Paid":
                self.workflow_state = "Awaiting Bank Confirmation"
            self.status = self.workflow_state or self.status

    def on_cancel(self):
        self.status = "Cancelled"
        self.workflow_state = "Cancelled"

    @frappe.whitelist()
    def mark_as_printed(self):
        frappe.only_for(("Accounts User", "Accounts Manager", "System Manager"))
        now = now_datetime()
        self.db_set({"printed_by": frappe.session.user, "printed_at": now})
        return {"printed_at": now}

    @frappe.whitelist()
    def create_payment_entry(self, submit: int | str = 0):
        if self.docstatus == 2:
            frappe.throw(_("Cannot create a Payment Entry from a cancelled Transfer Application."))

        submit_flag = bool(cint(submit))
        payment_entry = create_payment_entry_for_transfer_application(
            self, submit=submit_flag
        )
        self.reload()
        return {"payment_entry": payment_entry.name}


@frappe.whitelist()
def fetch_reference_doctype_options():
    return get_reference_doctype_options()
