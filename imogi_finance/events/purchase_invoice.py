import frappe
from frappe import _

from imogi_finance.accounting import PURCHASE_INVOICE_ALLOWED_STATUSES, PURCHASE_INVOICE_REQUEST_TYPES
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
)
from imogi_finance.tax_invoice_ocr import get_settings


def validate_before_submit(doc, method=None):
    settings = get_settings()
    require_verified = settings.get("require_verification_before_submit_pi")
    if require_verified and getattr(doc, "ti_verification_status", "") != "Verified":
        frappe.throw(
            _("Tax Invoice must be verified before submitting this Purchase Invoice."),
            title=_("Verification Required"),
        )


def on_submit(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    request = get_approved_expense_request(
        request, _("Purchase Invoice"), allowed_statuses=PURCHASE_INVOICE_ALLOWED_STATUSES
    )

    if request.linked_purchase_invoice:
        frappe.throw(
            _("Expense Request is already linked to Purchase Invoice {0}.").format(
                request.linked_purchase_invoice
            )
        )

    if request.request_type not in PURCHASE_INVOICE_REQUEST_TYPES:
        frappe.throw(
            _("Purchase Invoice can only be linked for request type(s): {0}").format(
                ", ".join(sorted(PURCHASE_INVOICE_REQUEST_TYPES))
            )
        )

    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"linked_purchase_invoice": doc.name, "pending_purchase_invoice": None, "status": "Linked"},
    )
    request.pending_purchase_invoice = None


def on_cancel(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    updates = get_cancel_updates(request, "linked_purchase_invoice")
    updates["pending_purchase_invoice"] = None

    frappe.db.set_value("Expense Request", request, updates)
