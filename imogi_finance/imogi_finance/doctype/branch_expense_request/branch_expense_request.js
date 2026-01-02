frappe.ui.form.on("Branch Expense Request", {
	onload(frm) {
		update_totals(frm);
	},
	refresh(frm) {
		update_totals(frm);
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
	const total = (frm.doc.items || []).reduce((acc, row) => acc + flt(row.amount || 0), 0);
	frm.set_value("total_amount", total);
}
