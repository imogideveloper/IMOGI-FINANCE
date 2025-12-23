frappe.ui.form.on('Bank Transaction', {
  refresh(frm) {
    if (frm.doc.docstatus !== 1 || frm.doc.status !== 'Unreconciled') return;

    if (frm.page.btn_secondary && frm.page.btn_secondary.get(0)?.innerText?.trim() === __('Cancel')) {
      frm.page.btn_secondary.hide();
    }

    (frm.page.secondary_actions || [])
      .filter((action) => action && action.label === __('Cancel'))
      .forEach((action) => action.hide && action.hide());
  },
});
