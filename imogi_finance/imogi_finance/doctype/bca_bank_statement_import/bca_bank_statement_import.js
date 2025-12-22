frappe.ui.form.on('BCA Bank Statement Import', {
  refresh(frm) {
    if (!frm.doc.company || !frm.doc.bank_account) {
      frm.dashboard.clear_headline();
      frm.dashboard.set_headline(__("Set Company and Bank Account to enable parsing."));
    }

    frm.set_intro(__("Upload BCA → Parse → Convert → buka Bank Reconciliation Tool (otomatis lewat tombol)."));

    if (!frm.is_new()) {
      frm.add_custom_button(__('Parse CSV BCA'), () => {
        frm.call('parse_csv').then(() => frm.reload_doc());
      }, __('Actions'));

      frm.add_custom_button(__('Convert to Bank Transaction'), () => {
        frm.call('convert_to_bank_transaction').then(() => frm.reload_doc());
      }, __('Actions'));

      frm.add_custom_button(__('Open Bank Reconciliation Tool'), () => {
        if (!frm.doc.company || !frm.doc.bank_account) {
          frappe.msgprint(__('Please set Company and Bank Account first.'));
          return;
        }

        const dates = (frm.doc.statement_rows || [])
          .map((row) => row.posting_date)
          .filter(Boolean);

        const from_date = dates.length ? dates.reduce((a, b) => (a < b ? a : b)) : undefined;
        const to_date = dates.length ? dates.reduce((a, b) => (a > b ? a : b)) : undefined;

        const params = new URLSearchParams({
          company: frm.doc.company,
          bank_account: frm.doc.bank_account,
        });

        if (from_date) params.append('from_date', from_date);
        if (to_date) params.append('to_date', to_date);

        const url = frappe.utils.get_url(`/app/bank-reconciliation?${params.toString()}`);
        window.open(url, '_blank');
      });
    }
  },
});
