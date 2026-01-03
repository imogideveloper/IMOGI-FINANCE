(() => {
  frappe.provide('imogi_finance.tax_invoice');

  const DEFAULT_FIELD_MAPS = {
    'Purchase Invoice': {
      fp_no: 'ti_fp_no',
      fp_date: 'ti_fp_date',
      npwp: 'ti_fp_npwp',
      dpp: 'ti_fp_dpp',
      ppn: 'ti_fp_ppn',
      ppnbm: 'ti_fp_ppnbm',
      ppn_type: 'ti_fp_ppn_type',
      status: 'ti_verification_status',
      notes: 'ti_verification_notes',
      duplicate_flag: 'ti_duplicate_flag',
      npwp_match: 'ti_npwp_match',
      ocr_status: 'ti_ocr_status',
      ocr_confidence: 'ti_ocr_confidence',
      ocr_raw_json: 'ti_ocr_raw_json',
      tax_invoice_pdf: 'ti_tax_invoice_pdf',
    },
    'Expense Request': {
      fp_no: 'ti_fp_no',
      fp_date: 'ti_fp_date',
      npwp: 'ti_fp_npwp',
      dpp: 'ti_fp_dpp',
      ppn: 'ti_fp_ppn',
      ppnbm: 'ti_fp_ppnbm',
      ppn_type: 'ti_fp_ppn_type',
      status: 'ti_verification_status',
      notes: 'ti_verification_notes',
      duplicate_flag: 'ti_duplicate_flag',
      npwp_match: 'ti_npwp_match',
      ocr_status: 'ti_ocr_status',
      ocr_confidence: 'ti_ocr_confidence',
      ocr_raw_json: 'ti_ocr_raw_json',
      tax_invoice_pdf: 'ti_tax_invoice_pdf',
    },
    'Branch Expense Request': {
      fp_no: 'ti_fp_no',
      fp_date: 'ti_fp_date',
      npwp: 'ti_fp_npwp',
      dpp: 'ti_fp_dpp',
      ppn: 'ti_fp_ppn',
      ppnbm: 'ti_fp_ppnbm',
      ppn_type: 'ti_fp_ppn_type',
      status: 'ti_verification_status',
      notes: 'ti_verification_notes',
      duplicate_flag: 'ti_duplicate_flag',
      npwp_match: 'ti_npwp_match',
      ocr_status: 'ti_ocr_status',
      ocr_confidence: 'ti_ocr_confidence',
      ocr_raw_json: 'ti_ocr_raw_json',
      tax_invoice_pdf: 'ti_tax_invoice_pdf',
    },
    'Sales Invoice': {
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
    },
    'Tax Invoice OCR Upload': {
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
    },
  };

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

  const DATA = {
    fieldMaps: { ...DEFAULT_FIELD_MAPS },
    copyKeys: [...DEFAULT_COPY_KEYS],
  };

  const JSON_URL = '/assets/imogi_finance/json/tax_invoice_field_maps.json';
  const DEFAULT_FALLBACK = 'Purchase Invoice';

  const normalizeFieldMaps = (maybeMaps) => {
    if (!maybeMaps || typeof maybeMaps !== 'object') {
      return;
    }

    Object.entries(maybeMaps).forEach(([doctype, mapping]) => {
      if (!mapping || typeof mapping !== 'object') {
        return;
      }

      DATA.fieldMaps[doctype] = { ...mapping };
    });
  };

  const maybeLoadFromJson = async () => {
    try {
      const response = await fetch(JSON_URL, { credentials: 'same-origin' });
      if (!response.ok) {
        return;
      }

      const payload = await response.json();
      normalizeFieldMaps(payload?.field_maps || payload?.fieldMaps);
      if (Array.isArray(payload?.copy_keys || payload?.copyKeys)) {
        DATA.copyKeys = [...(payload.copy_keys || payload.copyKeys)];
      }
    } catch (error) {
      // eslint-disable-next-line no-console
      console.warn('Unable to load tax invoice field maps JSON', error);
    }
  };

  const getFieldMap = (doctype) => {
    const mapping = DATA.fieldMaps[doctype] || DATA.fieldMaps[DEFAULT_FALLBACK];
    return { ...mapping };
  };

  const getFieldMaps = () => ({ ...DATA.fieldMaps });

  const getCopyKeys = () => [...DATA.copyKeys];

  const getSharedCopyKeys = (sourceDoctype, targetDoctype) => {
    const sourceMap = getFieldMap(sourceDoctype);
    const targetMap = getFieldMap(targetDoctype);
    return getCopyKeys().filter((key) => sourceMap[key] && targetMap[key]);
  };

  imogi_finance.tax_invoice.getFieldMap = getFieldMap;
  imogi_finance.tax_invoice.getFieldMaps = getFieldMaps;
  imogi_finance.tax_invoice.getCopyKeys = getCopyKeys;
  imogi_finance.tax_invoice.getSharedCopyKeys = getSharedCopyKeys;

  // Fire-and-forget JSON refresh to keep JS maps aligned with Python.
  maybeLoadFromJson();
})(); 
