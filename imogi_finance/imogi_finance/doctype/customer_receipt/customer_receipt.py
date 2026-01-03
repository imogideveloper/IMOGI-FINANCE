from __future__ import annotations

from decimal import Decimal
from typing import Dict, Iterable, List, Optional

import frappe
from frappe import _
from frappe.model.document import Document

from imogi_finance.branching import (
    apply_branch,
    doc_supports_branch,
    get_branch_settings,
    resolve_branch,
    validate_branch_alignment,
)
from imogi_finance.receipt_control.utils import get_receipt_control_settings, record_stamp_cost


class CustomerReceipt(Document):
    STATUS_FINALIZED = {"Issued", "Partially Paid", "Paid"}

    def validate(self):
        self.apply_defaults()
        self.validate_items()
        self.compute_totals()
        self.enforce_item_lock()
        self.apply_stamp_policy()

    def on_submit(self):
        self.status = "Issued"
        self.compute_totals()
        self.db_set("status", self.status)

    def before_cancel(self):
        active_payments = [row.payment_entry for row in self.get("payments") or []]
        if active_payments:
            submitted = frappe.get_all(
                "Payment Entry", filters={"name": ("in", active_payments), "docstatus": 1}, pluck="name"
            )
            if submitted:
                frappe.throw(
                    _("Cannot cancel because Payment Entry {0} is linked.").format(", ".join(submitted))
                )

    def on_cancel(self):
        self.status = "Cancelled"
        self.db_set("status", self.status)

    def apply_defaults(self):
        settings = get_receipt_control_settings()
        if not self.receipt_design and settings.default_receipt_design:
            self.receipt_design = settings.default_receipt_design
        if not self.posting_date:
            self.posting_date = frappe.utils.today()
        branch = resolve_branch(
            company=self.company,
            explicit_branch=getattr(self, "branch", None),
        )
        if branch:
            apply_branch(self, branch)

    def enforce_item_lock(self):
        previous = getattr(self, "_doc_before_save", None) or self.get_doc_before_save()
        if not previous or previous.docstatus != 1 or previous.status not in self.STATUS_FINALIZED:
            return
        if self.has_item_changes(previous):
            frappe.throw(_("Items cannot be changed after the receipt is issued."))

    def has_item_changes(self, previous: Document) -> bool:
        current_items = [(row.sales_order, row.sales_invoice, row.amount_to_collect) for row in self.get("items") or []]
        previous_items = [
            (row.sales_order, row.sales_invoice, row.amount_to_collect)
            for row in (previous.get("items") or [])
        ]
        return current_items != previous_items

    def validate_items(self):
        if not self.get("items"):
            frappe.throw(_("Please add at least one receipt item."))

        allowed_doctype = self.allowed_reference_doctype
        branch_settings = get_branch_settings()
        for row in self.get("items"):
            reference = row.sales_invoice if allowed_doctype == "Sales Invoice" else row.sales_order
            if not reference:
                frappe.throw(_("Receipt items must have a reference document."))

            self.set_reference_meta(row, allowed_doctype, reference, branch_settings=branch_settings)

            if row.amount_to_collect and row.reference_outstanding and row.amount_to_collect > row.reference_outstanding:
                frappe.throw(
                    _("Amount to collect for {0} cannot exceed outstanding {1}.").format(
                        reference, frappe.utils.fmt_money(row.reference_outstanding)
                    )
                )

    def set_reference_meta(self, row, allowed_doctype: str, reference: str, *, branch_settings=None):
        fields = ["customer", "company", "docstatus"]
        branch_field = "branch" if doc_supports_branch(allowed_doctype) else None
        if branch_field:
            fields.append(branch_field)
        if allowed_doctype == "Sales Invoice":
            fields.append("outstanding_amount")
            fields.append("posting_date")
        else:
            fields.append("advance_paid")
            fields.append("grand_total")
            fields.append("transaction_date")

        values = frappe.db.get_value(allowed_doctype, reference, fields, as_dict=True)
        if not values:
            frappe.throw(_("{0} {1} not found.").format(allowed_doctype, reference))

        if values.docstatus != 1:
            frappe.throw(_("{0} {1} must be submitted before linking.").format(allowed_doctype, reference))

        if values.customer != self.customer:
            frappe.throw(
                _("{0} {1} belongs to a different customer {2}.").format(allowed_doctype, reference, values.customer)
            )
        if values.company != self.company:
            frappe.throw(
                _("{0} {1} belongs to a different company {2}.").format(allowed_doctype, reference, values.company)
            )

        if branch_field and branch_settings and branch_settings.enable_multi_branch and branch_settings.enforce_branch_on_links:
            validate_branch_alignment(
                values.get(branch_field),
                getattr(self, "branch", None),
                label=_("{0} {1}").format(allowed_doctype, reference),
            )

        if allowed_doctype == "Sales Invoice":
            row.reference_outstanding = values.outstanding_amount
            row.reference_date = values.posting_date
        else:
            outstanding = (values.grand_total or 0) - (values.advance_paid or 0)
            row.reference_outstanding = outstanding
            row.reference_date = values.transaction_date

    @property
    def allowed_reference_doctype(self) -> str:
        return "Sales Invoice" if self.receipt_purpose == "Billing (Sales Invoice)" else "Sales Order"

    def compute_totals(self):
        total = sum([Decimal(row.amount_to_collect or 0) for row in self.get("items") or []])
        paid = sum([Decimal(row.paid_amount or 0) for row in self.get("payments") or []])
        outstanding = total - paid
        if outstanding < 0:
            outstanding = Decimal("0")

        self.total_amount = float(total)
        self.paid_amount = float(paid)
        self.outstanding_amount = float(outstanding)

        if self.docstatus == 1:
            if outstanding == 0:
                self.status = "Paid"
            elif paid > 0:
                self.status = "Partially Paid"
            else:
                self.status = "Issued"

    def recompute_payment_state(self):
        self.compute_totals()
        if self.docstatus == 1:
            self.db_set({
                "paid_amount": self.paid_amount,
                "outstanding_amount": self.outstanding_amount,
                "status": self.status,
            })

    def apply_stamp_policy(self):
        settings = get_receipt_control_settings()
        requires_digital = False
        if settings.enable_digital_stamp:
            if settings.digital_stamp_policy == "Mandatory Always":
                requires_digital = True
            elif (
                settings.digital_stamp_policy == "Mandatory by Threshold"
                and (self.total_amount or 0) >= (settings.digital_stamp_threshold_amount or 0)
            ):
                requires_digital = True

        if requires_digital:
            self.stamp_mode = "Digital"
        elif not self.stamp_mode:
            self.stamp_mode = "Physical" if settings.allow_physical_stamp_fallback else "None"

        stamp_issued = self.stamp_mode == "Digital" and self.digital_stamp_status == "Issued"
        if stamp_issued and requires_digital and not self._has_stamp_cost_reference():
            stamp_cost = getattr(settings, "digital_stamp_cost", None) or 10000
            payment_reference = record_stamp_cost(self.name, stamp_cost)
            self._update_stamp_log_with_cost(stamp_cost, payment_reference)

        if stamp_issued:
            self.digital_stamp_locked = 1

    def _has_stamp_cost_reference(self) -> bool:
        return any([row.payment_reference for row in (self.get("digital_stamp_logs") or [])])

    def _update_stamp_log_with_cost(self, stamp_cost: float, payment_reference: str):
        target_log = None
        for row in self.get("digital_stamp_logs") or []:
            if (row.action or "").lower() == "issued" and not row.payment_reference:
                target_log = row
                break

        if not target_log and self.get("digital_stamp_logs"):
            target_log = self.digital_stamp_logs[-1]

        if not target_log:
            target_log = self.append(
                "digital_stamp_logs",
                {
                    "action": "Issued",
                    "timestamp": frappe.utils.now_datetime(),
                    "user": frappe.session.user,
                },
            )
        else:
            target_log.timestamp = target_log.timestamp or frappe.utils.now_datetime()

        target_log.stamp_cost = stamp_cost
        target_log.payment_reference = payment_reference
        target_log.payment_reference_doctype = "Journal Entry"

    def get_reference_availability(self) -> Dict[str, Decimal]:
        consumption = self._get_reference_consumption()
        availability: Dict[str, Decimal] = {}
        for row in self.get("items") or []:
            ref = row.sales_invoice if self.allowed_reference_doctype == "Sales Invoice" else row.sales_order
            availability[ref] = Decimal(row.amount_to_collect or 0) - consumption.get(ref, Decimal("0"))
        return availability

    def _get_reference_consumption(self) -> Dict[str, Decimal]:
        payment_entries = frappe.get_all(
            "Payment Entry",
            filters={"customer_receipt": self.name, "docstatus": 1},
            pluck="name",
        )
        if not payment_entries:
            return {}

        rows = frappe.get_all(
            "Payment Entry Reference",
            fields=["reference_name", "sum(allocated_amount) as allocated_amount"],
            filters={
                "docstatus": 1,
                "parentfield": "references",
                "parenttype": "Payment Entry",
                "parent": ("in", payment_entries),
            },
            group_by="reference_name",
        )
        return {row.reference_name: Decimal(row.allocated_amount or 0) for row in rows}

    @frappe.whitelist()
    def make_payment_entry(self, paid_amount: Optional[float] = None):
        paid_amount = Decimal(paid_amount or self.outstanding_amount or 0)
        if paid_amount <= 0:
            frappe.throw(_("Paid amount must be greater than zero."))

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = self.customer
        pe.company = self.company
        pe.posting_date = frappe.utils.getdate()
        pe.customer_receipt = self.name
        pe.received_amount = float(paid_amount)
        pe.paid_amount = float(paid_amount)
        branch = resolve_branch(
            company=self.company,
            explicit_branch=getattr(self, "branch", None),
        )
        if branch:
            apply_branch(pe, branch)

        availability = self.get_reference_availability()
        remaining = paid_amount
        for row in self.get("items") or []:
            ref = row.sales_invoice if self.allowed_reference_doctype == "Sales Invoice" else row.sales_order
            available = availability.get(ref, Decimal("0"))
            if remaining <= 0 or available <= 0:
                continue
            allocation = min(available, remaining)
            pe.append(
                "references",
                {
                    "reference_doctype": self.allowed_reference_doctype,
                    "reference_name": ref,
                    "allocated_amount": float(allocation),
                },
            )
            remaining -= allocation

        return pe.insert(ignore_permissions=True)
