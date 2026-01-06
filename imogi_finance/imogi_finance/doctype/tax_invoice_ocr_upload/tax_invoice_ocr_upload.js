const TAX_INVOICE_OCR_GROUP = __('Tax Invoice OCR');

async function refreshUploadStatus(frm) {
	if (frm.is_new()) return;

	await frappe.call({
		method: 'imogi_finance.api.tax_invoice.monitor_tax_invoice_ocr',
		args: { docname: frm.doc.name, doctype: 'Tax Invoice OCR Upload' },
	});
	await frm.reload_doc();
}

frappe.ui.form.on('Tax Invoice OCR Upload', {
	async refresh(frm) {
		let providerReady = true;
		let providerError = null;
		let enabled = false;

		try {
			const { message } = await frappe.call({
				method: 'imogi_finance.api.tax_invoice.get_tax_invoice_upload_context_api',
				args: { target_doctype: 'Tax Invoice OCR Upload', target_name: frm.doc.name },
			});
			enabled = Boolean(message?.enable_tax_invoice_ocr);
			providerReady = Boolean(message?.provider_ready ?? true);
			providerError = message?.provider_error || null;
		} catch (error) {
			enabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
		}

		if (!enabled || frm.is_new()) {
			return;
		}

		if (providerReady === false) {
			const message = providerError
				? __('OCR cannot run: {0}', [providerError])
				: __('OCR provider is not configured.');
			frm.dashboard.set_headline(`<span class="indicator red">${message}</span>`);
		}

		frm.add_custom_button(__('Refresh OCR Status'), async () => {
			await refreshUploadStatus(frm);
		}, TAX_INVOICE_OCR_GROUP);

		if (frm.doc.tax_invoice_pdf && providerReady !== false) {
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
