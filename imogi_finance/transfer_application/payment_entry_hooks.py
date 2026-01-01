from __future__ import annotations

import frappe
from frappe import _


def validate_transfer_application_link(doc, method=None):
    transfer_application = getattr(doc, "transfer_application", None)
    if not transfer_application:
        return

    ta_info = frappe.db.get_value(
        "Transfer Application", transfer_application, ["docstatus", "payment_entry"], as_dict=True
    )
    if not ta_info:
        frappe.throw(_("Transfer Application {0} not found.").format(transfer_application))

    if ta_info.docstatus == 2:
        frappe.throw(_("Transfer Application {0} is cancelled.").format(transfer_application))

    existing = ta_info.payment_entry
    if existing and existing != doc.name:
        existing_status = frappe.db.get_value("Payment Entry", existing, "docstatus")
        if existing_status is not None and existing_status != 2:
            frappe.throw(
                _("Transfer Application {0} is already linked to Payment Entry {1}.").format(
                    transfer_application, existing
                )
            )


def on_submit(doc, method=None):
    transfer_application = getattr(doc, "transfer_application", None)
    if not transfer_application:
        return

    updates = {
        "payment_entry": doc.name,
        "paid_date": doc.posting_date,
        "paid_amount": doc.paid_amount,
        "workflow_state": "Paid",
        "status": "Paid",
    }
    frappe.db.set_value("Transfer Application", transfer_application, updates)

    try:
        ta_doc = frappe.get_doc("Transfer Application", transfer_application)
        ta_doc.add_comment(
            "Info",
            _("Linked Payment Entry {0} on submit.").format(doc.name),
            reference_doctype="Payment Entry",
            reference_name=doc.name,
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Failed to log Payment Entry submit for {transfer_application}",
        )


def on_cancel(doc, method=None):
    transfer_application = getattr(doc, "transfer_application", None)
    if not transfer_application:
        return

    updates = {
        "paid_date": None,
        "paid_amount": None,
    }

    current_link = frappe.db.get_value("Transfer Application", transfer_application, "payment_entry")
    if current_link == doc.name:
        updates["payment_entry"] = None

    workflow_state = frappe.db.get_value("Transfer Application", transfer_application, "workflow_state")
    if workflow_state == "Paid":
        workflow_state = "Awaiting Bank Confirmation"
    updates["workflow_state"] = workflow_state
    updates["status"] = workflow_state or "Awaiting Bank Confirmation"

    frappe.db.set_value("Transfer Application", transfer_application, updates)

    try:
        ta_doc = frappe.get_doc("Transfer Application", transfer_application)
        ta_doc.add_comment(
            "Info",
            _("Payment Entry {0} was cancelled; payment link cleared.").format(doc.name),
            reference_doctype="Payment Entry",
            reference_name=doc.name,
        )
    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Failed to log Payment Entry cancel for {transfer_application}",
        )
