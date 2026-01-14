import frappe
from frappe import _

from imogi_finance.branching import get_branch_settings, validate_branch_alignment
from imogi_finance.events.utils import (
    get_approved_expense_request,
    get_cancel_updates,
    get_expense_request_links,
    get_expense_request_status,
)


@frappe.whitelist()
def manual_create_assets_from_expense_request(expense_request_name: str):
    """Manual trigger to create assets from Expense Request.
    
    Use this if assets were not auto-created when Payment Entry was submitted.
    """
    request = frappe.get_doc("Expense Request", expense_request_name)
    
    if request.request_type != "Asset":
        frappe.throw(_("This is not an Asset type request"))
    
    if not request.linked_purchase_invoice:
        frappe.throw(_("No Purchase Invoice linked to this request"))
    
    # Check if Payment Entry exists and is submitted
    pi_name = request.linked_purchase_invoice
    pi = frappe.get_doc("Purchase Invoice", pi_name)
    
    if pi.outstanding_amount > 0:
        frappe.throw(_("Purchase Invoice has not been fully paid yet. Outstanding: {0}").format(pi.outstanding_amount))
    
    # Trigger asset creation
    _auto_create_assets_from_expense_request(request)
    
    return {"success": True, "message": "Assets created successfully"}


def _auto_create_assets_from_expense_request(request):
    """Auto-create Asset documents from paid Expense Request.
    
    Called when Payment Entry is submitted for Asset type requests.
    Creates individual Asset documents based on asset_items and qty.
    Only creates if no SUBMITTED assets exist for this request.
    """
    if request.request_type != "Asset":
        return
    
    # Check if SUBMITTED assets already exist (not just asset_links entries)
    # This allows re-creation if previous assets were cancelled
    if request.get("asset_links"):
        submitted_assets = []
        for asset_link in request.asset_links:
            asset_status = frappe.db.get_value("Asset", asset_link.asset, "docstatus")
            if asset_status == 1:  # Submitted
                submitted_assets.append(asset_link.asset)
        
        if submitted_assets:
            frappe.logger().info(
                f"{len(submitted_assets)} submitted asset(s) already exist for ER {request.name}, skipping auto-create"
            )
            frappe.msgprint(
                _("{0} asset(s) already exist for this Expense Request").format(len(submitted_assets)),
                alert=True,
                indicator="blue"
            )
            return
    
    if not request.linked_purchase_invoice:
        frappe.logger().warning(f"No Purchase Invoice linked to ER {request.name}, skipping asset creation")
        return
    
    asset_items = request.get("asset_items") or []
    if not asset_items:
        frappe.logger().warning(f"No asset items found in ER {request.name}")
        return
    
    # Get company from cost center
    company = frappe.db.get_value("Cost Center", request.cost_center, "company")
    
    created_assets = []
    
    # Check if this is a re-creation (previous assets were cancelled)
    is_recreation = request.get("asset_links") and len(request.asset_links) > 0
    
    for item in asset_items:
        try:
            qty = int(item.qty or 1)
            unit_amount = item.amount / qty if qty > 0 else item.amount
            
            for i in range(qty):
                # Create Asset
                asset = frappe.new_doc("Asset")
                
                # Basic info - add suffix for re-creation to avoid duplicate names
                base_name = item.asset_name
                if qty > 1:
                    asset_name = f"{base_name} #{i+1}"
                else:
                    asset_name = base_name
                
                # If re-creating (after cancel), add timestamp to avoid duplicates
                if is_recreation:
                    from datetime import datetime
                    timestamp = datetime.now().strftime("%H%M%S")
                    asset_name = f"{asset_name} (R{timestamp})"
                
                asset.asset_name = asset_name
                asset.asset_category = item.asset_category
                asset.is_existing_asset = 1  # Bypass item_code validation
                asset.company = company
                asset.location = item.asset_location
                
                # Financial details
                asset.gross_purchase_amount = unit_amount
                asset.purchase_date = request.request_date
                
                # Don't set purchase_invoice - ERPNext validation blocks multiple assets per PI for existing assets
                # Instead, track via custom field only
                # asset.purchase_invoice = request.linked_purchase_invoice
                
                # Link to Expense Request (custom field) - this is the primary tracking
                asset.imogi_expense_request = request.name
                
                # Save and submit (submit will trigger asset.on_submit which links back to ER)
                asset.insert(ignore_permissions=True)
                asset.submit()
                
                created_assets.append(asset.name)
                
                frappe.logger().info(f"Created Asset {asset.name} for ER {request.name}")
                
        except Exception as e:
            # Log error but don't block Payment Entry submission
            frappe.log_error(
                title=f"Asset Auto-Creation Error - {request.name}",
                message=f"Item: {item.asset_name}\nError: {str(e)}"
            )
            frappe.msgprint(
                _("Warning: Failed to create asset {0}: {1}").format(item.asset_name, str(e)),
                alert=True,
                indicator="orange"
            )
    
    if created_assets:
        frappe.msgprint(
            _("Successfully created {0} asset(s) for Expense Request {1}").format(
                len(created_assets), request.name
            ),
            alert=True,
            indicator="green"
        )
    
    frappe.db.commit()


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
    
    # Auto-create assets for Asset type requests
    if request.request_type == "Asset":
        _auto_create_assets_from_expense_request(request)


def on_cancel(doc, method=None):
    """Handle Payment Entry cancellation.
    
    When PE is cancelled:
    1. Clear linked_payment_entry from Expense Request
    2. Update status back to "PI Created" (or "Approved" if no PI)
    3. DO NOT cancel Assets (they're already submitted and may be in use)
    4. Assets remain linked in asset_links table for audit trail
    """
    request_name = _resolve_expense_request(doc)
    if not request_name:
        frappe.logger().info(f"[Payment Entry on_cancel] No ER linked to PE {doc.name}")
        return

    # Get cancel updates (clears linked_payment_entry and updates status)
    updates = get_cancel_updates(request_name, "linked_payment_entry")
    
    frappe.logger().info(f"[Payment Entry on_cancel] PE {doc.name} cancelled, updating ER {request_name}")
    frappe.logger().info(f"[Payment Entry on_cancel] New status: {updates.get('status')}")
    
    # Log info about linked assets (for audit)
    request_doc = frappe.get_doc("Expense Request", request_name)
    if request_doc.request_type == "Asset" and request_doc.get("asset_links"):
        asset_count = len(request_doc.asset_links)
        frappe.logger().info(
            f"[Payment Entry on_cancel] ER {request_name} has {asset_count} linked assets (not cancelled)"
        )
        frappe.msgprint(
            _("Note: {0} linked asset(s) remain active. Cancel them separately if needed.").format(asset_count),
            alert=True,
            indicator="blue"
        )

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
