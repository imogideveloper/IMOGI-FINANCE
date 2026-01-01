frappe.ui.form.on('Purchase Invoice', {
  refresh(frm) {
    const ensureSettings = async () => {
      const enabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
      return Boolean(enabled);
    };

    const addOcrButton = async () => {
      const enabled = await ensureSettings();
      if (!enabled || !frm.doc.ti_tax_invoice_pdf || frm.doc.docstatus === 1) {
        return;
      }

      frm.add_custom_button(__('Run OCR'), async () => {
        await frappe.call({
          method: 'imogi_finance.api.tax_invoice.run_ocr_for_purchase_invoice',
          args: { pi_name: frm.doc.name },
          freeze: true,
          freeze_message: __('Queueing OCR...'),
        });
        frappe.show_alert({ message: __('OCR queued.'), indicator: 'green' });
        frm.reload_doc();
      });
    };

    const addVerifyButton = () => {
      if (frm.doc.docstatus === 1) {
        return;
      }

      const hasData = frm.doc.ti_fp_no || frm.doc.ti_fp_npwp || frm.doc.ti_fp_dpp || frm.doc.ti_fp_ppn;
      if (!hasData && frm.doc.ti_ocr_status !== 'Done') {
        return;
      }

      frm.add_custom_button(__('Verify Tax Invoice'), async () => {
        const r = await frappe.call({
          method: 'imogi_finance.api.tax_invoice.verify_purchase_invoice_tax_invoice',
          args: { pi_name: frm.doc.name },
          freeze: true,
          freeze_message: __('Verifying...'),
        });

        if (r && r.message) {
          frappe.show_alert({ message: __('Verification status: {0}', [r.message.status]), indicator: 'green' });
          frm.reload_doc();
        }
      });
    };

    addOcrButton();
    addVerifyButton();
  },
});
