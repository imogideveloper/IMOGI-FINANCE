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

    # Validate linked_purchase_invoice matches this PI
    if request.linked_purchase_invoice and request.linked_purchase_invoice != doc.name:
        frappe.throw(
            _("Expense Request is already linked to a different Purchase Invoice {0}.").format(
                request.linked_purchase_invoice
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

    # Update status to PI Created now that PI is submitted
    frappe.db.set_value(
        "Expense Request",
        request.name,
        {"status": "PI Created", "workflow_state": "PI Created", "pending_purchase_invoice": None},
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


def on_cancel(doc, method=None):
    """Handle Purchase Invoice cancellation.
    
    When PI is cancelled:
    1. Check for active Payment Entry (must be cancelled first)
    2. Reverse budget consumption
    3. Clear linked_purchase_invoice from Request
    4. Update status appropriately
    """
    expense_request_name = doc.get("imogi_expense_request")
    branch_request_name = doc.get("branch_expense_request")
    
    # Check for active Payment Entry
    if expense_request_name:
        pe = frappe.db.get_value("Expense Request", expense_request_name, "linked_payment_entry")
        if pe and frappe.db.get_value("Payment Entry", pe, "docstatus") == 1:
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
    
    # Update Expense Request status
    if expense_request_name:
        updates = get_cancel_updates(expense_request_name, "linked_purchase_invoice")
        updates["pending_purchase_invoice"] = None
        frappe.db.set_value("Expense Request", expense_request_name, updates)
    
    # Update Branch Expense Request
    if branch_request_name:
        if frappe.db.exists("Branch Expense Request", branch_request_name):
            frappe.db.set_value("Branch Expense Request", branch_request_name, "linked_purchase_invoice", None)



def on_trash(doc, method=None):
    expense_request = doc.get("imogi_expense_request")
    branch_request = doc.get("branch_expense_request")
    
    # Handle Expense Request
    if expense_request:
        request_links = get_expense_request_links(expense_request, include_pending=True)
        updates = {}
        if request_links.get("pending_purchase_invoice") == doc.name:
            updates["pending_purchase_invoice"] = None
        if request_links.get("linked_purchase_invoice") == doc.name:
            updates["linked_purchase_invoice"] = None

        if updates:
            remaining_links = dict(request_links)
            for field in updates:
                remaining_links[field] = None
            next_status = get_expense_request_status(remaining_links)
            updates["status"] = next_status
            updates["workflow_state"] = next_status
            frappe.db.set_value("Expense Request", expense_request, updates)
    
    # Handle Branch Expense Request
    if branch_request:
        if frappe.db.exists("Branch Expense Request", branch_request):
            linked_pi = frappe.db.get_value("Branch Expense Request", branch_request, "linked_purchase_invoice")
            if linked_pi == doc.name:
                frappe.db.set_value("Branch Expense Request", branch_request, "linked_purchase_invoice", None)
