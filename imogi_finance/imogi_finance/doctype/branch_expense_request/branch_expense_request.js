frappe.provide("imogi_finance");
frappe.require("/assets/imogi_finance/js/tax_invoice_fields.js");

const TAX_INVOICE_MODULE = imogi_finance?.tax_invoice || {};
const DEFAULT_COPY_KEYS = [
	"fp_no",
	"fp_date",
	"npwp",
	"dpp",
	"ppn",
	"ppnbm",
	"ppn_type",
	"status",
	"notes",
	"duplicate_flag",
	"npwp_match",
];
const DEFAULT_BER_FIELDS = {
	fp_no: "ti_fp_no",
	fp_date: "ti_fp_date",
	npwp: "ti_fp_npwp",
	dpp: "ti_fp_dpp",
	ppn: "ti_fp_ppn",
	ppnbm: "ti_fp_ppnbm",
	ppn_type: "ti_fp_ppn_type",
	status: "ti_verification_status",
	notes: "ti_verification_notes",
	duplicate_flag: "ti_duplicate_flag",
	npwp_match: "ti_npwp_match",
	ocr_status: "ti_ocr_status",
	ocr_confidence: "ti_ocr_confidence",
	ocr_raw_json: "ti_ocr_raw_json",
	tax_invoice_pdf: "ti_tax_invoice_pdf",
};
const DEFAULT_UPLOAD_FIELDS = {
	fp_no: "fp_no",
	fp_date: "fp_date",
	npwp: "npwp",
	dpp: "dpp",
	ppn: "ppn",
	ppnbm: "ppnbm",
	ppn_type: "ppn_type",
	status: "verification_status",
	notes: "verification_notes",
	duplicate_flag: "duplicate_flag",
	npwp_match: "npwp_match",
	ocr_status: "ocr_status",
	ocr_confidence: "ocr_confidence",
	ocr_raw_json: "ocr_raw_json",
	tax_invoice_pdf: "tax_invoice_pdf",
};

const BER_TAX_INVOICE_FIELDS =
	(TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap("Branch Expense Request")) || DEFAULT_BER_FIELDS;
const UPLOAD_TAX_INVOICE_FIELDS =
	(TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap("Tax Invoice OCR Upload")) || DEFAULT_UPLOAD_FIELDS;
const COPY_KEYS =
	(TAX_INVOICE_MODULE.getSharedCopyKeys &&
		TAX_INVOICE_MODULE.getSharedCopyKeys("Tax Invoice OCR Upload", "Branch Expense Request")) ||
	DEFAULT_COPY_KEYS;

async function syncBerUpload(frm) {
	if (!frm.doc.ti_tax_invoice_upload) {
		return;
	}
	const cachedUpload = frm.taxInvoiceUploadCache?.[frm.doc.ti_tax_invoice_upload];
	const upload = cachedUpload || await frappe.db.get_doc("Tax Invoice OCR Upload", frm.doc.ti_tax_invoice_upload);
	const updates = {};
	COPY_KEYS.forEach((key) => {
		const sourceField = UPLOAD_TAX_INVOICE_FIELDS[key];
		const targetField = BER_TAX_INVOICE_FIELDS[key];
		if (!sourceField || !targetField) {
			return;
		}
		updates[targetField] = upload[sourceField] ?? null;
	});
	await frm.set_value(updates);
}

function lockBerTaxInvoiceFields(frm) {
	Object.values(BER_TAX_INVOICE_FIELDS).forEach((field) => {
		frm.set_df_property(field, "read_only", true);
	});
}

async function setBerUploadQuery(frm) {
	let usedUploads = [];
	let verifiedUploads = [];
	let providerReady = true;
	let providerError = null;

	try {
		const { message } = await frappe.call({
			method: "imogi_finance.api.tax_invoice.get_tax_invoice_upload_context_api",
			args: { target_doctype: "Branch Expense Request", target_name: frm.doc.name },
		});
		usedUploads = message?.used_uploads || [];
		verifiedUploads = message?.verified_uploads || [];
		providerReady = Boolean(message?.provider_ready ?? true);
		providerError = message?.provider_error || null;
	} catch (error) {
		console.error("Unable to load available Tax Invoice uploads", error);
	}

	frm.taxInvoiceProviderReady = providerReady;
	frm.taxInvoiceProviderError = providerError;

	frm.taxInvoiceUploadCache = (verifiedUploads || []).reduce((acc, upload) => {
		acc[upload.name] = upload;
		return acc;
	}, {});

	frm.set_query("ti_tax_invoice_upload", () => ({
		filters: {
			verification_status: "Verified",
			...(usedUploads.length ? { name: ["not in", usedUploads] } : {}),
		},
	}));
}

function maybeAddDeferredExpenseActions(frm) {
	if (!frm.doc.is_deferred_expense) {
		return;
	}

	frm.add_custom_button(__("Show Amortization Schedule"), async () => {
		if (!frm.doc.deferred_start_date) {
			frappe.msgprint(__("Deferred Start Date is required to generate the amortization schedule."));
			return;
		}

		if (!frm.doc.deferred_periods || frm.doc.deferred_periods <= 0) {
			frappe.msgprint(__("Deferred Periods must be greater than zero to generate the amortization schedule."));
			return;
		}

		const { message } = await frappe.call({
			method: "imogi_finance.services.deferred_expense.generate_amortization_schedule",
			args: {
				amount: frm.doc.amount,
				periods: frm.doc.deferred_periods,
				start_date: frm.doc.deferred_start_date,
			},
		});

		const schedule = message || [];
		const pretty = Array.isArray(schedule) ? JSON.stringify(schedule, null, 2) : String(schedule);
		frappe.msgprint({
			title: __("Amortization Schedule"),
			message: `<pre style="white-space: pre-wrap;">${pretty}</pre>`,
			indicator: "blue",
		});
	}, __("Actions"));
}

frappe.ui.form.on("Branch Expense Request", {
	onload(frm) {
		update_totals(frm);
	},
	async refresh(frm) {
		lockBerTaxInvoiceFields(frm);
		update_totals(frm);
		await setBerUploadQuery(frm);
		await syncBerUpload(frm);
		maybeAddDeferredExpenseActions(frm);
		maybeAddOcrButton(frm);
		maybeAddUploadActions(frm);
		maybeAddPaymentLetterButton(frm);
	},
	items_add(frm) {
		update_totals(frm);
	},
	items_remove(frm) {
		update_totals(frm);
	},
	ti_tax_invoice_upload: async function (frm) {
		await syncBerUpload(frm);
	},
});

frappe.ui.form.on("Branch Expense Request Item", {
	qty(frm, cdt, cdn) {
		update_item_amount(frm, cdt, cdn);
	},
	rate(frm, cdt, cdn) {
		update_item_amount(frm, cdt, cdn);
	},
	amount(frm) {
		update_totals(frm);
	},
});

function update_item_amount(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	const qty = flt(row.qty) || 0;
	const rate = flt(row.rate) || 0;
	const amount = qty * rate;
	frappe.model.set_value(cdt, cdn, "amount", amount);
	update_totals(frm);
}

function update_totals(frm) {
	const accounts = new Set();
	const total = (frm.doc.items || []).reduce((acc, row) => {
		if (row.expense_account) {
			accounts.add(row.expense_account);
		}
		return acc + flt(row.amount || 0);
	}, 0);

	frm.set_value("total_amount", total);
	frm.set_value("amount", total);
	frm.set_value("expense_account", accounts.size === 1 ? [...accounts][0] : null);
}

async function maybeAddOcrButton(frm) {
	if (!frm.doc.name) {
		return;
	}

	const enabled = await frappe.db.get_single_value("Tax Invoice OCR Settings", "enable_tax_invoice_ocr");
	if (!enabled || !frm.doc.ti_tax_invoice_upload) {
		return;
	}

	if (frm.taxInvoiceProviderReady === false) {
		const message = frm.taxInvoiceProviderError
			? __("OCR cannot run: {0}", [frm.taxInvoiceProviderError])
			: __("OCR provider is not configured.");
		frm.dashboard.set_headline(`<span class="indicator red">${message}</span>`);
		return;
	}

	frm.add_custom_button(__("Run OCR"), async () => {
		await frappe.call({
			method: "imogi_finance.api.tax_invoice.run_ocr_for_upload",
			args: { upload_name: frm.doc.ti_tax_invoice_upload },
			freeze: true,
			freeze_message: __("Queueing OCR..."),
		});
		frappe.show_alert({ message: __("OCR queued."), indicator: "green" });
		await syncBerUpload(frm);
	}, __("Tax Invoice"));
}

function maybeAddUploadActions(frm) {
	if (!frm.doc.name || !frm.doc.ti_tax_invoice_upload) {
		return;
	}

	frm.add_custom_button(__("Open Tax Invoice Upload"), () => {
		frappe.set_route("Form", "Tax Invoice OCR Upload", frm.doc.ti_tax_invoice_upload);
	}, __("Tax Invoice"));

	frm.add_custom_button(__("Refresh Tax Invoice Data"), async () => {
		await frappe.call({
			method: "imogi_finance.api.tax_invoice.apply_tax_invoice_upload",
			args: { target_doctype: "Branch Expense Request", target_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Refreshing..."),
		});
		await frm.reload_doc();
	}, __("Tax Invoice"));
}

function maybeAddPaymentLetterButton(frm) {
	if (frm.is_new() || frm.doc.docstatus !== 1) {
		return;
	}

	frm.add_custom_button(
		__("Payment Letter"),
		() => {
			frappe.call({
				method: "imogi_finance.imogi_finance.doctype.branch_expense_request.branch_expense_request.get_branch_expense_request_payment_letter",
				args: { name: frm.doc.name },
				callback(r) {
					if (!r.exc && r.message) {
						const w = window.open("", "_blank");
						w.document.write(r.message);
						w.document.close();
					}
				},
			});
		},
		__("Print"),
	);
}
