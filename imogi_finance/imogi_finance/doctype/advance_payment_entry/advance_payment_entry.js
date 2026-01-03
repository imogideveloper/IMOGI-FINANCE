frappe.ui.form.on("Advance Payment Entry", {
    refresh(frm) {
        frm.trigger("recalculate_totals");
        frm.trigger("toggle_allocation_status");
    },

    advance_amount(frm) {
        frm.trigger("recalculate_totals");
    },

    exchange_rate(frm) {
        frm.trigger("recalculate_totals");
    },

    recalculate_totals(frm) {
        const allowUpdates = frm.doc.docstatus === 0;
        const allocated = (frm.doc.references || []).reduce((acc, row) => acc + frappe.utils.flt(row.allocated_amount), 0);
        const unallocated = frappe.utils.flt(frm.doc.advance_amount) - allocated;

        if (allowUpdates) {
            frm.set_value("allocated_amount", allocated);
            frm.set_value("unallocated_amount", unallocated);
            frm.set_value("base_advance_amount", frappe.utils.flt(frm.doc.advance_amount) * frappe.utils.flt(frm.doc.exchange_rate || 1));
            frm.set_value("base_allocated_amount", allocated * frappe.utils.flt(frm.doc.exchange_rate || 1));
            frm.set_value("base_unallocated_amount", frappe.utils.flt(frm.doc.base_advance_amount) - frappe.utils.flt(frm.doc.base_allocated_amount));
        }

        if (allowUpdates) {
            (frm.doc.references || []).forEach((row) => {
                row.remaining_amount = Math.max(unallocated, 0);
                if (!row.reference_currency) {
                    row.reference_currency = frm.doc.currency;
                }
                if (!row.reference_exchange_rate) {
                    row.reference_exchange_rate = frm.doc.exchange_rate;
                }
            });
        }

        frm.refresh_field("references");
    },

    toggle_allocation_status(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.unallocated_amount && frm.doc.unallocated_amount <= 0) {
            frm.set_value("status", "Reconciled");
        }
    },

    references_remove(frm) {
        frm.trigger("recalculate_totals");
    },
});

frappe.ui.form.on("Advance Payment Reference", {
    allocated_amount(frm) {
        frm.trigger("recalculate_totals");
    },
});
