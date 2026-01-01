from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, now_datetime

from imogi_finance.branching import apply_branch, doc_supports_branch, resolve_branch
from imogi_finance.tax_operations import validate_tax_period_lock


@dataclass
class AccountDetails:
    name: str
    account_type: Optional[str]
    root_type: Optional[str]
    is_group: int
    company: Optional[str]


DEFAULT_APV_SETTINGS = {
    "enforce_branch": 0,
    "enforce_cost_center": 0,
    "allow_target_bank_cash": 0,
    "default_mode_of_payment": None,
    "require_attachment_for_reasons": 0,
    "posting_requires_accounts_manager": 0,
}


def resolve_fiscal_year(posting_date, company: str) -> frappe._dict:
    for path in ("erpnext.accounts.utils.get_fiscal_year", "frappe.utils.get_fiscal_year"):
        try:
            getter = frappe.get_attr(path)
        except Exception:
            continue
        return getter(posting_date, company=company, as_dict=True)

    frappe.throw(_("Unable to resolve fiscal year helper. Please check ERPNext installation."))


def get_apv_settings() -> frappe._dict:
    settings = frappe._dict(DEFAULT_APV_SETTINGS.copy())
    if not getattr(frappe, "db", None):
        return settings

    if not frappe.db.exists("DocType", "Finance Control Settings"):
        return settings

    record = frappe.get_cached_doc("Finance Control Settings")
    if not record:
        return settings

    for key in settings.keys():
        settings[key] = getattr(record, key, settings[key])

    if getattr(record, "require_attachment_for_reasons", 0):
        settings.reason_requirements = {
            row.reason_code: row.requires_attachment for row in getattr(record, "reason_requirements", []) or []
        }
    else:
        settings.reason_requirements = {}

    return settings


def get_account_details(account: str) -> AccountDetails:
    account_type, root_type, is_group, company = frappe.db.get_value(
        "Account", account, ["account_type", "root_type", "is_group", "company"]
    )
    return AccountDetails(
        name=account,
        account_type=account_type,
        root_type=root_type,
        is_group=is_group or 0,
        company=company,
    )


def validate_bank_cash(details: AccountDetails, company: str) -> None:
    if details.is_group:
        frappe.throw(_("Bank/Cash account {0} cannot be a group.").format(details.name))

    if details.company and details.company != company:
        frappe.throw(
            _("Bank/Cash account {0} must belong to company {1}.").format(details.name, company)
        )

    bank_like = (details.account_type or "").lower() in {"bank", "cash"}
    asset_like = (details.root_type or "").lower() in {"asset"}
    if not bank_like and not asset_like:
        frappe.throw(
            _("Bank/Cash account {0} must have Account Type Bank/Cash or an Asset root type.").format(
                details.name
            )
        )


def validate_target_account(details: AccountDetails, company: str) -> None:
    if details.is_group:
        frappe.throw(_("Target account {0} cannot be a group.").format(details.name))

    if details.company and details.company != company:
        frappe.throw(
            _("Target account {0} must belong to company {1}.").format(details.name, company)
        )


def party_required(details: AccountDetails) -> bool:
    return (details.account_type or "").lower() in {"receivable", "payable"}


def validate_party(details: AccountDetails, party_type: Optional[str], party: Optional[str]) -> None:
    if not party_required(details):
        return

    if not party_type or not party:
        frappe.throw(_("Party Type and Party are required when the target account is Receivable/Payable."))


def map_payment_entry_accounts(direction: str, amount: float, bank_account: str, target_account: str) -> frappe._dict:
    direction_normalized = (direction or "").strip().lower()
    if direction_normalized not in {"receive", "pay"}:
        frappe.throw(_("Direction must be Receive or Pay."))

    if amount <= 0:
        frappe.throw(_("Amount must be greater than zero."))

    if direction_normalized == "receive":
        return frappe._dict(
            payment_type="Receive",
            paid_from=target_account,
            paid_to=bank_account,
            paid_amount=amount,
            received_amount=amount,
        )

    return frappe._dict(
        payment_type="Pay",
        paid_from=bank_account,
        paid_to=target_account,
        paid_amount=amount,
        received_amount=amount,
    )


def apply_optional_dimension(doc: Document, fieldname: str, value: Optional[str]) -> None:
    if not value or not frappe.db.has_column(doc.doctype, fieldname):
        return

    setattr(doc, fieldname, value)


class AdministrativePaymentVoucher(Document):
    def validate(self):
        self._ensure_status_defaults()
        self.sync_status_with_workflow_state()
        self._apply_branch_defaults()
        self._apply_settings_defaults()
        self._apply_reason_attachment_policy()
        validate_tax_period_lock(self)
        self._validate_fiscal_year()
        self._validate_amount()
        self._validate_accounts()
        self._validate_party_rules()
        self._validate_party_alignment()
        self._validate_reference_fields()
        self._validate_attachments()
        self._validate_workflow_action_guard()
        self._prevent_edits_after_approval()

    def before_submit(self):
        # Submission should only happen through the Post transition.
        self._allow_workflow_action()
        self._assert_can_post()

    def on_submit(self):
        # Persist posting metadata if workflow already set them in on_workflow_action.
        self._set_posting_audit()
        self.sync_status_with_workflow_state()
        self.db_set("status", self.status)

    def on_cancel(self):
        self._attempt_cancel_payment_entry()
        self.status = "Cancelled"
        self.workflow_state = "Cancelled"
        self.db_set({"status": "Cancelled", "workflow_state": "Cancelled"})
        self._add_timeline_comment(_("Cancelled Administrative Payment Voucher and attempted to cancel Payment Entry."))

    @frappe.whitelist()
    def create_payment_entry_from_client(self):
        self._assert_payment_entry_context(from_client=True)

        payment_entry = self.create_payment_entry()
        return {"payment_entry": getattr(payment_entry, "name", None)}

    def create_payment_entry(self):
        self._assert_payment_entry_context()

        if self.payment_entry:
            existing_status = frappe.db.get_value("Payment Entry", self.payment_entry, "docstatus")
            if existing_status is not None and existing_status != 2:
                frappe.msgprint(
                    _("Payment Entry {0} already exists for this voucher.").format(self.payment_entry)
                )
                return frappe.get_doc("Payment Entry", self.payment_entry)

        bank_details = self._get_account(self.bank_cash_account)
        target_details = self._get_account(self.target_gl_account)
        account_map = map_payment_entry_accounts(
            self.direction, self.amount, bank_details.name, target_details.name
        )

        payment_entry = frappe.new_doc("Payment Entry")
        payment_entry.payment_type = account_map.payment_type
        payment_entry.company = self.company
        payment_entry.posting_date = self.posting_date
        payment_entry.paid_from = account_map.paid_from
        payment_entry.paid_to = account_map.paid_to
        payment_entry.paid_amount = account_map.paid_amount
        payment_entry.received_amount = account_map.received_amount
        payment_entry.mode_of_payment = self.mode_of_payment
        payment_entry.reference_no = self.name
        payment_entry.reference_date = self.posting_date
        payment_entry.remarks = self._build_remarks()

        if party_required(target_details):
            payment_entry.party_type = self.party_type
            payment_entry.party = self.party
            if hasattr(payment_entry, "party_account"):
                payment_entry.party_account = target_details.name

        apply_optional_dimension(payment_entry, "cost_center", self.cost_center)

        branch = getattr(self, "branch", None)
        if doc_supports_branch(payment_entry.doctype):
            apply_branch(payment_entry, branch)
        elif branch and frappe.db.has_column(payment_entry.doctype, "branch"):
            apply_optional_dimension(payment_entry, "branch", branch)

        if self.reference_doctype and self.reference_name:
            payment_entry.append(
                "references",
                {
                    "reference_doctype": self.reference_doctype,
                    "reference_name": self.reference_name,
                    "allocated_amount": self.amount,
                    "cost_center": self.cost_center,
                },
            )

        if hasattr(payment_entry, "imogi_administrative_payment_voucher"):
            payment_entry.imogi_administrative_payment_voucher = self.name

        if hasattr(payment_entry, "set_missing_values"):
            payment_entry.set_missing_values()

        payment_entry.insert(ignore_permissions=True)
        payment_entry.submit()
        self._add_timeline_comment(
            _("Payment Entry {0} created from Administrative Payment Voucher").format(payment_entry.name),
            reference_doctype="Payment Entry",
            reference_name=payment_entry.name,
        )
        return payment_entry

    def _build_remarks(self) -> str:
        parts = [(_("Administrative Payment Voucher {0}").format(self.name))]
        if self.justification:
            parts.append(self.justification)
        if self.reference_doctype and self.reference_name:
            parts.append(_("Reference: {0} {1}").format(self.reference_doctype, self.reference_name))
        return " | ".join(parts)

    def _validate_amount(self):
        if not self.amount or self.amount <= 0:
            frappe.throw(_("Amount must be greater than zero."))

    def _validate_accounts(self):
        bank_details = self._get_account(self.bank_cash_account)
        target_details = self._get_account(self.target_gl_account)

        validate_bank_cash(bank_details, self.company)
        settings = get_apv_settings()
        if not settings.allow_target_bank_cash:
            validate_target_account(target_details, self.company)
        else:
            if target_details.is_group:
                frappe.throw(_("Target account {0} cannot be a group.").format(target_details.name))

    def _validate_party_rules(self):
        target_details = self._get_account(self.target_gl_account)
        validate_party(target_details, self.party_type, self.party)

    def _validate_reference_fields(self):
        if self.reference_name and not self.reference_doctype:
            frappe.throw(_("Please choose a Reference Doctype when Reference Name is set."))
        if self.reference_doctype and not self.reference_name:
            frappe.throw(_("Please choose a Reference Name when Reference Doctype is set."))

    def _validate_attachments(self):
        if not getattr(self, "require_attachment", 0):
            return

        attachments = self.get("_attachments") or []
        if not attachments and self.name:
            attachments = frappe.get_all(
                "File",
                filters={"attached_to_doctype": self.doctype, "attached_to_name": self.name},
                limit=1,
            )
        if attachments:
            return
        frappe.throw(_("An attachment is required for this Administrative Payment Voucher."))

    def _validate_fiscal_year(self):
        if not self.posting_date:
            return

        posting = getdate(self.posting_date)
        try:
            fiscal_year = resolve_fiscal_year(posting, company=self.company)
        except Exception:
            fiscal_year = None
        if fiscal_year:
            from_date = getdate(fiscal_year.get("year_start_date"))
            to_date = getdate(fiscal_year.get("year_end_date"))
            if posting < from_date or posting > to_date:
                frappe.throw(
                    _("Posting Date must fall within the Fiscal Year ({0} to {1}).").format(
                        from_date, to_date
                    ),
                    title=_("Invalid Posting Date"),
                )

    def _ensure_status_defaults(self):
        if self.docstatus == 0 and not self.status:
            self.status = "Draft"
        if self.docstatus == 2:
            self.status = "Cancelled"
        if not self.workflow_state:
            self.workflow_state = self.status or "Draft"

    def _apply_branch_defaults(self):
        branch = resolve_branch(
            company=getattr(self, "company", None),
            cost_center=getattr(self, "cost_center", None),
            explicit_branch=getattr(self, "branch", None),
        )
        if branch:
            apply_branch(self, branch)

    def _apply_settings_defaults(self):
        settings = get_apv_settings()
        if settings.default_mode_of_payment and not self.mode_of_payment:
            self.mode_of_payment = settings.default_mode_of_payment

        if settings.enforce_branch and not self.branch:
            frappe.throw(_("Branch is required for Administrative Payment Voucher."))

        if settings.enforce_cost_center and not self.cost_center:
            frappe.throw(_("Cost Center is required for Administrative Payment Voucher."))

    def _validate_party_alignment(self):
        if not self.party_type or not self.party:
            return

        doctype_map = {
            "Customer": "Customer",
            "Supplier": "Supplier",
            "Employee": "Employee",
        }
        expected_doctype = doctype_map.get(self.party_type)
        if not expected_doctype:
            return

        if not frappe.db.exists(expected_doctype, self.party):
            frappe.throw(
                _("Party {0} does not match Party Type {1}.").format(self.party, self.party_type),
                title=_("Invalid Party"),
            )

    def _validate_workflow_action_guard(self):
        flags_obj = getattr(self, "flags", None)
        if flags_obj and getattr(flags_obj, "workflow_action_allowed", False):
            return

        flags = getattr(frappe, "flags", None)
        if getattr(flags, "in_patch", False) or getattr(flags, "in_install", False):
            return

        previous = self._get_previous_doc()
        if not previous or getattr(previous, "docstatus", None) != getattr(self, "docstatus", None):
            return

        if getattr(previous, "status", None) == getattr(self, "status", None):
            return

        frappe.throw(_("Status changes must be performed via workflow actions."), title=_("Not Allowed"))

    def _prevent_edits_after_approval(self):
        previous = self._get_previous_doc()
        if not previous:
            return

        immutable_states = {"Approved", "Posted"}
        if previous.docstatus == 1 or previous.status in immutable_states or previous.workflow_state in immutable_states:
            flags_obj = getattr(self, "flags", None)
            if flags_obj and getattr(flags_obj, "workflow_action_allowed", False):
                return

            changed_fields = self._get_changed_fields(previous)
            if changed_fields:
                frappe.throw(
                    _("Edits are locked after approval/posting. Changed fields: {0}.").format(
                        ", ".join(sorted(changed_fields))
                    ),
                    title=_("Not Allowed"),
                )

    def _get_changed_fields(self, previous: Document) -> set[str]:
        changed: set[str] = set()
        ignore_fields = {
            "modified",
            "modified_by",
            "status",
            "workflow_state",
            "_comments",
            "_assign",
            "_liked_by",
        }
        for field in self.meta.get_valid_columns():
            if field in ignore_fields:
                continue
            if getattr(self, field, None) != getattr(previous, field, None):
                changed.add(field)
        return changed

    def _apply_reason_attachment_policy(self):
        settings = get_apv_settings()
        if not settings.require_attachment_for_reasons:
            return

        reason_rules = settings.get("reason_requirements") or {}
        if not reason_rules:
            return

        if self.reason_code and reason_rules.get(self.reason_code):
            self.require_attachment = 1

    def before_workflow_action(self, action, **kwargs):
        self._allow_workflow_action()
        if action == "Submit for Approval":
            if frappe.session.user != self.owner:
                frappe.throw(_("Only the creator can submit this voucher for approval."))
            self._apply_reason_attachment_policy()
        if action == "Approve":
            self._set_approval_audit()
        if action == "Post":
            self._assert_can_post()
            self._allow_workflow_action(allow_payment_entry=True)
        if action == "Cancel":
            self._assert_can_cancel()

    def on_workflow_action(self, action, **kwargs):
        next_state = kwargs.get("next_state") or getattr(self, "workflow_state", None)
        self.sync_status_with_workflow_state(target_state=next_state)
        if action == "Approve":
            self._add_timeline_comment(_("Approved Administrative Payment Voucher."))
        if action == "Post":
            payment_entry = self.create_payment_entry()
            if payment_entry:
                self.payment_entry = payment_entry.name
                self.posted_by = frappe.session.user
                self.posted_on = now_datetime()
                self.db_set(
                    {
                        "payment_entry": payment_entry.name,
                        "posted_by": self.posted_by,
                        "posted_on": self.posted_on,
                    }
                )
                self._add_timeline_comment(
                    _("Posted Administrative Payment Voucher and created Payment Entry {0}.").format(
                        payment_entry.name
                    ),
                    reference_doctype="Payment Entry",
                    reference_name=payment_entry.name,
                )
        if action == "Cancel":
            self._attempt_cancel_payment_entry()

    def sync_status_with_workflow_state(self, *, target_state: Optional[str] = None):
        workflow_state = target_state or getattr(self, "workflow_state", None)
        if not workflow_state:
            return

        valid_states = {"Draft", "Pending Approval", "Approved", "Posted", "Rejected", "Cancelled"}
        if workflow_state not in valid_states:
            return

        if self.status == workflow_state:
            return

        self.status = workflow_state
        self.workflow_state = workflow_state
        self._allow_workflow_action()

    def _assert_payment_entry_context(self, *, from_client: bool = False):
        if from_client and self.docstatus != 1:
            frappe.throw(_("Please submit the Administrative Payment Voucher before posting a Payment Entry."))

        if self.workflow_state not in {"Approved", "Posted"}:
            frappe.throw(
                _("Payment Entry can only be created when the voucher is Approved."),
                title=_("Not Allowed"),
            )

        settings = get_apv_settings()
        if settings.posting_requires_accounts_manager and "Accounts Manager" not in frappe.get_roles():
            frappe.throw(_("Only Accounts Managers can post Administrative Payment Vouchers."))

    def _assert_can_post(self):
        if self.workflow_state not in {"Approved", "Posted"} and self.status not in {"Approved", "Posted"}:
            frappe.throw(_("Voucher must be Approved before posting."))
        settings = get_apv_settings()
        if settings.posting_requires_accounts_manager and "Accounts Manager" not in frappe.get_roles():
            frappe.throw(_("Only Accounts Managers can post Administrative Payment Vouchers."))

    def _assert_can_cancel(self):
        if "Accounts Manager" not in frappe.get_roles():
            frappe.throw(_("Only Accounts Managers can cancel a posted Administrative Payment Voucher."))

    def _allow_workflow_action(self, *, allow_payment_entry: bool = False):
        flags = getattr(self, "flags", None)
        if flags is None:
            flags = type("Flags", (), {})()
            self.flags = flags
        self.flags.workflow_action_allowed = True
        if allow_payment_entry:
            self.flags.allow_payment_entry = True

    def _set_approval_audit(self):
        self.approved_by = frappe.session.user
        self.approved_on = now_datetime()

    def _set_posting_audit(self):
        if not self.posted_by:
            self.posted_by = frappe.session.user
        if not self.posted_on:
            self.posted_on = now_datetime()

    def _attempt_cancel_payment_entry(self):
        if not self.payment_entry or not frappe.db.exists("Payment Entry", self.payment_entry):
            return

        payment_entry = frappe.get_doc("Payment Entry", self.payment_entry)
        if payment_entry.docstatus == 2:
            return

        if payment_entry.docstatus == 0:
            payment_entry.delete()
            return

        try:
            payment_entry.cancel()
            self._add_timeline_comment(
                _("Cancelled linked Payment Entry {0}.").format(payment_entry.name),
                reference_doctype="Payment Entry",
                reference_name=payment_entry.name,
            )
        except Exception as exc:
            frappe.throw(
                _("Unable to cancel Payment Entry {0}. Please unreconcile or close references first. Error: {1}").format(
                    payment_entry.name, frappe.utils.cstr(exc)
                )
            )

    def _get_account(self, account: str) -> AccountDetails:
        if not account:
            frappe.throw(_("Please set an account."))

        if not hasattr(self, "_account_cache"):
            self._account_cache = {}

        if account not in self._account_cache:
            self._account_cache[account] = get_account_details(account)

        return self._account_cache[account]

    def _get_previous_doc(self):
        previous = getattr(self, "_doc_before_save", None)
        if not previous and hasattr(self, "get_doc_before_save"):
            try:
                previous = self.get_doc_before_save()
            except Exception:
                previous = None

        return previous

    def get_indicator(self):
        state = getattr(self, "workflow_state", None) or self.status
        colors = {
            "Draft": "gray",
            "Pending Approval": "blue",
            "Approved": "green",
            "Posted": "green",
            "Rejected": "red",
            "Cancelled": "red",
        }
        return (state, colors.get(state, "gray"), "")

    def _add_timeline_comment(self, content: str, *, reference_doctype: Optional[str] = None, reference_name=None):
        try:
            self.add_comment(
                "Info",
                content,
                reference_doctype=reference_doctype,
                reference_name=reference_name,
            )
        except Exception:
            pass
