const TAX_INVOICE_OCR_GROUP = __('Tax Invoice OCR');

async function refreshUploadStatus(frm) {
	if (frm.is_new()) return;

	await frm.call('refresh_status');
	await frm.reload_doc();
}

frappe.ui.form.on('Tax Invoice OCR Upload', {
	async refresh(frm) {
		const enabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
		if (!enabled || frm.is_new()) {
			return;
		}

		frm.add_custom_button(__('Refresh OCR Status'), async () => {
			await refreshUploadStatus(frm);
		}, TAX_INVOICE_OCR_GROUP);

		if (frm.doc.tax_invoice_pdf) {
			frm.add_custom_button(__('Run OCR'), async () => {
				await frappe.call({
					method: 'imogi_finance.api.tax_invoice.run_ocr_for_upload',
					args: { upload_name: frm.doc.name },
					freeze: true,
					freeze_message: __('Queueing OCR...'),
				});
				frappe.show_alert({ message: __('OCR queued.'), indicator: 'green' });
				await refreshUploadStatus(frm);
			}, TAX_INVOICE_OCR_GROUP);
		}

		frm.add_custom_button(__('Verify Tax Invoice'), async () => {
			await frappe.call({
				method: 'imogi_finance.api.tax_invoice.verify_tax_invoice_upload',
				args: { upload_name: frm.doc.name },
				freeze: true,
				freeze_message: __('Verifying Tax Invoice...'),
			});
			frappe.show_alert({ message: __('Tax Invoice verification queued.'), indicator: 'green' });
			await refreshUploadStatus(frm);
		}, TAX_INVOICE_OCR_GROUP);
	},
});
