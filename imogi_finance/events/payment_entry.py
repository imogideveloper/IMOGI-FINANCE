import frappe
from frappe import _

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
)


def on_change_expense_request(doc, method=None):
    """Auto-populate amount and description from selected Expense Request."""
    request_name = doc.get("imogi_expense_request")
    if not request_name:
        return

    try:
        request = frappe.get_doc("Expense Request", request_name)
        
        # Fetch amount from ER
        if request.total_amount:
            doc.paid_amount = request.total_amount
            doc.received_amount = request.total_amount
        
        # Fetch description from ER (if remarks field exists, populate with ER details)
        if request.get("name"):
            existing_remarks = doc.get("remarks") or ""
            if "Expense Request" not in existing_remarks:
                doc.remarks = _("Payment for Expense Request {0} - {1}").format(
                    request.name,
                    request.get("description", request.get("request_type", ""))
                )
    except frappe.DoesNotExistError:
        frappe.msgprint(
            _("Expense Request {0} not found").format(request_name),
            alert=True,
            indicator="orange"
        )
    except Exception as e:
        # Don't block document save for data fetch errors
        pass


def on_submit(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    request = get_approved_expense_request(
        request, _("Payment Entry"), allowed_statuses=frozenset({"PI Created"})
    )

    linked_payment_entry = getattr(request, "linked_payment_entry", None)
    if linked_payment_entry:
        frappe.throw(
            _("Expense Request already linked to Payment Entry {0}").format(
                linked_payment_entry
            )
        )

    existing_payment_entry = frappe.db.exists(
        "Payment Entry",
        {"imogi_expense_request": request.name, "docstatus": ["!=", 2]},
    )
    if existing_payment_entry:
        frappe.throw(
            _("An active Payment Entry {0} already exists for Expense Request {1}").format(
                existing_payment_entry, request.name
            )
        )

    has_purchase_invoice = getattr(request, "linked_purchase_invoice", None)
    has_asset_link = request.request_type == "Asset" and getattr(
        request, "linked_asset", None
    )
    if has_purchase_invoice:
        pi_docstatus = frappe.db.get_value("Purchase Invoice", has_purchase_invoice, "docstatus")
        if pi_docstatus != 1:
            frappe.throw(
                _("Linked Purchase Invoice {0} must be submitted before creating Payment Entry.").format(
                    has_purchase_invoice
                )
            )
    if has_asset_link:
        asset_docstatus = frappe.db.get_value("Asset", has_asset_link, "docstatus")
        if asset_docstatus != 1:
            frappe.throw(
                _("Linked Asset {0} must be submitted before creating Payment Entry.").format(
                    has_asset_link
                )
            )
    if not has_purchase_invoice and not has_asset_link:
        frappe.throw(
            _(
                "Expense Request must be linked to a Purchase Invoice{0} before submitting Payment Entry."
            ).format(
                _(" or Asset") if request.request_type == "Asset" else ""
            )
        )

    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            getattr(doc, "branch", None),
            getattr(request, "branch", None),
            label=_("Payment Entry"),
        )

    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"linked_payment_entry": doc.name, "status": "Paid"},
    )


def on_cancel(doc, method=None):
    request = doc.get("imogi_expense_request")
    if not request:
        return

    updates = get_cancel_updates(request, "linked_payment_entry")

    frappe.db.set_value("Expense Request", request, updates)
