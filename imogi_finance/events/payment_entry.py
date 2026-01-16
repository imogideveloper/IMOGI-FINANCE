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

    # Always update to latest PE (auto-update from cancelled to new PE)
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
    # Allow "Paid" status for re-submitting PE after previous PE was cancelled
    request = _sync_expense_request_link(
        doc, request_name, allowed_statuses=frozenset({"PI Created", "Paid"})
    )
    if not request:
        return

    # Check if ER has another ACTIVE (submitted) PE
    linked_payment_entry = getattr(request, "linked_payment_entry", None)
    if linked_payment_entry and linked_payment_entry != doc.name:
        # Allow if old PE is cancelled (docstatus=2)
        old_pe_docstatus = frappe.db.get_value("Payment Entry", linked_payment_entry, "docstatus")
        if old_pe_docstatus == 1:  # Still submitted
            frappe.throw(
                _("Expense Request already linked to an active Payment Entry {0}. Cancel it first.").format(
                    linked_payment_entry
                )
            )
        # Old PE is cancelled/draft, proceed with linking new PE
        frappe.logger().info(f"[PE on_submit] Old PE {linked_payment_entry} is cancelled, linking to new PE {doc.name}")

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
    
def before_cancel(doc, method=None):
    """Pre-cancel validation and setup.
    
    1. Check if included in printed daily reports
    2. Set flags to ignore ALL linked documents (they should not be cancelled)
    3. Suppress "Cancel All Documents" dialog completely
    """
    # Check printed report constraint
    if _check_linked_to_printed_report(doc):
        frappe.throw(
            frappe._(
                "Cannot cancel Payment Entry {0} because it is included in a printed Cash/Bank Daily Report. "
                "Use the 'Reverse Payment Entry' button instead to create a reversal entry at today's date."
            ).format(doc.name),
            title=_("Cancellation Blocked")
        )
    
    # Set multiple flags to completely suppress "Cancel All Documents" dialog
    doc.flags.ignore_links = True
    doc.flags.ignore_link_validation = True
    doc.flags.skip_link_doctypes = True


def on_cancel(doc, method=None):
    """Handle Payment Entry cancellation.
    
    Payment Entry is the endpoint of the payment flow and can be freely cancelled,
    EXCEPT when already included in printed Cash/Bank Daily Reports.
    
    Philosophy:
    - PE cancel does not invalidate upstream documents (ER, PI)
    - Links remain intact for audit trail
    - New PE can be created anytime from existing PI
    - Only constraint: printed daily reports (accounting lock)
    
    When PE is cancelled:
    1. Check if linked to any printed daily reports (done in before_cancel)
    2. If yes, BLOCK cancellation and suggest reversal
    3. If no, allow cancellation without touching ER/PI status
    """
    
    # That's it! No need to rollback ER status or clear links
    # ER stays "Paid", links stay intact, PI remains valid
    frappe.logger().info(f"[Payment Entry on_cancel] PE {doc.name} cancelled successfully (ER/PI unchanged)")


def _check_linked_to_printed_report(payment_entry) -> bool:
    """Check if Payment Entry is included in any printed (submitted) Cash/Bank Daily Reports.
    
    For Cash Account mode (GL Entry):
    - Check GL Entry posting_date and match with submitted reports
    
    For Bank Account mode (Bank Transaction):
    - Check Bank Transaction date and match with submitted reports
    
    Returns True if linked to submitted report (docstatus=1).
    """
    if not getattr(frappe, "db", None):
        return False
    
    # Get posting date from Payment Entry
    posting_date = getattr(payment_entry, "posting_date", None)
    if not posting_date:
        return False
    
    # Check for submitted (printed) reports on this date
    # For cash accounts (via GL Entry)
    printed_reports = frappe.get_all(
        "Cash Bank Daily Report",
        filters={
            "report_date": posting_date,
            "docstatus": 1  # Submitted = Printed
        },
        fields=["name", "cash_account", "bank_account"]
    )
    
    if not printed_reports:
        return False
    
    # Check if PE's account matches any printed report's account
    pe_account = getattr(payment_entry, "paid_from", None) or getattr(payment_entry, "paid_to", None)
    
    for report in printed_reports:
        if report.get("cash_account") == pe_account or report.get("bank_account") == pe_account:
            return True
    
    return False


@frappe.whitelist()
def reverse_payment_entry(payment_entry_name: str, reversal_date: str | None = None):
    """Create a reversal Payment Entry at today's date (or specified date).
    
    This is the proper way to reverse a Payment Entry that's already included
    in a printed Cash/Bank Daily Report, instead of cancelling it.
    
    The reversal entry:
    - Mirrors all amounts and accounts (flipped direction)
    - Posts at reversal_date (default: today)
    - Links back to original PE in remarks
    - Updates Expense Request status back to "PI Created"
    
    Args:
        payment_entry_name: Name of Payment Entry to reverse
        reversal_date: Date for reversal entry (default: today)
    
    Returns:
        dict: Created reversal Payment Entry
    """
    from datetime import date as date_class
    
    # Get original PE
    original_pe = frappe.get_doc("Payment Entry", payment_entry_name)
    
    if original_pe.docstatus != 1:
        frappe.throw(frappe._("Can only reverse submitted Payment Entries"))
    
    # Default reversal date to today
    if not reversal_date:
        reversal_date = frappe.utils.today()
    
    # Create reversal PE
    reversal_pe = frappe.get_doc({
        "doctype": "Payment Entry",
        "posting_date": reversal_date,
        "payment_type": original_pe.payment_type,
        "company": original_pe.company,
        # Flip accounts
        "paid_from": original_pe.paid_to,  # Reversed
        "paid_to": original_pe.paid_from,  # Reversed
        "paid_amount": original_pe.paid_amount,
        "received_amount": original_pe.received_amount,
        "source_exchange_rate": original_pe.source_exchange_rate,
        "target_exchange_rate": original_pe.target_exchange_rate,
        "mode_of_payment": original_pe.mode_of_payment,
        "party_type": original_pe.party_type,
        "party": original_pe.party,
        "branch": original_pe.branch if hasattr(original_pe, "branch") else None,
        "remarks": frappe._(
            "Reversal of Payment Entry {0} (original date: {1})"
        ).format(
            original_pe.name,
            frappe.utils.format_date(original_pe.posting_date)
        ),
        # Copy references if any
        "references": [
            {
                "reference_doctype": ref.reference_doctype,
                "reference_name": ref.reference_name,
                "total_amount": ref.total_amount,
                "outstanding_amount": ref.outstanding_amount,
                "allocated_amount": -ref.allocated_amount  # Negative to reverse
            }
            for ref in (original_pe.references or [])
        ] if original_pe.get("references") else [],
        # Mark as reversal
        "is_reversal": 1,
        "reversed_entry": original_pe.name
    })
    
    reversal_pe.insert()
    
    frappe.msgprint(
        frappe._(
            "Reversal Payment Entry {0} created for date {1}. "
            "Please review and submit it."
        ).format(reversal_pe.name, frappe.utils.format_date(reversal_date)),
        indicator="green",
        title=_("Reversal Created")
    )
    
    # Update original PE to mark it as reversed
    frappe.db.set_value("Payment Entry", payment_entry_name, {
        "is_reversed": 1,
        "reversal_entry": reversal_pe.name
    })
    
    # Update Expense Request status back to PI Created
    request_name = _resolve_expense_request(original_pe)
    if request_name:
        updates = get_cancel_updates(request_name, "linked_payment_entry")
        frappe.db.set_value("Expense Request", request_name, updates)
    
    return reversal_pe.as_dict()


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
