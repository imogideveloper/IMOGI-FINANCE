// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Customer Receipt', {
    refresh: function(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.outstanding_amount > 0) {
            frm.add_custom_button(__('Make Payment Entry'), function() {
                frappe.call({
                    method: 'make_payment_entry',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message) {
                            frappe.set_route('Form', 'Payment Entry', r.message.name);
                        }
                    }
                });
            });
        }

        // Track print action
        if (frm.doc.docstatus === 1) {
            frm.page.on('print', function() {
                frappe.call({
                    method: 'track_print',
                    doc: frm.doc,
                    callback: function(r) {
                        if (r.message) {
                            frm.reload_doc();
                        }
                    }
                });
            });
        }
    },

    receipt_purpose: function(frm) {
        // Clear items when receipt purpose changes
        frm.clear_table('items');
        frm.refresh_field('items');
    },

    customer: function(frm) {
        // Clear items when customer changes
        frm.clear_table('items');
        frm.refresh_field('items');
    },

    company: function(frm) {
        // Clear items when company changes
        frm.clear_table('items');
        frm.refresh_field('items');
    }
});

frappe.ui.form.on('Customer Receipt Item', {
    items_add: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        
        // Set up query filters for Sales Invoice
        if (frm.doc.receipt_purpose === 'Billing (Sales Invoice)' && frm.doc.customer && frm.doc.company) {
            frappe.meta.get_docfield('Customer Receipt Item', 'sales_invoice', cdn).get_query = function() {
                return {
                    filters: {
                        'customer': frm.doc.customer,
                        'company': frm.doc.company,
                        'docstatus': 1,
                        'outstanding_amount': ['>', 0]
                    }
                };
            };
        }

        // Set up query filters for Sales Order
        if (frm.doc.receipt_purpose === 'Before Billing (Sales Order)' && frm.doc.customer && frm.doc.company) {
            frappe.meta.get_docfield('Customer Receipt Item', 'sales_order', cdn).get_query = function() {
                return {
                    filters: {
                        'customer': frm.doc.customer,
                        'company': frm.doc.company,
                        'docstatus': 1
                    }
                };
            };
        }
    },

    sales_invoice: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.sales_invoice && frm.doc.receipt_purpose === 'Billing (Sales Invoice)') {
            // Clear sales_order if accidentally filled
            if (row.sales_order) {
                frappe.model.set_value(cdt, cdn, 'sales_order', '');
            }
            fetch_sales_invoice_data(frm, row);
        }
    },

    sales_order: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.sales_order && frm.doc.receipt_purpose === 'Before Billing (Sales Order)') {
            // Clear sales_invoice if accidentally filled
            if (row.sales_invoice) {
                frappe.model.set_value(cdt, cdn, 'sales_invoice', '');
            }
            fetch_sales_order_data(frm, row);
        }
    }
});

function fetch_sales_invoice_data(frm, row) {
    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Sales Invoice',
            name: row.sales_invoice,
            fields: ['customer', 'company', 'posting_date', 'outstanding_amount', 'grand_total', 'docstatus']
        },
        callback: function(r) {
            if (r.message) {
                // Validate customer
                if (r.message.customer !== frm.doc.customer) {
                    frappe.msgprint(__('Sales Invoice customer does not match Customer Receipt customer'));
                    frappe.model.set_value(row.doctype, row.name, 'sales_invoice', '');
                    return;
                }

                // Validate company
                if (r.message.company !== frm.doc.company) {
                    frappe.msgprint(__('Sales Invoice company does not match Customer Receipt company'));
                    frappe.model.set_value(row.doctype, row.name, 'sales_invoice', '');
                    return;
                }

                // Validate submission status
                if (r.message.docstatus !== 1) {
                    frappe.msgprint(__('Sales Invoice must be submitted before linking'));
                    frappe.model.set_value(row.doctype, row.name, 'sales_invoice', '');
                    return;
                }

                // Auto-fill data
                frappe.model.set_value(row.doctype, row.name, 'reference_date', r.message.posting_date);
                frappe.model.set_value(row.doctype, row.name, 'reference_outstanding', r.message.outstanding_amount);
                
                // Set amount_to_collect to outstanding amount if not already set
                if (!row.amount_to_collect || row.amount_to_collect === 0) {
                    frappe.model.set_value(row.doctype, row.name, 'amount_to_collect', r.message.outstanding_amount);
                }

                frappe.show_alert({
                    message: __('Sales Invoice data fetched: Customer={0}, Amount={1}', [r.message.customer, format_currency(r.message.outstanding_amount)]),
                    indicator: 'green'
                }, 5);
            }
        }
    });
}

function fetch_sales_order_data(frm, row) {
    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Sales Order',
            name: row.sales_order,
            fields: ['customer', 'company', 'transaction_date', 'advance_paid', 'grand_total', 'docstatus']
        },
        callback: function(r) {
            if (r.message) {
                // Validate customer
                if (r.message.customer !== frm.doc.customer) {
                    frappe.msgprint(__('Sales Order customer does not match Customer Receipt customer'));
                    frappe.model.set_value(row.doctype, row.name, 'sales_order', '');
                    return;
                }

                // Validate company
                if (r.message.company !== frm.doc.company) {
                    frappe.msgprint(__('Sales Order company does not match Customer Receipt company'));
                    frappe.model.set_value(row.doctype, row.name, 'sales_order', '');
                    return;
                }

                // Validate submission status
                if (r.message.docstatus !== 1) {
                    frappe.msgprint(__('Sales Order must be submitted before linking'));
                    frappe.model.set_value(row.doctype, row.name, 'sales_order', '');
                    return;
                }

                // Calculate outstanding (grand_total - advance_paid)
                let outstanding = r.message.grand_total - (r.message.advance_paid || 0);

                // Auto-fill data
                frappe.model.set_value(row.doctype, row.name, 'reference_date', r.message.transaction_date);
                frappe.model.set_value(row.doctype, row.name, 'reference_outstanding', outstanding);
                
                // Set amount_to_collect to outstanding amount if not already set
                if (!row.amount_to_collect || row.amount_to_collect === 0) {
                    frappe.model.set_value(row.doctype, row.name, 'amount_to_collect', outstanding);
                }

                frappe.show_alert({
                    message: __('Sales Order data fetched: Customer={0}, Amount={1}', [r.message.customer, format_currency(outstanding)]),
                    indicator: 'green'
                }, 5);
            }
        }
    });
}
