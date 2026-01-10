frappe.provide('imogi_finance');
frappe.require('/assets/imogi_finance/js/tax_invoice_fields.js');

const TAX_INVOICE_MODULE = imogi_finance?.tax_invoice || {};
const DEFAULT_COPY_KEYS = [
  'fp_no',
  'fp_date',
  'npwp',
  'dpp',
  'ppn',
  'ppnbm',
  'ppn_type',
  'status',
  'notes',
  'duplicate_flag',
  'npwp_match',
];
const DEFAULT_SI_FIELDS = {
  fp_no: 'out_fp_no',
  fp_date: 'out_fp_date',
  npwp: 'out_fp_npwp',
  dpp: 'out_fp_dpp',
  ppn: 'out_fp_ppn',
  ppnbm: 'out_fp_ppnbm',
  ppn_type: 'out_fp_ppn_type',
  status: 'out_fp_status',
  notes: 'out_fp_verification_notes',
  duplicate_flag: 'out_fp_duplicate_flag',
  npwp_match: 'out_fp_npwp_match',
  ocr_status: 'out_fp_ocr_status',
  ocr_confidence: 'out_fp_ocr_confidence',
  ocr_raw_json: 'out_fp_ocr_raw_json',
  tax_invoice_pdf: 'out_fp_tax_invoice_pdf',
};
const DEFAULT_UPLOAD_FIELDS = {
  fp_no: 'fp_no',
  fp_date: 'fp_date',
  npwp: 'npwp',
  dpp: 'dpp',
  ppn: 'ppn',
  ppnbm: 'ppnbm',
  ppn_type: 'ppn_type',
  status: 'verification_status',
  notes: 'verification_notes',
  duplicate_flag: 'duplicate_flag',
  npwp_match: 'npwp_match',
  ocr_status: 'ocr_status',
  ocr_confidence: 'ocr_confidence',
  ocr_raw_json: 'ocr_raw_json',
  tax_invoice_pdf: 'tax_invoice_pdf',
};

const SI_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Sales Invoice')) || DEFAULT_SI_FIELDS;
const UPLOAD_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Tax Invoice OCR Upload')) || DEFAULT_UPLOAD_FIELDS;
const COPY_KEYS = (TAX_INVOICE_MODULE.getSharedCopyKeys && TAX_INVOICE_MODULE.getSharedCopyKeys('Tax Invoice OCR Upload', 'Sales Invoice'))
  || DEFAULT_COPY_KEYS;

async function syncSiUpload(frm) {
  if (!frm.doc.out_fp_tax_invoice_upload) {
    return;
  }
  const upload = await frappe.db.get_doc('Tax Invoice OCR Upload', frm.doc.out_fp_tax_invoice_upload);
  const updates = {};
  COPY_KEYS.forEach((key) => {
    const sourceField = UPLOAD_TAX_INVOICE_FIELDS[key];
    const targetField = SI_TAX_INVOICE_FIELDS[key];
    if (!sourceField || !targetField) {
      return;
    }
    updates[targetField] = upload[sourceField] || null;
  });
  if (updates.out_fp_npwp) {
    updates.out_buyer_tax_id = updates.out_fp_npwp;
  }
  await frm.set_value(updates);
}

function lockSiTaxInvoiceFields(frm) {
  Object.values(SI_TAX_INVOICE_FIELDS).forEach((field) => {
    frm.set_df_property(field, 'read_only', true);
  });
}

function setSiUploadQuery(frm) {
  frm.set_query('out_fp_tax_invoice_upload', () => ({
    filters: {
      verification_status: 'Verified',
    },
  }));
}

async function showTaxInvoiceSyncStatus(frm) {
  const { message } = await frappe.call({
    method: 'imogi_finance.services.tax_invoice_service.check_sales_invoice_tax_invoice_status',
    args: { sales_invoice: frm.doc.name },
    freeze: true,
    freeze_message: __('Checking sync status...'),
  });

  if (!message) {
    return;
  }

  const rows = [
    __('Sales Invoice: {0}', [frm.doc.name]),
    __('Sync Status: {0}', [message.synch_status || message.status || __('Unknown')]),
  ];

  if (message.tax_invoice_no) {
    rows.push(__('Tax Invoice No: {0}', [message.tax_invoice_no]));
  }
  if (message.tax_invoice_date) {
    rows.push(__('Tax Invoice Date: {0}', [message.tax_invoice_date]));
  }
  if (message.customer_npwp) {
    rows.push(__('Customer NPWP: {0}', [message.customer_npwp]));
  }
  if (message.invoice_pdf) {
    rows.push(__('PDF: {0}', [message.invoice_pdf]));
  }
  if (message.sync_error) {
    rows.push(__('Last Error: {0}', [message.sync_error]));
  }

  frappe.msgprint({
    title: __('Tax Invoice Sync'),
    message: rows.join('<br>'),
    indicator: message.status === 'Synced' ? 'green' : message.status === 'Error' ? 'red' : 'orange',
  });

  await frm.reload_doc();
}

function addSyncCheckButton(frm) {
  if (frm.is_new()) {
    return;
  }
  frm.add_custom_button(__('Cek Sinkronisasi Faktur Pajak'), async () => {
    await showTaxInvoiceSyncStatus(frm);
  }, __('Tax Invoice'));
}

function maybeAddPaymentLetterButton(frm) {
  if (frm.is_new() || frm.doc.docstatus !== 1) {
    return;
  }

  frm.add_custom_button(
    __('Payment Letter'),
    () => {
      frappe.call({
        method: 'imogi_finance.overrides.sales_invoice.get_sales_invoice_payment_letter',
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

frappe.ui.form.on('Sales Invoice', {
  async refresh(frm) {
    lockSiTaxInvoiceFields(frm);
    setSiUploadQuery(frm);
    await syncSiUpload(frm);

    const ensureSettings = async () => {
      const enabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
      return Boolean(enabled);
    };

    const addOcrButton = async () => {
      const enabled = await ensureSettings();
      if (!enabled || !frm.doc.out_fp_tax_invoice_upload || frm.doc.docstatus === 1) {
        return;
      }

      frm.add_custom_button(__('Run OCR'), async () => {
        await frappe.call({
          method: 'imogi_finance.api.tax_invoice.run_ocr_for_upload',
          args: { upload_name: frm.doc.out_fp_tax_invoice_upload },
          freeze: true,
          freeze_message: __('Queueing OCR...'),
        });
        frappe.show_alert({ message: __('OCR queued.'), indicator: 'green' });
        await syncSiUpload(frm);
      }, __('Tax Invoice'));
    };

    const addUploadButtons = () => {
      if (!frm.doc.out_fp_tax_invoice_upload) {
        return;
      }

      frm.add_custom_button(__('Open Tax Invoice Upload'), () => {
        frappe.set_route('Form', 'Tax Invoice OCR Upload', frm.doc.out_fp_tax_invoice_upload);
      }, __('Tax Invoice'));

      frm.add_custom_button(__('Refresh Tax Invoice Data'), async () => {
        await frappe.call({
          method: 'imogi_finance.api.tax_invoice.apply_tax_invoice_upload',
          args: { target_doctype: 'Sales Invoice', target_name: frm.doc.name },
          freeze: true,
          freeze_message: __('Refreshing...'),
        });
        await frm.reload_doc();
      }, __('Tax Invoice'));
    };

    addOcrButton();
    addUploadButtons();
    addSyncCheckButton(frm);
    maybeAddPaymentLetterButton(frm);
  },

  async out_fp_tax_invoice_upload(frm) {
    await syncSiUpload(frm);
  },
});
