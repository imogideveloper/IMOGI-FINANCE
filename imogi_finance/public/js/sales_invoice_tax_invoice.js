frappe.ui.form.on('Sales Invoice', {
  refresh(frm) {
    const ensureSettings = async () => {
      const enabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
      return Boolean(enabled);
    };

    const addOcrButton = async () => {
      const enabled = await ensureSettings();
      if (!enabled || !frm.doc.out_fp_pdf || frm.doc.docstatus === 1) {
        return;
      }

      frm.add_custom_button(__('Run OCR'), async () => {
        await frappe.call({
          method: 'imogi_finance.api.tax_invoice.run_ocr_for_sales_invoice',
          args: { si_name: frm.doc.name },
          freeze: true,
          freeze_message: __('Queueing OCR...'),
        });
        frappe.show_alert({ message: __('OCR queued.'), indicator: 'green' });
        frm.reload_doc();
      }, __('Tax Invoice'));
    };

    const addVerifyButton = () => {
      const hasData =
        frm.doc.out_fp_no ||
        frm.doc.out_buyer_tax_id ||
        frm.doc.out_fp_dpp ||
        frm.doc.out_fp_ppn ||
        frm.doc.out_fp_ocr_status === 'Done';

      if (!hasData) {
        return;
      }

      frm.add_custom_button(__('Verify Tax Invoice'), async () => {
        const r = await frappe.call({
          method: 'imogi_finance.api.tax_invoice.verify_sales_invoice_tax_invoice',
          args: { si_name: frm.doc.name },
          freeze: true,
          freeze_message: __('Verifying...'),
        });

        if (r && r.message) {
          frappe.show_alert({ message: __('Verification status: {0}', [r.message.status]), indicator: 'green' });
          frm.reload_doc();
        }
      }, __('Tax Invoice'));
    };

    addOcrButton();
    addVerifyButton();
  },
});
