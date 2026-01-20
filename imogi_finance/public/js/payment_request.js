frappe.ui.form.on('Payment Request', {
  refresh(frm) {
    maybeAddPaymentLetterButton(frm);
  },
});

function maybeAddPaymentLetterButton(frm) {
  if (frm.is_new() || frm.doc.docstatus !== 1) {
    return;
  }

  frm.add_custom_button(
    __('Payment Letter'),
    () => {
      frappe.call({
        method: 'imogi_finance.overrides.payment_request.get_payment_request_payment_letter',
        args: { name: frm.doc.name },
        callback(r) {
          if (!r.exc && r.message) {
            const w = window.open('', '_blank');
            w.document.write(r.message);
            w.document.close();
          }
        },
      });
    },
    __('Print'),
  );
}
