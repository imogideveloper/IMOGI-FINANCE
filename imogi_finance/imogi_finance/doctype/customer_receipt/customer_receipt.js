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
        // Update query filters for future rows
        setup_item_query_filters(frm);
    },

    customer: function(frm) {
        // Clear items when customer changes
        frm.clear_table('items');
        frm.refresh_field('items');
        // Update query filters for future rows
        setup_item_query_filters(frm);
    },

    company: function(frm) {
        // Clear items when company changes
        frm.clear_table('items');
        frm.refresh_field('items');
        // Update query filters for future rows
        setup_item_query_filters(frm);
    }
});

// Helper function to setup query filters
function setup_item_query_filters(frm) {
    // Set up query filters for Sales Invoice
    if (frm.doc.receipt_purpose === 'Billing (Sales Invoice)') {
        frm.set_query('sales_invoice', 'items', function() {
            return {
                filters: {
                    'customer': frm.doc.customer || '',
                    'company': frm.doc.company || '',
                    'docstatus': 1,
                    'outstanding_amount': ['>', 0]
                }
            };
        });
        // Clear sales_order query
        frm.set_query('sales_order', 'items', function() {
            return { filters: { 'name': ['=', ''] } }; // Return empty to hide
        });
    }
    // Set up query filters for Sales Order
    else if (frm.doc.receipt_purpose === 'Before Billing (Sales Order)') {
        frm.set_query('sales_order', 'items', function() {
            return {
                filters: {
                    'customer': frm.doc.customer || '',
                    'company': frm.doc.company || '',
                    'docstatus': 1
                }
            };
        });
        // Clear sales_invoice query
        frm.set_query('sales_invoice', 'items', function() {
            return { filters: { 'name': ['=', ''] } }; // Return empty to hide
        });
    }
}

frappe.ui.form.on('Customer Receipt Item', {
    items_add: function(frm, cdt, cdn) {
        // Query filters are already set at parent level
        setup_item_query_filters(frm);
    },

    sales_invoice: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log('sales_invoice triggered', {sales_invoice: row.sales_invoice, receipt_purpose: frm.doc.receipt_purpose});
        
        if (row.sales_invoice) {
            // Validate receipt purpose
            if (frm.doc.receipt_purpose !== 'Billing (Sales Invoice)') {
                frappe.msgprint(__('Please set Receipt Purpose to "Billing (Sales Invoice)" to use Sales Invoice'));
                frappe.model.set_value(cdt, cdn, 'sales_invoice', '');
                return;
            }
            
            // Clear sales_order if accidentally filled
            if (row.sales_order) {
                frappe.model.set_value(cdt, cdn, 'sales_order', '');
            }
            
            fetch_sales_invoice_data(frm, row);
        }
    },

    sales_order: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        console.log('sales_order triggered', {sales_order: row.sales_order, receipt_purpose: frm.doc.receipt_purpose});
        
        if (row.sales_order) {
            // Validate receipt purpose
            if (frm.doc.receipt_purpose !== 'Before Billing (Sales Order)') {
                frappe.msgprint(__('Please set Receipt Purpose to "Before Billing (Sales Order)" to use Sales Order'));
                frappe.model.set_value(cdt, cdn, 'sales_order', '');
                return;
            }
            
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
                // Auto-populate customer if empty
                if (!frm.doc.customer) {
                    frm.set_value('customer', r.message.customer);
                }
                
                // Auto-populate company if empty
                if (!frm.doc.company) {
                    frm.set_value('company', r.message.company);
                }
                
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

                // Auto-fill data - update locals directly to avoid refresh issues with depends_on
                row.reference_date = r.message.posting_date;
                row.reference_outstanding = r.message.outstanding_amount;
                
                // Set amount_to_collect to outstanding amount if not already set
                if (!row.amount_to_collect || row.amount_to_collect === 0) {
                    row.amount_to_collect = r.message.outstanding_amount;
                }
                
                // Refresh the grid row to show updated values
                frm.fields_dict.items.grid.grid_rows_by_docname[row.name].refresh();

                frappe.show_alert({
                    message: __('Sales Invoice data fetched: Customer={0}, Amount={1}', [r.message.customer, format_currency(r.message.outstanding_amount)]),
                    indicator: 'green'
                }, 5);
            }
        }
    });
}

function fetch_sales_order_data(frm, row) {
    console.log('fetch_sales_order_data called', {sales_order: row.sales_order, row_name: row.name});
    
    frappe.call({
        method: 'frappe.client.get',
        args: {
            doctype: 'Sales Order',
            name: row.sales_order,
            fields: ['customer', 'company', 'transaction_date', 'advance_paid', 'grand_total', 'docstatus']
        },
        callback: function(r) {
            console.log('fetch_sales_order_data response', r);
            
            if (r.message) {
                // Auto-populate customer if empty
                if (!frm.doc.customer) {
                    frm.set_value('customer', r.message.customer);
                }
                
                // Auto-populate company if empty
                if (!frm.doc.company) {
                    frm.set_value('company', r.message.company);
                }
                
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

                // Auto-fill data - update locals directly to avoid refresh issues with depends_on
                row.reference_date = r.message.transaction_date;
                row.reference_outstanding = outstanding;
                
                // Set amount_to_collect to outstanding amount if not already set
                if (!row.amount_to_collect || row.amount_to_collect === 0) {
                    row.amount_to_collect = outstanding;
                }
                
                // Refresh the grid row to show updated values
                frm.fields_dict.items.grid.grid_rows_by_docname[row.name].refresh();

                frappe.show_alert({
                    message: __('Sales Order data fetched: Customer={0}, Amount={1}', [r.message.customer, format_currency(outstanding)]),
                    indicator: 'green'
                }, 5);
            }
        }
    });
}
