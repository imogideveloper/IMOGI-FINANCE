frappe.ui.form.on("Branch Expense Request", {
	onload(frm) {
		update_totals(frm);
	},
	refresh(frm) {
		update_totals(frm);
		maybeAddOcrButton(frm);
		maybeAddVerifyButton(frm);
	},
	items_add(frm) {
		update_totals(frm);
	},
	items_remove(frm) {
		update_totals(frm);
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
	if (!enabled || !frm.doc.ti_tax_invoice_pdf) {
		return;
	}

	frm.add_custom_button(__("Run OCR"), async () => {
		await frappe.call({
			method: "imogi_finance.api.tax_invoice.run_ocr_for_branch_expense_request",
			args: { ber_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Queueing OCR..."),
		});
		frappe.show_alert({ message: __("OCR queued."), indicator: "green" });
		frm.reload_doc();
	}, __("Tax Invoice"));
}

function maybeAddVerifyButton(frm) {
	if (!frm.doc.name) {
		return;
	}

	if (!frm.doc.ti_fp_no && !frm.doc.ti_fp_npwp && !frm.doc.ti_fp_dpp && !frm.doc.ti_fp_ppn && frm.doc.ti_ocr_status !== "Done") {
		return;
	}

	frm.add_custom_button(__("Verify Tax Invoice"), async () => {
		const r = await frappe.call({
			method: "imogi_finance.api.tax_invoice.verify_branch_expense_request_tax_invoice",
			args: { ber_name: frm.doc.name },
			freeze: true,
			freeze_message: __("Verifying..."),
		});
		if (r && r.message) {
			frappe.show_alert({ message: __("Verification status: {0}", [r.message.status]), indicator: "green" });
			frm.reload_doc();
		}
	}, __("Tax Invoice"));
}
