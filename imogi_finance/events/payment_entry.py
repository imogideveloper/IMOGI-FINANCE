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


def _validate_expense_request_link(doc, request, request_name: str) -> None:
    linked_payment_entry = getattr(request, "linked_payment_entry", None)
    if linked_payment_entry and linked_payment_entry != doc.name:
        frappe.throw(
            _("Expense Request already linked to Payment Entry {0}").format(
                linked_payment_entry
            )
        )

    existing_payment_entry = frappe.db.exists(
        "Payment Entry",
        {
            "imogi_expense_request": request.name,
            "docstatus": ["!=", 2],
            "name": ["!=", doc.name],
        },
    )
    if existing_payment_entry:
        frappe.throw(
            _("An active Payment Entry {0} already exists for Expense Request {1}").format(
                existing_payment_entry, request.name
            )
        )


def _sync_expense_request_link(
    doc, request_name: str | None, *, allowed_statuses: frozenset[str] | set[str] | None = None
):
    if not request_name:
        frappe.logger().info(f"[_sync_expense_request_link] No request_name for PE: {doc.name}")
        return None
    
    frappe.logger().info(f"[_sync_expense_request_link] Syncing PE {doc.name} to ER {request_name}")
    
    _ensure_expense_request_reference(doc, request_name)

    request = get_approved_expense_request(
        request_name, _("Payment Entry"), allowed_statuses=allowed_statuses
    )

    _validate_expense_request_link(doc, request, request_name)

    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"linked_payment_entry": doc.name},
    )
    
    frappe.logger().info(f"[_sync_expense_request_link] Successfully linked PE {doc.name} to ER {request_name}")
    
    return request


def sync_expense_request_reference(doc, method=None):
    """Persist Expense Request reference from Payment Entry references.
    
    This runs in validate hook to auto-populate the field before save.
    """
    # Skip if already set manually
    if doc.get("imogi_expense_request"):
        return
    
    request_name = _resolve_expense_request(doc)
    
    # Debug logging
    frappe.logger().info(f"[Payment Entry validate] PE: {getattr(doc, 'name', 'NEW')}, Resolved ER: {request_name}")
    frappe.logger().info(f"[Payment Entry validate] References count: {len(doc.get('references') or [])}")
    
    if request_name:
        doc.imogi_expense_request = request_name
        frappe.logger().info(f"[Payment Entry validate] Set imogi_expense_request to {request_name}")


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
    # Skip - references table tidak terisi di after_insert
    # Logic di-handle di on_update dan on_submit
    pass


def on_update(doc, method=None):
    """Ensure Expense Request link syncs when set after insert."""
    if doc.get("docstatus") == 2:
        return
    
    # Skip if already linked
    if doc.get("imogi_expense_request"):
        return
    
    request_name = _resolve_expense_request(doc)
    
    # Debug logging
    frappe.logger().info(f"[Payment Entry on_update] PE: {doc.name}, Resolved ER: {request_name}")
    
    if not request_name:
        return
    
    # Sync link to ER (draft only)
    _sync_expense_request_link(doc, request_name)


def on_submit(doc, method=None):
    request_name = _resolve_expense_request(doc)
    if not request_name:
        return
    
    # Sync link with validation for submit
    request = _sync_expense_request_link(
        doc, request_name, allowed_statuses=frozenset({"PI Created"})
    )
    if not request:
        return

    # Validate this PE is the one linked to ER (set in after_insert)
    linked_payment_entry = getattr(request, "linked_payment_entry", None)
    if linked_payment_entry and linked_payment_entry != doc.name:
        frappe.throw(
            _("Expense Request already linked to a different Payment Entry {0}").format(
                linked_payment_entry
            )
        )

    has_purchase_invoice = getattr(request, "linked_purchase_invoice", None)
    if has_purchase_invoice:
        pi_docstatus = frappe.db.get_value("Purchase Invoice", has_purchase_invoice, "docstatus")
        if pi_docstatus != 1:
            frappe.throw(
                _("Linked Purchase Invoice {0} must be submitted before creating Payment Entry.").format(
                    has_purchase_invoice
                )
            )
    if not has_purchase_invoice:
        frappe.throw(
            _("Expense Request must be linked to a Purchase Invoice before submitting Payment Entry.")
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
    """Handle Payment Entry cancellation.
    
    When PE is cancelled:
    1. Clear linked_payment_entry from Expense Request
    2. Update status back to "PI Created" (or "Approved" if no PI)
    """
    request_name = _resolve_expense_request(doc)
    if not request_name:
        frappe.logger().info(f"[Payment Entry on_cancel] No ER linked to PE {doc.name}")
        return

    # Get cancel updates (clears linked_payment_entry and updates status)
    updates = get_cancel_updates(request_name, "linked_payment_entry")
    
    frappe.logger().info(f"[Payment Entry on_cancel] PE {doc.name} cancelled, updating ER {request_name}")
    frappe.logger().info(f"[Payment Entry on_cancel] New status: {updates.get('status')}")
    
    # Update Expense Request
    frappe.db.set_value("Expense Request", request_name, updates)


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
