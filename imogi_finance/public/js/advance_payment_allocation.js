frappe.provide("imogi_finance.advance_payment");

const allocationUI = {
    async renderAllocations(frm) {
        if (frm.is_new()) {
            return;
        }

        try {
            const response = await frappe.call({
                method: "imogi_finance.advance_payment.api.get_allocations_for_reference",
                args: {
                    reference_doctype: frm.doc.doctype,
                    reference_name: frm.doc.name,
                },
            });
            const rows = response.message || [];
            if (!rows.length) {
                if (frm.dashboard && frm.dashboard.clear) {
                    frm.dashboard.clear();
                }
                return;
            }

            const totalAllocated = rows.reduce((acc, row) => acc + frappe.utils.flt(row.allocated_amount), 0);
            if (frm.dashboard) {
                if (frm.dashboard.clear) {
                    frm.dashboard.clear();
                }
                frm.dashboard.add_indicator(
                    `${frappe.utils.format_currency(totalAllocated, frm.doc.currency || rows[0].reference_currency || rows[0].advance_currency)} allocated from advances`,
                    "blue",
                );

                const tableRows = rows
                    .map(
                        (row) => `
                        <tr>
                            <td>${row.parent}</td>
                            <td>${frappe.utils.format_currency(row.allocated_amount, row.reference_currency || frm.doc.currency)}</td>
                            <td>${row.advance_unallocated != null ? frappe.utils.format_currency(row.advance_unallocated, row.advance_currency) : "-"}</td>
                        </tr>`
                    )
                    .join("");
                const table = `
                    <div class="form-dashboard-section">
                        <div class="section-body">
                            <table class="table table-bordered">
                                <thead>
                                    <tr>
                                        <th>${__("Advance Payment")}</th>
                                        <th>${__("Allocated")}</th>
                                        <th>${__("Unallocated")}</th>
                                    </tr>
                                </thead>
                                <tbody>${tableRows}</tbody>
                            </table>
                        </div>
                    </div>`;
                frm.dashboard.add_section(table);
                frm.dashboard.show();
            }
        } catch (error) {
            frappe.show_alert({ message: __("Unable to load advance allocations"), indicator: "orange" });
            // eslint-disable-next-line no-console
            console.warn("Failed to load allocations", error);
        }
    },

    addButton(frm, partyInfo) {
        if (!partyInfo.party || frm.doc.docstatus === 2) {
            return;
        }

        const label = __("Get Advances");
        const group = __("Payments");

        frm.add_custom_button(
            label,
            () => {
                if (frm.is_dirty()) {
                    frappe.throw(__("Please save the document before allocating advances."));
                }
                allocationUI.openDialog(frm, partyInfo);
            },
            group,
        );
    },

    async openDialog(frm, partyInfo) {
        const advances = await allocationUI.fetchAdvances(partyInfo);
        if (!advances.length) {
            frappe.msgprint(__("No unallocated advances were found for this party."));
            return;
        }

        const dialog = new frappe.ui.Dialog({
            title: __("Allocate Advances"),
            size: "large",
            fields: [{ fieldname: "body", fieldtype: "HTML" }],
            primary_action_label: __("Allocate"),
            primary_action: async () => {
                const allocations = [];
                dialog.$wrapper.find('[data-role="advance-row"]').each((_, row) => {
                    const $row = $(row);
                    const isChecked = $row.find('input[type="checkbox"]').is(":checked");
                    if (!isChecked) return;

                    const amount = frappe.utils.flt($row.find('input[data-fieldname="allocated_amount"]').val());
                    if (amount > 0) {
                        allocations.push({
                            advance_payment_entry: $row.data("name"),
                            allocated_amount: amount,
                        });
                    }
                });

                if (!allocations.length) {
                    frappe.throw(__("Please enter at least one allocation amount."));
                }

                const outstanding = allocationUI.getOutstandingAmount(frm);
                const totalAllocation = allocations.reduce((acc, row) => acc + frappe.utils.flt(row.allocated_amount), 0);
                if (outstanding != null && totalAllocation - outstanding > 0.005) {
                    frappe.throw(
                        __("Allocations of {0} exceed outstanding amount {1}.", [
                            frappe.format_currency(totalAllocation, frm.doc.currency),
                            frappe.format_currency(outstanding, frm.doc.currency),
                        ]),
                    );
                }

                await frappe.call({
                    method: "imogi_finance.advance_payment.api.allocate_advances",
                    args: {
                        reference_doctype: frm.doc.doctype,
                        reference_name: frm.doc.name,
                        allocations,
                        party_type: partyInfo.party_type,
                        party: partyInfo.party,
                    },
                });

                dialog.hide();
                await frm.reload_doc();
                allocationUI.renderAllocations(frm);
                frappe.show_alert({ message: __("Advance allocations updated"), indicator: "green" });
            },
        });

        const rowsHtml = advances
            .map(
                (row) => `
                <tr data-role="advance-row" data-name="${row.name}">
                    <td><input type="checkbox" checked /></td>
                    <td>${row.name}</td>
                    <td>${frappe.datetime.str_to_user(row.posting_date)}</td>
                    <td>${frappe.utils.format_currency(row.unallocated_amount, row.currency)}</td>
                    <td><input data-fieldname="allocated_amount" type="number" min="0" max="${row.unallocated_amount}" step="0.01" value="${row.unallocated_amount}" class="input-with-feedback form-control" /></td>
                </tr>`
            )
            .join("");

        dialog.fields_dict.body.$wrapper.html(`
            <div class="table-responsive">
                <table class="table table-bordered" style="margin-bottom: 0;">
                    <thead>
                        <tr>
                            <th style="width: 40px"></th>
                            <th>${__("Advance Payment")}</th>
                            <th>${__("Posting Date")}</th>
                            <th>${__("Unallocated Amount")}</th>
                            <th>${__("Allocated Amount")}</th>
                        </tr>
                    </thead>
                    <tbody>${rowsHtml}</tbody>
                </table>
            </div>`);

        dialog.$wrapper.on("input", 'input[data-fieldname="allocated_amount"]', (event) => {
            const $input = $(event.currentTarget);
            const max = frappe.utils.flt($input.attr("max"));
            const val = frappe.utils.flt($input.val());
            if (val > max) {
                $input.val(max);
            }
        });

        dialog.show();
    },

    async fetchAdvances(partyInfo) {
        const response = await frappe.call({
            method: "imogi_finance.advance_payment.api.get_available_advances",
            args: {
                party_type: partyInfo.party_type,
                party: partyInfo.party,
                company: partyInfo.company,
                currency: partyInfo.currency,
            },
        });

        return response.message || [];
    },

    getOutstandingAmount(frm) {
        if (frm.doc.doctype === "Purchase Invoice") {
            return frappe.utils.flt(frm.doc.outstanding_amount || frm.doc.rounded_total || frm.doc.grand_total || 0);
        }
        if (frm.doc.doctype === "Expense Claim") {
            const total = frappe.utils.flt(frm.doc.grand_total || frm.doc.total_sanctioned_amount || frm.doc.total_claimed_amount || 0);
            const reimbursed = frappe.utils.flt(frm.doc.total_amount_reimbursed || 0);
            const advances = frappe.utils.flt(frm.doc.total_advance_amount || frm.doc.total_advance || 0);
            return total - reimbursed - advances;
        }
        if (frm.doc.doctype === "Payroll Entry") {
            return frappe.utils.flt(frm.doc.total_deduction || frm.doc.total_payment || 0);
        }
        return null;
    },
};

const buildPartyInfo = (frm) => {
    const defaults = {
        company: frm.doc.company,
        currency: frm.doc.currency || frm.doc.company_currency,
    };

    if (frm.doc.doctype === "Purchase Invoice") {
        return {
            ...defaults,
            party_type: "Supplier",
            party: frm.doc.supplier,
        };
    }

    if (frm.doc.doctype === "Expense Claim") {
        return {
            ...defaults,
            party_type: "Employee",
            party: frm.doc.employee,
        };
    }

    return defaults;
};

frappe.ui.form.on("Purchase Invoice", {
    refresh(frm) {
        const partyInfo = buildPartyInfo(frm);
        allocationUI.addButton(frm, partyInfo);
        allocationUI.renderAllocations(frm);
    },
    after_save(frm) {
        allocationUI.renderAllocations(frm);
    },
});

frappe.ui.form.on("Expense Claim", {
    refresh(frm) {
        const partyInfo = buildPartyInfo(frm);
        allocationUI.addButton(frm, partyInfo);
        allocationUI.renderAllocations(frm);
    },
    after_save(frm) {
        allocationUI.renderAllocations(frm);
    },
});

frappe.ui.form.on("Payroll Entry", {
    refresh(frm) {
        const partyInfo = buildPartyInfo(frm);
        allocationUI.addButton(frm, partyInfo);
        allocationUI.renderAllocations(frm);
    },
    after_save(frm) {
        allocationUI.renderAllocations(frm);
    },
});
