import frappe
from frappe import _

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
    get_expense_request_links,
    get_expense_request_status,
)


def _resolve_expense_request(doc) -> tuple[str | None, str | None]:
    """Resolve expense request and branch expense request.
    
    Returns:
        tuple: (expense_request_name, branch_request_name)
    """
    expense_request = doc.get("imogi_expense_request") or doc.get("expense_request")
    branch_request = doc.get("branch_expense_request")
    
    if expense_request or branch_request:
        return expense_request, branch_request

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
                ["imogi_expense_request", "expense_request", "branch_expense_request"],
                as_dict=True,
            )
        except Exception:
            values = None
        if values:
            return (
                values.get("imogi_expense_request") or values.get("expense_request"),
                values.get("branch_expense_request")
            )

    return None, None


def _ensure_expense_request_reference(doc, expense_request: str | None, branch_request: str | None) -> None:
    """Ensure expense request or branch request reference is set on Payment Entry."""
    if expense_request and not doc.get("imogi_expense_request"):
        if hasattr(doc, "db_set"):
            try:
                doc.db_set("imogi_expense_request", expense_request, update_modified=False)
            except Exception:
                setattr(doc, "imogi_expense_request", expense_request)
        else:
            setattr(doc, "imogi_expense_request", expense_request)
    
    if branch_request and not doc.get("branch_expense_request"):
        if hasattr(doc, "db_set"):
            try:
                doc.db_set("branch_expense_request", branch_request, update_modified=False)
            except Exception:
                setattr(doc, "branch_expense_request", branch_request)
        else:
            setattr(doc, "branch_expense_request", branch_request)


def _validate_expense_request_link(doc, request, request_name: str) -> None:
    """Validate Payment Entry link to Expense Request.
    
    Note: Multiple PE per ER is allowed (1 PI can have multiple payments).
    This function is kept for future validation needs.
    """
    # ✅ Multiple PE per ER is ALLOWED
    # 1 PI can be paid via multiple Payment Entries
    # No validation needed here
    pass


def _sync_expense_request_link(
    doc, expense_request: str | None, branch_request: str | None, *, allowed_statuses: frozenset[str] | set[str] | None = None
):
    """Sync Payment Entry link to Expense Request or Branch Expense Request."""
    if not expense_request and not branch_request:
        frappe.logger().info(f"[_sync_expense_request_link] No request for PE: {doc.name}")
        return None
    
    frappe.logger().info(f"[_sync_expense_request_link] Syncing PE {doc.name} to ER {expense_request} / BER {branch_request}")
    
    _ensure_expense_request_reference(doc, expense_request, branch_request)

    if expense_request:
        request = get_approved_expense_request(
            expense_request, _("Payment Entry"), allowed_statuses=allowed_statuses
        )
        # ✅ Multiple PE per ER is allowed - no validation needed
        # Link established via doc.imogi_expense_request field
        # Status akan auto-update via query saat PE di-submit
        frappe.logger().info(f"[_sync_expense_request_link] Successfully synced PE {doc.name} to ER {expense_request}")
        return request
    
    if branch_request:
        request = frappe.get_doc("Branch Expense Request", branch_request)
        if request.docstatus != 1:
            frappe.throw(
                _("Branch Expense Request {0} must be submitted before creating Payment Entry").format(branch_request),
                title=_("Invalid Status")
            )
        # Link PE to Branch Expense Request
        if hasattr(request, "linked_payment_entry"):
            frappe.db.set_value(
                "Branch Expense Request",
                request.name,
                {"linked_payment_entry": doc.name},
            )
        frappe.logger().info(f"[_sync_expense_request_link] Successfully linked PE {doc.name} to BER {branch_request}")
        return request
    
    return None


def sync_expense_request_reference(doc, method=None):
    """Persist Expense Request or Branch Expense Request reference from Payment Entry references.
    
    This runs in validate hook to auto-populate the field before save.
    """
    # Skip if already set manually
    if doc.get("imogi_expense_request") or doc.get("branch_expense_request"):
        return
    
    expense_request, branch_request = _resolve_expense_request(doc)
    
    # Debug logging
    frappe.logger().info(f"[Payment Entry validate] PE: {getattr(doc, 'name', 'NEW')}, Resolved ER: {expense_request}, BER: {branch_request}")
    frappe.logger().info(f"[Payment Entry validate] References count: {len(doc.get('references') or [])}")
    
    if expense_request:
        doc.imogi_expense_request = expense_request
        frappe.logger().info(f"[Payment Entry validate] Set imogi_expense_request to {expense_request}")
    
    if branch_request:
        doc.branch_expense_request = branch_request
        frappe.logger().info(f"[Payment Entry validate] Set branch_expense_request to {branch_request}")


def on_change_expense_request(doc, method=None):
    """Auto-populate amount and description from selected Expense Request or Branch Expense Request."""
    expense_request = doc.get("imogi_expense_request")
    branch_request = doc.get("branch_expense_request")
    
    request = None
    request_type = None
    
    if expense_request:
        try:
            request = frappe.get_doc("Expense Request", expense_request)
            request_type = "Expense Request"
        except frappe.DoesNotExistError:
            frappe.msgprint(
                _("Expense Request {0} not found").format(expense_request),
                alert=True,
                indicator="orange"
            )
            return
    elif branch_request:
        try:
            request = frappe.get_doc("Branch Expense Request", branch_request)
            request_type = "Branch Expense Request"
        except frappe.DoesNotExistError:
            frappe.msgprint(
                _("Branch Expense Request {0} not found").format(branch_request),
                alert=True,
                indicator="orange"
            )
            return
    
    if not request:
        return
    
    try:
        # Fetch amount from request
        amount = getattr(request, "total_amount", None)
        if amount:
            doc.paid_amount = amount
            doc.received_amount = amount
        
        # Fetch description from request (if remarks field exists, populate with request details)
        if request.get("name"):
            existing_remarks = doc.get("remarks") or ""
            if request_type not in existing_remarks:
                doc.remarks = _("Payment for {0} {1} - {2}").format(
                    request_type,
                    request.name,
                    request.get("description", request.get("purpose", request.get("request_type", "")))
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
    """Ensure Expense Request or Branch Expense Request link syncs when set after insert."""
    if doc.get("docstatus") == 2:
        return
    
    # Skip if already linked
    if doc.get("imogi_expense_request") or doc.get("branch_expense_request"):
        return
    
    expense_request, branch_request = _resolve_expense_request(doc)
    
    # Debug logging
    frappe.logger().info(f"[Payment Entry on_update] PE: {doc.name}, Resolved ER: {expense_request}, BER: {branch_request}")
    
    if not expense_request and not branch_request:
        return
    
    # Sync link to request (draft only)
    _sync_expense_request_link(doc, expense_request, branch_request)


def on_submit(doc, method=None):
    expense_request, branch_request = _resolve_expense_request(doc)
    
    if not expense_request and not branch_request:
        return
    
    # Handle Expense Request
    if expense_request:
        _handle_expense_request_submit(doc, expense_request)
    
    # Handle Branch Expense Request
    if branch_request:
        _handle_branch_expense_request_submit(doc, branch_request)


def _handle_expense_request_submit(doc, expense_request):
    """Handle Payment Entry submit for Expense Request."""
    # Sync link with validation for submit
    # Allow "Paid" status for re-submitting PE after previous PE was cancelled
    request = _sync_expense_request_link(
        doc, expense_request, None, allowed_statuses=frozenset({"PI Created", "Paid"})
    )
    if not request:
        return

    # Validate ada PI yang submitted (query dari DB)
    has_purchase_invoice = frappe.db.get_value(
        "Purchase Invoice",
        {"imogi_expense_request": request.name, "docstatus": 1},
        "name"
    )
    
    if not has_purchase_invoice:
        frappe.throw(
            _("Expense Request must be linked to a submitted Purchase Invoice before submitting Payment Entry.")
        )

    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            getattr(doc, "branch", None),
            getattr(request, "branch", None),
            label=_("Payment Entry"),
        )

    # Update workflow state to Paid
    # Status akan auto-update via query karena PE.imogi_expense_request sudah set
    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"workflow_state": "Paid", "status": "Paid"},
    )


def _handle_branch_expense_request_submit(doc, branch_request):
    """Handle Payment Entry submit for Branch Expense Request."""
    # Sync link with validation
    request = _sync_expense_request_link(doc, None, branch_request)
    if not request:
        return
    
    # Check if has linked PI
    has_purchase_invoice = getattr(request, "linked_purchase_invoice", None)
    if has_purchase_invoice:
        pi_docstatus = frappe.db.get_value("Purchase Invoice", has_purchase_invoice, "docstatus")
        if pi_docstatus != 1:
            frappe.throw(
                _("Linked Purchase Invoice {0} must be submitted before creating Payment Entry.").format(
                    has_purchase_invoice
                )
            )
    
    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            getattr(doc, "branch", None),
            getattr(request, "branch", None),
            label=_("Payment Entry"),
        )
    
    # Update status to Paid if supported
    if hasattr(request, "status"):
        frappe.db.set_value(
            "Branch Expense Request",
            request.name,
            {"status": "Paid"},
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


def before_delete(doc, method=None):
    """Set flag to ignore link validation before deletion.
    
    This prevents LinkExistsError when deleting draft PE that is linked to ER.
    The actual link cleanup happens in on_trash.
    """
    expense_request, branch_request = _resolve_expense_request(doc)
    if expense_request or branch_request:
        doc.flags.ignore_links = True


def on_cancel(doc, method=None):
    """Handle Payment Entry cancellation.
    
    With multiple PE support:
    - If OTHER submitted PE still exist → Status remains "Paid"
    - If NO OTHER submitted PE exist → Status back to "PI Created"
    - Cancelled PE (docstatus=2) are automatically excluded by query
    
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
    3. If no, allow cancellation
    4. Status auto-updated via query:
       - Query filters docstatus=1 (only submitted)
       - Cancelled PE (docstatus=2) automatically excluded
       - If other PE exist → "Paid"
       - If no PE exist → "PI Created"
    """
    expense_request_name = doc.get("imogi_expense_request")
    branch_request_name = doc.get("branch_expense_request")
    
    # Update Expense Request workflow state
    # Query will automatically exclude this cancelled PE (docstatus=2)
    if expense_request_name:
        # Query untuk cek apakah masih ada PE lain yang submitted
        other_pes = frappe.db.get_all(
            "Payment Entry",
            filters={
                "imogi_expense_request": expense_request_name,
                "docstatus": 1,  # Only submitted
                "name": ["!=", doc.name]  # Exclude current (being cancelled)
            },
            pluck="name"
        )
        
        # Determine status based on remaining PEs
        if other_pes:
            # Masih ada PE lain yang submitted → status tetap "Paid"
            next_status = "Paid"
            frappe.logger().info(
                f"[PE on_cancel] PE {doc.name} cancelled, "
                f"but {len(other_pes)} other PE(s) still active: {other_pes}. "
                f"ER status remains 'Paid'"
            )
        else:
            # Tidak ada PE lain → status kembali ke "PI Created" (atau "Approved" jika PI juga cancelled)
            request_links = get_expense_request_links(expense_request_name)
            next_status = get_expense_request_status(request_links)
            frappe.logger().info(
                f"[PE on_cancel] PE {doc.name} cancelled, "
                f"no other active PE. ER status: {next_status}"
            )
        
        frappe.db.set_value(
            "Expense Request",
            expense_request_name,
            {"workflow_state": next_status}
        )
    
    # Update Branch Expense Request
    if branch_request_name:
        if frappe.db.exists("Branch Expense Request", branch_request_name):
            # Check if other PEs exist
            other_pes = frappe.db.get_all(
                "Payment Entry",
                filters={
                    "branch_expense_request": branch_request_name,
                    "docstatus": 1,
                    "name": ["!=", doc.name]
                },
                pluck="name"
            )
            
            # Update status based on remaining PEs
            if not other_pes:
                frappe.db.set_value(
                    "Branch Expense Request",
                    branch_request_name,
                    {"linked_payment_entry": None}
                )


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
        # Flip account currencies to match flipped accounts
        "paid_from_account_currency": getattr(original_pe, "paid_to_account_currency", None),
        "paid_to_account_currency": getattr(original_pe, "paid_from_account_currency", None),
        "source_exchange_rate": original_pe.source_exchange_rate,
        "target_exchange_rate": original_pe.target_exchange_rate,
        "mode_of_payment": original_pe.mode_of_payment,
        "party_type": original_pe.party_type,
        "party": original_pe.party,
        # Copy party_account - this is the party's receivable/payable account
        "party_account": getattr(original_pe, "party_account", None),
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
    
    # Update Expense Request workflow state
    # Check if other submitted PEs still exist
    expense_request, branch_request = _resolve_expense_request(original_pe)
    
    if expense_request:
        # Query untuk cek apakah masih ada PE lain yang submitted
        # Note: original PE belum di-cancel, masih docstatus=1
        # Tapi sudah di-mark is_reversed=1
        other_pes = frappe.db.get_all(
            "Payment Entry",
            filters={
                "imogi_expense_request": expense_request,
                "docstatus": 1,  # Only submitted
                "name": ["!=", payment_entry_name],  # Exclude reversed PE
                "is_reversed": ["!=", 1]  # Exclude reversed PEs
            },
            pluck="name"
        )
        
        # Determine status based on remaining PEs
        if other_pes:
            # Masih ada PE lain yang active → status tetap "Paid"
            next_status = "Paid"
            frappe.logger().info(
                f"[PE reversal] PE {payment_entry_name} reversed, "
                f"but {len(other_pes)} other PE(s) still active: {other_pes}. "
                f"ER status remains 'Paid'"
            )
        else:
            # Tidak ada PE lain → status kembali ke "PI Created"
            request_links = get_expense_request_links(expense_request)
            next_status = get_expense_request_status(request_links)
            frappe.logger().info(
                f"[PE reversal] PE {payment_entry_name} reversed, "
                f"no other active PE. ER status: {next_status}"
            )
        
        frappe.db.set_value(
            "Expense Request",
            expense_request,
            {"workflow_state": next_status}
        )
    
    if branch_request:
        if frappe.db.exists("Branch Expense Request", branch_request):
            frappe.db.set_value("Branch Expense Request", branch_request, "linked_payment_entry", None)
    
    return reversal_pe.as_dict()


def on_trash(doc, method=None):
    """Clear links from Expense Request before deleting PE to avoid LinkExistsError."""
    expense_request, branch_request = _resolve_expense_request(doc)
    
    # Handle Expense Request - clear link and update workflow state
    if expense_request:
        if frappe.db.exists("Expense Request", expense_request):
            updates = {}
            
            # Clear linked_payment_entry if it matches (THIS IS THE KEY FIX)
            # This field is what causes LinkExistsError
            current_linked = frappe.db.get_value("Expense Request", expense_request, "linked_payment_entry")
            if current_linked == doc.name:
                updates["linked_payment_entry"] = None
            
            # Update workflow state based on remaining links
            request_links = get_expense_request_links(expense_request)
            next_status = get_expense_request_status(request_links)
            updates["workflow_state"] = next_status
            
            frappe.db.set_value("Expense Request", expense_request, updates)
            frappe.db.commit()  # Commit immediately to ensure link is cleared
    
    # Handle Branch Expense Request
    if branch_request:
        if frappe.db.exists("Branch Expense Request", branch_request):
            linked_pe = frappe.db.get_value("Branch Expense Request", branch_request, "linked_payment_entry")
            if linked_pe == doc.name:
                frappe.db.set_value("Branch Expense Request", branch_request, "linked_payment_entry", None)
                frappe.db.commit()  # Commit immediately
