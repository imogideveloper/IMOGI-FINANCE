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
	
	// Skip sync for non-draft documents - OCR fields are read-only and already saved
	if (frm.doc.docstatus !== 0) {
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

function hideBerOcrStatus(frm) {
	if (frm.fields_dict?.ti_ocr_status) {
		frm.set_df_property('ti_ocr_status', 'hidden', true);
	}
}

function setExpenseAccountQuery(frm) {
	const filters = { root_type: "Expense", is_group: 0 };
	frm.set_query("expense_account", () => ({ filters }));
	frm.set_query("expense_account", "items", () => ({ filters }));
}

function formatApprovalTimestamps(frm) {
	// Format and display approval/rejection timestamps for each level
	for (let level = 1; level <= 3; level++) {
		const userField = `level_${level}_user`;
		const approvedField = `level_${level}_approved_on`;
		const rejectedField = `level_${level}_rejected_on`;
		
		if (!frm.doc[userField]) {
			continue; // Skip levels without approver
		}
		
		// Update field descriptions to show timestamps
		if (frm.doc[approvedField]) {
			const formattedTime = frappe.datetime.str_to_user(frm.doc[approvedField]);
			frm.set_df_property(approvedField, 'description', `✅ Approved at ${formattedTime}`);
		}
		
		if (frm.doc[rejectedField]) {
			const formattedTime = frappe.datetime.str_to_user(frm.doc[rejectedField]);
			frm.set_df_property(rejectedField, 'description', `❌ Rejected at ${formattedTime}`);
		}
	}
}

async function checkOcrEnabledBer(frm) {
	try {
		const ocrEnabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
		frm.doc.__ocr_enabled = Boolean(ocrEnabled);
		frm.refresh_fields();
	} catch (error) {
		console.error('Unable to check OCR settings', error);
		frm.doc.__ocr_enabled = false;
	}
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

function computeTotalsBer(frm) {
	const flt = (frappe.utils && frappe.utils.flt) || window.flt || ((value) => parseFloat(value) || 0);
	const totalExpense = flt(frm.doc.amount || 0);
	const totalPpn = flt(frm.doc.ti_fp_ppn || 0);
	const totalPpnbm = flt(frm.doc.ti_fp_ppnbm || 0);
	const totalAmount = totalExpense + totalPpn + totalPpnbm;

	return {
		totalExpense,
		totalPpn,
		totalPpnbm,
		totalAmount,
	};
}

function renderTotalsHtmlBer(frm, totals) {
	const format = (value) =>
		frappe.format(value, { fieldtype: 'Currency', options: frm.doc.currency });

	const rows = [
		['Total Expense', format(totals.totalExpense)],
		['Total PPN', format(totals.totalPpn)],
		['Total PPnBM', format(totals.totalPpnbm)],
		['Total', format(totals.totalAmount)],
	];

	const cells = rows
		.map(
			([label, value]) => `
			<tr>
				<td>${frappe.utils.escape_html(label)}</td>
				<td class="text-right">${value}</td>
			</tr>
			`
		)
		.join('');

	return `<table class="table table-bordered table-sm"><tbody>${cells}</tbody></table>`;
}

function updateTotalsSummaryBer(frm) {
	const totals = computeTotalsBer(frm);
	const fields = {
		total_amount: totals.totalAmount,
	};

	// Only update fields in draft mode to prevent "Not Saved" badge on submitted docs
	if (frm.doc.docstatus === 0) {
		Object.entries(fields).forEach(([field, value]) => {
			if (!frm.fields_dict[field]) {
				return;
			}
			if (frm.doc[field] !== value) {
				frm.doc[field] = value;
				frm.refresh_field(field);
			}
		});
	}

	const html = renderTotalsHtmlBer(frm, totals);
	['items_totals_html'].forEach((fieldname) => {
		const field = frm.fields_dict[fieldname];
		if (field?.$wrapper) {
			field.$wrapper.html(html);
		}
	});
}

function maybeAddDeferredExpenseActions(frm) {
	// Deprecated: replaced by per-item deferred actions.
}

async function loadDeferrableAccounts(frm) {
	if (frm.deferrableAccountsLoaded) {
		return;
	}

	try {
		const { message } = await frappe.call({
			method: "imogi_finance.api.get_deferrable_accounts",
		});

		const accounts = message?.accounts || [];
		frm.deferrableAccountMap = accounts.reduce((acc, row) => {
			if (row.prepaid_account) {
				acc[row.prepaid_account] = row;
			}
			return acc;
		}, {});
		frm.deferrableAccountsLoaded = true;
	} catch (error) {
		console.error("Failed to load deferrable accounts", error);
	}
}

async function setDeferredExpenseQueries(frm) {
	await loadDeferrableAccounts(frm);

	const accountNames = Object.keys(frm.deferrableAccountMap || {});
	frm.set_query("prepaid_account", "items", () => ({
		filters: {
			name: ["in", accountNames.length ? accountNames : [""]],
		},
	}));
}

async function showDeferredScheduleForItem(row) {
	if (!row.deferred_start_date) {
		frappe.msgprint(__("Deferred Start Date is required to generate the amortization schedule."));
		return;
	}

	if (!row.deferred_periods || row.deferred_periods <= 0) {
		frappe.msgprint(__("Deferred Periods must be greater than zero to generate the amortization schedule."));
		return;
	}

	const { message } = await frappe.call({
		method: "imogi_finance.services.deferred_expense.generate_amortization_schedule",
		args: {
			amount: row.amount,
			periods: row.deferred_periods,
			start_date: row.deferred_start_date,
		},
	});

	const schedule = message || [];
	const pretty = Array.isArray(schedule) ? JSON.stringify(schedule, null, 2) : String(schedule);
	frappe.msgprint({
		title: __("Amortization Schedule"),
		message: `<pre style="white-space: pre-wrap;">${pretty}</pre>`,
		indicator: "blue",
	});
}

function addDeferredExpenseItemActions(frm) {
	const grid = frm.fields_dict.items?.grid;
	if (!grid) {
		return;
	}

	grid.grid_rows.forEach((row) => {
		if (!row?.doc?.is_deferred_expense) {
			return;
		}

		if (row.__hasDeferredAction) {
			return;
		}

		const addButton = row.add_custom_button || row.grid_form?.add_custom_button;
		if (typeof addButton !== "function") {
			return;
		}

		addButton.call(row, __("Show Amortization Schedule"), () => showDeferredScheduleForItem(row.doc));
		row.__hasDeferredAction = true;
	});
}

function updateDeferredExpenseIndicators(frm) {
	const grid = frm.fields_dict.items?.grid;
	if (!grid) {
		return;
	}

	grid.grid_rows.forEach((row) => {
		const indicator = row.$row?.find('.grid-static-col[data-fieldname="is_deferred_expense"] .static-text');
		if (!indicator?.length) {
			return;
		}
		indicator.text(row.doc?.is_deferred_expense ? "📅" : "");
	});
}

frappe.ui.form.on("Branch Expense Request", {
	onload(frm) {
		update_totals(frm);
	},
	async refresh(frm) {
		hideBerOcrStatus(frm);
		lockBerTaxInvoiceFields(frm);
		setExpenseAccountQuery(frm);
		formatApprovalTimestamps(frm);
		frm.dashboard.clear_headline();
		update_totals(frm);
		await setBerUploadQuery(frm);
		await checkOcrEnabledBer(frm);
		await syncBerUpload(frm);
		await setDeferredExpenseQueries(frm);
		addDeferredExpenseItemActions(frm);
		updateDeferredExpenseIndicators(frm);
		updateTotalsSummaryBer(frm);
		maybeAddOcrButton(frm);
		maybeAddUploadActions(frm);
		addCheckRouteButton(frm);
	},
	items_add(frm) {
		update_totals(frm);
		addDeferredExpenseItemActions(frm);
		updateDeferredExpenseIndicators(frm);
		updateTotalsSummaryBer(frm);
	},
	items_remove(frm) {
		update_totals(frm);
		updateDeferredExpenseIndicators(frm);
		updateTotalsSummaryBer(frm);
	},
	ti_fp_ppn(frm) {
		updateTotalsSummaryBer(frm);
	},
	ti_fp_ppnbm(frm) {
		updateTotalsSummaryBer(frm);
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
		updateTotalsSummaryBer(frm);
	},
	async prepaid_account(frm, cdt, cdn) {
		await loadDeferrableAccounts(frm);
		const row = frappe.get_doc(cdt, cdn);
		const mapping = frm.deferrableAccountMap?.[row.prepaid_account];
		if (!mapping) {
			return;
		}

		if (mapping.expense_account && row.expense_account !== mapping.expense_account) {
			frappe.model.set_value(cdt, cdn, "expense_account", mapping.expense_account);
		}
		if (mapping.default_periods && !row.deferred_periods) {
			frappe.model.set_value(cdt, cdn, "deferred_periods", mapping.default_periods);
		}
	},
	is_deferred_expense(frm) {
		addDeferredExpenseItemActions(frm);
		updateDeferredExpenseIndicators(frm);
	},
	deferred_start_date(frm) {
		addDeferredExpenseItemActions(frm);
	},
	deferred_periods(frm) {
		addDeferredExpenseItemActions(frm);
	},
});

function update_item_amount(frm, cdt, cdn) {
	const row = frappe.get_doc(cdt, cdn);
	const qty = flt(row.qty) || 0;
	const rate = flt(row.rate) || 0;
	const amount = qty * rate;
	frappe.model.set_value(cdt, cdn, "amount", amount);
	update_totals(frm);
	updateTotalsSummaryBer(frm);
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
	updateTotalsSummaryBer(frm);
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

function addCheckRouteButton(frm) {
	if (!frm.doc.branch || frm.doc.docstatus !== 0) {
		return;
	}

	const routeBtn = frm.add_custom_button(__('Check Approval Route'), async () => {
		const stringify = (value) => JSON.stringify(value || []);

		try {
			routeBtn?.prop?.('disabled', true);
		} catch (error) {
			// ignore if prop is not available
		}

		try {
			const { message } = await frappe.call({
				method: 'imogi_finance.branch_approval.check_branch_expense_request_route',
				args: {
					branch: frm.doc.branch,
					items: stringify(frm.doc.items),
					expense_accounts: stringify(frm.doc.expense_accounts),
					amount: frm.doc.amount,
					docstatus: frm.doc.docstatus,
				},
			});

			if (message?.ok) {
				const route = message.route || {};
				const rows = ['1', '2', '3']
					.map((level) => {
						const info = route[`level_${level}`] || {};
						if (!info.user) {
							return null;
						}
						const role = info.role ? __('Role: {0}', [info.role]) : '';
						const user = info.user ? __('User: {0}', [info.user]) : '';
						const details = [user, role].filter(Boolean).join(' | ');
						return `<li>${__('Level {0}', [level])}: ${details}</li>`;
					})
					.filter(Boolean)
					.join('');

				let messageContent = rows
					? `<ul>${rows}</ul>`
					: __('No approver configured for the current route.');

				// Show auto-approve notice if applicable
				if (message.auto_approve) {
					messageContent = __('No approval required. Request will be auto-approved.');
				}

				frappe.msgprint({
					title: __('Approval Route'),
					message: messageContent,
					indicator: 'green',
				});
				return;
			}

			// Handle validation errors (including invalid users)
			let indicator = 'orange';
			let errorMessage = message?.message
				? message.message
				: __('Approval route could not be determined. Please ask your System Manager to configure a Branch Expense Approval Setting.');

			// Show red indicator for user validation errors
			if (message?.user_validation && !message.user_validation.valid) {
				indicator = 'red';

				// Build detailed error message
				const details = [];

				if (message.user_validation.invalid_users?.length) {
					details.push(
						'<strong>' + __('Users not found:') + '</strong><ul>' +
						message.user_validation.invalid_users.map(u =>
							`<li>${__('Level {0}', [u.level])}: <code>${u.user}</code></li>`
						).join('') +
						'</ul>'
					);
				}

				if (message.user_validation.disabled_users?.length) {
					details.push(
						'<strong>' + __('Users disabled:') + '</strong><ul>' +
						message.user_validation.disabled_users.map(u =>
							`<li>${__('Level {0}', [u.level])}: <code>${u.user}</code></li>`
						).join('') +
						'</ul>'
					);
				}

				if (details.length) {
					errorMessage = details.join('<br>') +
						'<br><br>' + __('Please update the Branch Expense Approval Setting to use valid, active users.');
				}
			}
			frappe.msgprint({
				title: __('Approval Route'),
				message: errorMessage,
				indicator: indicator,
			});
		} catch (error) {
			frappe.msgprint({
				title: __('Approval Route'),
				message: error?.message
					? error.message
					: __('Unable to check approval route right now. Please try again.'),
				indicator: 'red',
			});
		} finally {
			try {
				routeBtn?.prop?.('disabled', false);
			} catch (error) {
				// ignore if prop is not available
			}
		}
	}, __('Actions'));
}
