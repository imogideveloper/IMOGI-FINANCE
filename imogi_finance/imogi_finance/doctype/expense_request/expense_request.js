frappe.ui.form.on('Expense Request', {
  refresh(frm) {
    if (!frm.doc.docstatus) {
      return;
    }

    if (frm.doc.docstatus === 1 && frm.doc.status === 'Approved') {
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
