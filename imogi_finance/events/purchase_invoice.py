import frappe
from frappe import _
from frappe.utils import cint

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.accounting import PURCHASE_INVOICE_ALLOWED_STATUSES, PURCHASE_INVOICE_REQUEST_TYPES
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
    get_expense_request_links,
    get_expense_request_status,
)
from imogi_finance.tax_invoice_ocr import (
    get_settings,
    normalize_npwp,
    sync_tax_invoice_upload,
    validate_tax_invoice_upload_link,
)
from imogi_finance.budget_control.workflow import (
    consume_budget_for_purchase_invoice,
    reverse_consumption_for_purchase_invoice,
    maybe_post_internal_charge_je,
)


def validate_before_submit(doc, method=None):
    # Sync OCR fields but don't save - document will be saved automatically after this hook
    sync_tax_invoice_upload(doc, "Purchase Invoice", save=False)
    validate_tax_invoice_upload_link(doc, "Purchase Invoice")
    
    # Validate NPWP match between OCR and Supplier
    _validate_npwp_match(doc)
    
    # Validate 1 ER = 1 PI (only submitted PI, cancelled are ignored)
    _validate_one_pi_per_request(doc)
    
    settings = get_settings()
    require_verified = cint(settings.get("enable_tax_invoice_ocr")) and cint(
        settings.get("require_verification_before_submit_pi")
    )
    has_tax_invoice_upload = bool(getattr(doc, "ti_tax_invoice_upload", None))
    if (
        require_verified
        and has_tax_invoice_upload
        and getattr(doc, "ti_verification_status", "") != "Verified"
    ):
        message = _("Tax Invoice must be verified before submitting this Purchase Invoice.")
        marker = getattr(frappe, "ThrowMarker", None)
        throw_fn = getattr(frappe, "throw", None)

        if callable(throw_fn):
            try:
                throw_fn(message, title=_("Verification Required"))
                return
            except Exception as exc:
                if marker and not isinstance(exc, marker) and exc.__class__.__name__ != "ThrowCalled":
                    raise marker(message)
                raise

        if marker:
            raise marker(message)
        raise Exception(message)


def _validate_one_pi_per_request(doc):
    """Validate 1 Expense Request = 1 Purchase Invoice (submitted only).
    
    Cancelled PI are ignored - allow creating new PI if old one is cancelled.
    """
    expense_request = doc.get("imogi_expense_request")
    branch_request = doc.get("branch_expense_request")
    
    if expense_request:
        existing_pi = frappe.db.get_value(
            "Purchase Invoice",
            {
                "imogi_expense_request": expense_request,
                "docstatus": 1,  # Only submitted
                "name": ["!=", doc.name]
            },
            "name"
        )
        
        if existing_pi:
            frappe.throw(
                _("Expense Request {0} is already linked to submitted Purchase Invoice {1}. Please cancel that PI first.").format(
                    expense_request, existing_pi
                ),
                title=_("Duplicate Purchase Invoice")
            )
    
    if branch_request:
        existing_pi = frappe.db.get_value(
            "Purchase Invoice",
            {
                "branch_expense_request": branch_request,
                "docstatus": 1,  # Only submitted
                "name": ["!=", doc.name]
            },
            "name"
        )
        
        if existing_pi:
            frappe.throw(
                _("Branch Expense Request {0} is already linked to submitted Purchase Invoice {1}. Please cancel that PI first.").format(
                    branch_request, existing_pi
                ),
                title=_("Duplicate Purchase Invoice")
            )


def _validate_npwp_match(doc):
    """Validate NPWP from OCR matches supplier's NPWP.
    
    Skip validation if Purchase Invoice is created from Expense Request or Branch Expense Request
    because validation has already been done at the request level.
    """
    # Skip if linked to Expense Request or Branch Expense Request
    if getattr(doc, "imogi_expense_request", None) or getattr(doc, "branch_expense_request", None):
        return
    
    has_tax_invoice_upload = bool(getattr(doc, "ti_tax_invoice_upload", None))
    if not has_tax_invoice_upload:
        return
    
    supplier_npwp = getattr(doc, "supplier_tax_id", None)
    ocr_npwp = getattr(doc, "ti_fp_npwp", None)
    
    if not supplier_npwp or not ocr_npwp:
        return
    
    supplier_npwp_normalized = normalize_npwp(supplier_npwp)
    ocr_npwp_normalized = normalize_npwp(ocr_npwp)
    
    if supplier_npwp_normalized and ocr_npwp_normalized and supplier_npwp_normalized != ocr_npwp_normalized:
        frappe.throw(
            _("NPWP dari OCR ({0}) tidak sesuai dengan NPWP Supplier ({1})").format(
                ocr_npwp, supplier_npwp
            ),
            title=_("NPWP Mismatch")
        )


def on_submit(doc, method=None):
    # Check for Expense Request or Branch Expense Request
    expense_request = doc.get("imogi_expense_request")
    branch_request = doc.get("branch_expense_request")
    
    if expense_request:
        _handle_expense_request_submit(doc, expense_request)
    elif branch_request:
        _handle_branch_expense_request_submit(doc, branch_request)


def _handle_expense_request_submit(doc, request_name):
    """Handle Purchase Invoice submit for Expense Request."""
    request = get_approved_expense_request(
        request_name, _("Purchase Invoice"), allowed_statuses=PURCHASE_INVOICE_ALLOWED_STATUSES | {"PI Created"}
    )

    # Validate tidak ada PI lain yang sudah linked (query dari DB)
    existing_pi = frappe.db.get_value(
        "Purchase Invoice",
        {
            "imogi_expense_request": request.name,
            "docstatus": 1,
            "name": ["!=", doc.name]
        },
        "name"
    )
    
    if existing_pi:
        frappe.throw(
            _("Expense Request is already linked to a different Purchase Invoice {0}.").format(
                existing_pi
            )
        )

    if request.request_type not in PURCHASE_INVOICE_REQUEST_TYPES:
        frappe.throw(
            _("Purchase Invoice can only be linked for request type(s): {0}").format(
                ", ".join(sorted(PURCHASE_INVOICE_REQUEST_TYPES))
            )
        )

    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            getattr(doc, "branch", None),
            getattr(request, "branch", None),
            label=_("Purchase Invoice"),
        )

    # Update workflow state to PI Created
    # Status akan auto-update via query karena PI.imogi_expense_request sudah set
    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"workflow_state": "PI Created", "status": "PI Created", "pending_purchase_invoice": None},
    )
    
    # Budget consumption MUST succeed or PI submit fails
    try:
        consume_budget_for_purchase_invoice(doc, expense_request=request)
    except frappe.ValidationError:
        raise
    except Exception as e:
        frappe.log_error(
            title=f"Budget Consumption Failed for PI {doc.name}",
            message=f"Error: {str(e)}\n\n{frappe.get_traceback()}"
        )
        frappe.throw(
            _("Budget consumption failed. Purchase Invoice cannot be submitted. Error: {0}").format(str(e)),
            title=_("Budget Control Error")
        )
    
    maybe_post_internal_charge_je(doc, expense_request=request)


def _handle_branch_expense_request_submit(doc, request_name):
    """Handle Purchase Invoice submit for Branch Expense Request."""
    # Get the Branch Expense Request
    request = frappe.get_doc("Branch Expense Request", request_name)
    
    # Validate request is approved/submitted
    if request.docstatus != 1:
        frappe.throw(
            _("Branch Expense Request {0} must be submitted before creating Purchase Invoice").format(request_name),
            title=_("Invalid Status")
        )
    
    # Validate linked_purchase_invoice matches this PI
    if hasattr(request, "linked_purchase_invoice") and request.linked_purchase_invoice and request.linked_purchase_invoice != doc.name:
        frappe.throw(
            _("Branch Expense Request is already linked to a different Purchase Invoice {0}.").format(
                request.linked_purchase_invoice
            )
        )
    
    branch_settings = get_branch_settings()
    if branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
        validate_branch_alignment(
            getattr(doc, "branch", None),
            getattr(request, "branch", None),
            label=_("Purchase Invoice"),
        )
    
    # Update status - link PI to request
    if hasattr(request, "linked_purchase_invoice"):
        frappe.db.set_value(
            "Branch Expense Request",
            request.name,
            {"linked_purchase_invoice": doc.name},
        )


def before_cancel(doc, method=None):
    if doc.get("imogi_expense_request") or doc.get("branch_expense_request"):
        doc.flags.ignore_links = True


def before_delete(doc, method=None):
    """Set flag to ignore link validation before deletion.
    
    This prevents LinkExistsError when deleting draft PI that is linked to ER.
    The actual link cleanup happens in on_trash.
    """
    if doc.get("imogi_expense_request") or doc.get("branch_expense_request"):
        doc.flags.ignore_links = True


def on_cancel(doc, method=None):
    """Handle Purchase Invoice cancellation.
    
    When PI is cancelled:
    1. Check for active Payment Entry (must be cancelled first)
    2. Reverse budget consumption
    3. Update workflow state (status auto-updated via query)
    """
    expense_request_name = doc.get("imogi_expense_request")
    branch_request_name = doc.get("branch_expense_request")
    
    # Check for active Payment Entry via query
    if expense_request_name:
        pe = frappe.db.get_value(
            "Payment Entry",
            {"imogi_expense_request": expense_request_name, "docstatus": 1},
            "name"
        )
        if pe:
            frappe.throw(
                _("Cannot cancel Purchase Invoice. Payment Entry {0} must be cancelled first.").format(pe),
                title=_("Active Payment Exists")
            )
    
    # Reverse budget consumption - MUST succeed or cancel fails
    try:
        reverse_consumption_for_purchase_invoice(doc)
    except Exception as e:
        frappe.log_error(
            title=f"Budget Reversal Failed for PI {doc.name}",
            message=f"Error: {str(e)}\n\n{frappe.get_traceback()}"
        )
        frappe.throw(
            _("Failed to reverse budget consumption. Purchase Invoice cannot be cancelled. Error: {0}").format(str(e)),
            title=_("Budget Reversal Error")
        )
    
    # Update Expense Request workflow state
    # Status akan auto-update via query (tidak ada PI submitted lagi)
    if expense_request_name:
        request_links = get_expense_request_links(expense_request_name)
        next_status = get_expense_request_status(request_links)
        frappe.db.set_value(
            "Expense Request",
            expense_request_name,
            {"workflow_state": next_status, "pending_purchase_invoice": None}
        )
    
    # Update Branch Expense Request
    if branch_request_name:
        if frappe.db.exists("Branch Expense Request", branch_request_name):
            frappe.db.set_value("Branch Expense Request", branch_request_name, "linked_purchase_invoice", None)



def on_trash(doc, method=None):
    """Clear links from Expense Request before deleting PI to avoid LinkExistsError."""
    expense_request = doc.get("imogi_expense_request")
    branch_request = doc.get("branch_expense_request")
    
    # Handle Expense Request
    if expense_request:
        if frappe.db.exists("Expense Request", expense_request):
            # Clear BOTH linked and pending fields to break the link
            request_links = get_expense_request_links(expense_request, include_pending=True)
            updates = {}
            
            # Clear pending_purchase_invoice if it matches
            if request_links.get("pending_purchase_invoice") == doc.name:
                updates["pending_purchase_invoice"] = None
            
            # Clear linked_purchase_invoice if it matches (THIS IS THE FIX)
            # This field is what causes LinkExistsError
            current_linked = frappe.db.get_value("Expense Request", expense_request, "linked_purchase_invoice")
            if current_linked == doc.name:
                updates["linked_purchase_invoice"] = None

            if updates or True:  # Always update workflow state
                # Re-query untuk get status terbaru (after clearing links)
                current_links = get_expense_request_links(expense_request)
                next_status = get_expense_request_status(current_links)
                updates["workflow_state"] = next_status
                
                frappe.db.set_value("Expense Request", expense_request, updates)
                frappe.db.commit()  # Commit immediately to ensure link is cleared
    
    # Handle Branch Expense Request
    if branch_request:
        if frappe.db.exists("Branch Expense Request", branch_request):
            linked_pi = frappe.db.get_value("Branch Expense Request", branch_request, "linked_purchase_invoice")
            if linked_pi == doc.name:
                frappe.db.set_value("Branch Expense Request", branch_request, "linked_purchase_invoice", None)
                frappe.db.commit()  # Commit immediately
