import frappe
from frappe import _

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
    get_expense_request_links,
    get_expense_request_status,
)


def _resolve_expense_request(doc) -> str | None:
    request_name = doc.get("imogi_expense_request") or doc.get("expense_request")
    if request_name:
        return request_name

    references = doc.get("references") or []
    for ref in references:
        if ref.get("reference_doctype") != "Purchase Invoice":
            continue
        reference_name = ref.get("reference_name")
        if not reference_name:
            continue
        try:
            values = frappe.db.get_value(
                "Purchase Invoice",
                reference_name,
                ["imogi_expense_request", "expense_request"],
                as_dict=True,
            )
        except Exception:
            values = None
        if values:
            return values.get("imogi_expense_request") or values.get("expense_request")

    return None


def _ensure_expense_request_reference(doc, request_name: str | None) -> None:
    if not request_name:
        return
    if doc.get("imogi_expense_request"):
        return
    if hasattr(doc, "db_set"):
        try:
            doc.db_set("imogi_expense_request", request_name, update_modified=False)
            return
        except Exception:
            pass
    setattr(doc, "imogi_expense_request", request_name)


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


def after_insert(doc, method=None):
    """Link Payment Entry to Expense Request immediately on draft creation."""
    request_name = _resolve_expense_request(doc)
    if not request_name:
        return
    _ensure_expense_request_reference(doc, request_name)

    # Validate ER is in correct status
    request = get_approved_expense_request(
        request_name, _("Payment Entry")
    )

    # Check no other PE is already linked
    linked_payment_entry = getattr(request, "linked_payment_entry", None)
    if linked_payment_entry and linked_payment_entry != doc.name:
        frappe.throw(
            _("Expense Request already linked to Payment Entry {0}").format(
                linked_payment_entry
            )
        )

    # Check no other active PE exists for this ER
    existing_payment_entry = frappe.db.exists(
        "Payment Entry",
        {"imogi_expense_request": request.name, "docstatus": ["!=", 2], "name": ["!=", doc.name]},
    )
    if existing_payment_entry:
        frappe.throw(
            _("An active Payment Entry {0} already exists for Expense Request {1}").format(
                existing_payment_entry, request.name
            )
        )

    # Set linked_payment_entry immediately, status remains PI Created
    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"linked_payment_entry": doc.name},
    )


def on_submit(doc, method=None):
    request = _resolve_expense_request(doc)
    if not request:
        return
    _ensure_expense_request_reference(doc, request)

    request = get_approved_expense_request(
        request, _("Payment Entry"), allowed_statuses=frozenset({"PI Created"})
    )

    # Validate this PE is the one linked to ER (set in after_insert)
    linked_payment_entry = getattr(request, "linked_payment_entry", None)
    if linked_payment_entry and linked_payment_entry != doc.name:
        frappe.throw(
            _("Expense Request already linked to a different Payment Entry {0}").format(
                linked_payment_entry
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

    # Update status to Paid now that PE is submitted
    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"status": "Paid", "workflow_state": "Paid"},
    )


def on_cancel(doc, method=None):
    request = _resolve_expense_request(doc)
    if not request:
        return

    updates = get_cancel_updates(request, "linked_payment_entry")

    frappe.db.set_value("Expense Request", request, updates)


def on_trash(doc, method=None):
    """Clear linked_payment_entry when Payment Entry is deleted."""
    request = _resolve_expense_request(doc)
    if not request:
        return

    request_links = get_expense_request_links(request)
    
    # Only clear if this PE is the linked one
    if request_links.get("linked_payment_entry") != doc.name:
        return

    remaining_links = dict(request_links)
    remaining_links["linked_payment_entry"] = None
    next_status = get_expense_request_status(remaining_links)

    frappe.db.set_value(
        "Expense Request",
        request,
        {"linked_payment_entry": None, "status": next_status, "workflow_state": next_status},
    )
