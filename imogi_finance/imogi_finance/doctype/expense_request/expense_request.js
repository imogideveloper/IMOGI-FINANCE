frappe.ui.form.on('Expense Request', {
  refresh(frm) {
    frm.dashboard.clear_headline();

    if (!frm.doc.docstatus) {
      return;
    }

    const isSubmitted = frm.doc.docstatus === 1;
    const allowedStatuses = ['Approved'];
    const isAllowedStatus = allowedStatuses.includes(frm.doc.status);
    const isLinked = frm.doc.status === 'Linked';
    const hasLinkedPurchaseInvoice = Boolean(frm.doc.linked_purchase_invoice);

    if (isSubmitted && isLinked && hasLinkedPurchaseInvoice) {
      frm.dashboard.set_headline(__('Purchase Invoice {0} already linked to this request.', [
        frm.doc.linked_purchase_invoice,
      ]));
    }

    const canCreatePurchaseInvoice = isSubmitted && isAllowedStatus && !hasLinkedPurchaseInvoice;

    if (canCreatePurchaseInvoice) {
      frm.add_custom_button(__('Create Purchase Invoice'), () => {
        frm.call('create_purchase_invoice', {
          expense_request: frm.doc.name,
        }).then((r) => {
          if (r && r.message) {
            frappe.msgprint({
              title: __('Purchase Invoice Created'),
              message: __('Purchase Invoice {0} created from this request.', [r.message]),
              indicator: 'green',
            });
            frm.reload_doc();
          }
        });
      }, __('Create'));
    }
  },
});
