frappe.ui.form.on('BCA Bank Statement Import', {
  refresh(frm) {
    if (!frm.doc.company || !frm.doc.bank_account) {
      frm.dashboard.clear_headline();
      frm.dashboard.set_headline(__("Set Company and Bank Account to enable parsing."));
    }

    if (!frm.is_new()) {
      frm.add_custom_button(__('Parse CSV BCA'), () => {
        frm.call('parse_csv').then(() => frm.reload_doc());
      }, __('Actions'));

      frm.add_custom_button(__('Convert to Bank Transaction'), () => {
        frm.call('convert_to_bank_transaction').then(() => frm.reload_doc());
      }, __('Actions'));

      frm.add_custom_button(__('Open Bank Reconciliation Tool'), () => {
        frappe.route_options = {
          company: frm.doc.company,
          bank_account: frm.doc.bank_account,
        };
        frappe.set_route('bank-reconciliation');
      });
    }
  },
});
