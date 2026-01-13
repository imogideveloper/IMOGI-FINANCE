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
const DEFAULT_ER_FIELDS = {
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

const ER_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Expense Request')) || DEFAULT_ER_FIELDS;
const UPLOAD_TAX_INVOICE_FIELDS = (TAX_INVOICE_MODULE.getFieldMap && TAX_INVOICE_MODULE.getFieldMap('Tax Invoice OCR Upload')) || DEFAULT_UPLOAD_FIELDS;
const COPY_KEYS = (TAX_INVOICE_MODULE.getSharedCopyKeys && TAX_INVOICE_MODULE.getSharedCopyKeys('Tax Invoice OCR Upload', 'Expense Request'))
  || DEFAULT_COPY_KEYS;

async function syncErUpload(frm) {
  if (!frm.doc.ti_tax_invoice_upload) {
    return;
  }
  const cachedUpload = frm.taxInvoiceUploadCache?.[frm.doc.ti_tax_invoice_upload];
  const upload = cachedUpload || await frappe.db.get_doc('Tax Invoice OCR Upload', frm.doc.ti_tax_invoice_upload);
  const updates = {};
  COPY_KEYS.forEach((key) => {
    const sourceField = UPLOAD_TAX_INVOICE_FIELDS[key];
    const targetField = ER_TAX_INVOICE_FIELDS[key];
    if (!sourceField || !targetField) {
      return;
    }
    updates[targetField] = upload[sourceField] ?? null;
  });
  await frm.set_value(updates);
}

function lockErTaxInvoiceFields(frm) {
  Object.values(ER_TAX_INVOICE_FIELDS).forEach((field) => {
    frm.set_df_property(field, 'read_only', true);
  });
}

function hideErOcrStatus(frm) {
  if (frm.fields_dict?.ti_ocr_status) {
    frm.set_df_property('ti_ocr_status', 'hidden', true);
  }
}

function setExpenseAccountQuery(frm) {
  const filters = { root_type: 'Expense', is_group: 0 };
  frm.set_query('expense_account', () => ({ filters }));
  frm.set_query('expense_account', 'items', () => ({ filters }));
}

function toggleAssetItemsBehavior(frm) {
  const isAsset = frm.doc.request_type === 'Asset';
  const useCumulative = Boolean(frm.doc.build_cumulative_asset_from_items);
  const assetItemsField = frm.get_field('asset_items');
  const shouldLock = isAsset && useCumulative;

  frm.set_df_property('asset_items_section', 'hidden', !isAsset);
  frm.set_df_property('asset_items', 'read_only', shouldLock);

  if (assetItemsField?.grid) {
    assetItemsField.grid.cannot_add_rows = shouldLock;
    assetItemsField.grid.cannot_delete_rows = shouldLock;
    assetItemsField.grid.only_sortable = !shouldLock;
  }
}

function formatCurrency(frm, value) {
  return frappe.format(value, { fieldtype: 'Currency', options: frm.doc.currency });
}

async function setPphRate(frm) {
  if (!frm.doc.pph_type) {
    frm._pph_rate = 0;
    return;
  }

  try {
    const { message } = await frappe.call({
      method: 'imogi_finance.imogi_finance.doctype.expense_request.expense_request.get_pph_rate',
      args: { pph_type: frm.doc.pph_type },
    });
    frm._pph_rate = message?.rate || 0;
  } catch (error) {
    frm._pph_rate = 0;
  }
}

function computeTotals(frm) {
  const flt = (frappe.utils && frappe.utils.flt) || window.flt || ((value) => parseFloat(value) || 0);
  const totalExpense = flt(frm.doc.amount || 0);
  const totalAsset = (frm.doc.asset_items || []).reduce(
    (sum, row) => sum + flt(row.amount || 0),
    0,
  );
  const itemPphTotal = (frm.doc.items || []).reduce(
    (sum, row) => sum + (row.is_pph_applicable ? flt(row.pph_base_amount || 0) : 0),
    0,
  );
  const totalPpn = flt(frm.doc.ti_fp_ppn || frm.doc.ppn || 0);
  const totalPpnbm = flt(frm.doc.ti_fp_ppnbm || frm.doc.ppnbm || 0);
  const pphBaseTotal = itemPphTotal
    || (frm.doc.is_pph_applicable ? flt(frm.doc.pph_base_amount || 0) : 0);
  const pphRate = flt(frm._pph_rate || 0);
  const totalPph = pphRate ? (pphBaseTotal * pphRate) / 100 : pphBaseTotal;
  const totalAmount = totalExpense + totalAsset + totalPpn + totalPpnbm + totalPph;

  return {
    totalExpense,
    totalAsset,
    totalPpn,
    totalPpnbm,
    totalPph,
    totalAmount,
  };
}

function renderTotalsHtml(frm, totals) {
  const rows = [
    ['Total Expense', totals.totalExpense],
    ['Total Asset', totals.totalAsset],
    ['Total PPN', totals.totalPpn],
    ['Total PPnBM', totals.totalPpnbm],
    ['Total PPh', totals.totalPph],
    ['Total', totals.totalAmount],
  ];

  const cells = rows
    .map(
      ([label, value]) => `
        <tr>
          <td>${frappe.utils.escape_html(label)}</td>
          <td class="text-right">${formatCurrency(frm, value)}</td>
        </tr>
      `,
    )
    .join('');

  return `<table class="table table-bordered table-sm"><tbody>${cells}</tbody></table>`;
}

function updateTotalsSummary(frm) {
  const totals = computeTotals(frm);
  const fields = {
    total_expense: totals.totalExpense,
    total_asset: totals.totalAsset,
    total_ppn: totals.totalPpn,
    total_ppnbm: totals.totalPpnbm,
    total_pph: totals.totalPph,
    total_amount: totals.totalAmount,
  };

  Object.entries(fields).forEach(([field, value]) => {
    if (!frm.fields_dict[field]) {
      return;
    }
    if (frm.doc[field] !== value) {
      frm.doc[field] = value;
      frm.refresh_field(field);
    }
  });

  const html = renderTotalsHtml(frm, totals);
  ['items_totals_html', 'asset_totals_html'].forEach((fieldname) => {
    const field = frm.fields_dict[fieldname];
    if (field?.$wrapper) {
      field.$wrapper.html(html);
    }
  });
}

function canSubmitExpenseRequest(frm) {
  if (frm.is_new()) {
    return false;
  }

  if (frm.doc.docstatus !== 0) {
    return false;
  }

  if (frm.doc.owner === frappe.session.user) {
    return true;
  }

  return frappe.user.has_role('Expense Approver') || frappe.user.has_role('System Manager');
}

function maybeRenderPrimarySubmitButton(frm) {
  frm.remove_custom_button(__('Submit'));

  if (!canSubmitExpenseRequest(frm)) {
    return;
  }

  const submitBtn = frm.add_custom_button(__('Submit'), () => frm.save('Submit'));
  submitBtn.addClass('btn-primary');
}

async function setErUploadQuery(frm) {
  let usedUploads = [];
  let verifiedUploads = [];
  let providerReady = true;
  let providerError = null;

  try {
    const { message } = await frappe.call({
      method: 'imogi_finance.api.tax_invoice.get_tax_invoice_upload_context_api',
      args: { target_doctype: 'Expense Request', target_name: frm.doc.name },
    });
    usedUploads = message?.used_uploads || [];
    verifiedUploads = message?.verified_uploads || [];
    providerReady = Boolean(message?.provider_ready ?? true);
    providerError = message?.provider_error || null;
  } catch (error) {
    console.error('Unable to load available Tax Invoice uploads', error);
  }

  frm.taxInvoiceProviderReady = providerReady;
  frm.taxInvoiceProviderError = providerError;

  frm.taxInvoiceUploadCache = (verifiedUploads || []).reduce((acc, upload) => {
    acc[upload.name] = upload;
    return acc;
  }, {});

  frm.set_query('ti_tax_invoice_upload', () => ({
    filters: {
      verification_status: 'Verified',
      ...(usedUploads.length ? { name: ['not in', usedUploads] } : {}),
    },
  }));
}

function maybeAddDeferredExpenseActions(frm) {
  if (!frm.doc.is_deferred_expense) {
    return;
  }

  frm.add_custom_button(__('Show Amortization Schedule'), async () => {
    if (!frm.doc.deferred_start_date) {
      frappe.msgprint(__('Deferred Start Date is required to generate the amortization schedule.'));
      return;
    }

    if (!frm.doc.deferred_periods || frm.doc.deferred_periods <= 0) {
      frappe.msgprint(__('Deferred Periods must be greater than zero to generate the amortization schedule.'));
      return;
    }

    const { message } = await frappe.call({
      method: 'imogi_finance.services.deferred_expense.generate_amortization_schedule',
      args: {
        amount: frm.doc.amount,
        periods: frm.doc.deferred_periods,
        start_date: frm.doc.deferred_start_date,
      },
    });

    const schedule = message || [];
    const pretty = Array.isArray(schedule) ? JSON.stringify(schedule, null, 2) : String(schedule);
    frappe.msgprint({
      title: __('Amortization Schedule'),
      message: `<pre style="white-space: pre-wrap;">${pretty}</pre>`,
      indicator: 'blue',
    });
  }, __('Actions'));
}

function maybeRenderCancelDeleteActions(frm) {
  if (frm.is_new()) {
    return;
  }

  const isSubmitted = frm.doc.docstatus === 1;
  const isCancelled = frm.doc.docstatus === 2;
  const canDelete = frm.doc.docstatus === 0 || isCancelled;

  if (isSubmitted) {
    frm.add_custom_button(__('Cancel'), () => {
      frappe.confirm(
        __('Are you sure you want to cancel this Expense Request?'),
        async () => {
          try {
            await frm.cancel();
          } catch (error) {
            frappe.msgprint({
              title: __('Error'),
              message: error?.message || __('Failed to cancel Expense Request.'),
              indicator: 'red',
            });
          }
        }
      );
    }, __('Actions'));
  }

  if (canDelete) {
    frm.add_custom_button(__('Delete'), () => {
      frappe.confirm(
        __('Are you sure you want to delete this Expense Request?'),
        async () => {
          try {
            await frappe.call({
              method: 'frappe.client.delete',
              args: {
                doctype: frm.doc.doctype,
                name: frm.doc.name,
              },
              freeze: true,
              freeze_message: __('Deleting Expense Request...'),
            });
            frappe.show_alert({
              message: __('Expense Request deleted.'),
              indicator: 'green',
            }, 5);
            frappe.set_route('List', frm.doc.doctype);
          } catch (error) {
            frappe.msgprint({
              title: __('Error'),
              message: error?.message || __('Failed to delete Expense Request.'),
              indicator: 'red',
            });
          }
        }
      );
    }, __('Actions'));
  }
}

frappe.ui.form.on('Expense Request', {
  async refresh(frm) {
    hideErOcrStatus(frm);
    lockErTaxInvoiceFields(frm);
    setExpenseAccountQuery(frm);
    toggleAssetItemsBehavior(frm);
    frm.dashboard.clear_headline();
    await setErUploadQuery(frm);
    await syncErUpload(frm);
    await setPphRate(frm);
    maybeAddDeferredExpenseActions(frm);
    maybeRenderCancelDeleteActions(frm);
    maybeRenderPrimarySubmitButton(frm);
    updateTotalsSummary(frm);

    const addCheckRouteButton = () => {
      if (!frm.doc.cost_center) {
        return;
      }

      const routeBtn = frm.add_custom_button(__('Check Approval Route'), async () => {
        const stringify = (value) => JSON.stringify(value || []);

        try {
          routeBtn?.prop?.('disabled', true);
        } catch (error) {
          // ignore if prop is not available
        }

        try {
          const { message } = await frappe.call({
            method: 'imogi_finance.approval.check_expense_request_route',
            args: {
              cost_center: frm.doc.cost_center,
              items: stringify(frm.doc.items),
              expense_accounts: stringify(frm.doc.expense_accounts),
              amount: frm.doc.amount,
              docstatus: frm.doc.docstatus,
            },
          });

          if (message?.ok) {
            const route = message.route || {};
            const rows = ['1', '2', '3']
              .map((level) => {
                const info = route[`level_${level}`] || {};
                if (!info.role && !info.user) {
                  return null;
                }
                const role = info.role ? __('Role: {0}', [info.role]) : '';
                const user = info.user ? __('User: {0}', [info.user]) : '';
                const details = [role, user].filter(Boolean).join(' | ');
                return `<li>${__('Level {0}', [level])}: ${details}</li>`;
              })
              .filter(Boolean)
              .join('');

            let messageContent = rows
              ? `<ul>${rows}</ul>`
              : __('No approver configured for the current route.');

            frappe.msgprint({
              title: __('Approval Route'),
              message: messageContent,
              indicator: 'green',
            });
            return;
          }

          // Handle validation errors (including invalid users)
          let indicator = 'orange';
          let errorMessage = message?.message
            ? message.message
            : __('Approval route could not be determined. Please ask your System Manager to configure an Expense Approval Setting.');

          // Show red indicator for user validation errors
          if (message?.user_validation && !message.user_validation.valid) {
            indicator = 'red';

            // Build detailed error message
            const details = [];

            if (message.user_validation.invalid_users?.length) {
              details.push(
                '<strong>' + __('Users not found:') + '</strong><ul>' +
                message.user_validation.invalid_users.map(u =>
                  `<li>${__('Level {0}', [u.level])}: <code>${u.user}</code></li>`
                ).join('') +
                '</ul>'
      );
    }

            if (message.user_validation.disabled_users?.length) {
              details.push(
                '<strong>' + __('Users disabled:') + '</strong><ul>' +
                message.user_validation.disabled_users.map(u =>
                  `<li>${__('Level {0}', [u.level])}: <code>${u.user}</code></li>`
                ).join('') +
                '</ul>'
              );
      }

            if (details.length) {
              errorMessage = details.join('<br>') +
                '<br><br>' + __('Please update the Expense Approval Setting to use valid, active users.');
            }
          }
            frappe.msgprint({
            title: __('Approval Route'),
            message: errorMessage,
            indicator: indicator,
            });
        } catch (error) {
          frappe.msgprint({
            title: __('Approval Route'),
            message: error?.message
              ? error.message
              : __('Unable to check approval route right now. Please try again.'),
            indicator: 'red',
          });
        } finally {
          try {
            routeBtn?.prop?.('disabled', false);
          } catch (error) {
            // ignore if prop is not available
          }
        }
      }, __('Actions'));
    };

    addCheckRouteButton();

    if (!frm.doc.docstatus) {
      maybeRenderInternalChargeButton(frm);
      return;
    }

    maybeRenderInternalChargeButton(frm);

    const isSubmitted = frm.doc.docstatus === 1;
    if (frm.doc.status === 'Approved') {
      frm.dashboard.set_headline(
        '<span class="indicator orange">' +
        __('Expense Request is Approved. Ready to create Purchase Invoice.') +
        '</span>'
      );
    } else if (frm.doc.status === 'PI Created') {
      frm.dashboard.set_headline(
        '<span class="indicator blue">' +
        __('Purchase Invoice {0} created. Awaiting payment.', [frm.doc.linked_purchase_invoice]) +
        '</span>'
      );
    } else if (frm.doc.status === 'Paid') {
      frm.dashboard.set_headline(
        '<span class="indicator green">' +
        __('Expense Request completed and paid.') +
        '</span>'
      );
    }

    if (isSubmitted && frm.doc.status === 'Approved' && !frm.doc.linked_purchase_invoice) {
      await maybeRenderPurchaseInvoiceButton(frm);
    }

    // Tax Invoice OCR actions are intentionally managed from the OCR Upload doctype.
  },
  items_add(frm) {
    updateTotalsSummary(frm);
  },
  items_remove(frm) {
    updateTotalsSummary(frm);
  },
  asset_items_add(frm) {
    updateTotalsSummary(frm);
  },
  asset_items_remove(frm) {
    updateTotalsSummary(frm);
  },
  ti_fp_ppn(frm) {
    updateTotalsSummary(frm);
  },
  ti_fp_ppnbm(frm) {
    updateTotalsSummary(frm);
  },
  async pph_type(frm) {
    await setPphRate(frm);
    updateTotalsSummary(frm);
  },
  pph_base_amount(frm) {
    updateTotalsSummary(frm);
  },
  is_pph_applicable(frm) {
    updateTotalsSummary(frm);
  },

  async ti_tax_invoice_upload(frm) {
    await syncErUpload(frm);
  },
  request_type(frm) {
    toggleAssetItemsBehavior(frm);
  },
  build_cumulative_asset_from_items(frm) {
    toggleAssetItemsBehavior(frm);
  },
});

function maybeRenderInternalChargeButton(frm) {
  const requiresInternalCharge = frm.doc.allocation_mode === 'Allocated via Internal Charge';
  const hasInternalCharge = Boolean(frm.doc.internal_charge_request);

  if (!requiresInternalCharge) {
    return;
  }

  if (hasInternalCharge) {
    frm.dashboard.add_indicator(__('Internal Charge {0}', [frm.doc.internal_charge_request]), 'green');
    return;
  }

  frm.dashboard.add_indicator(__('Internal Charge not generated'), 'orange');

  frm.add_custom_button(__('Generate Internal Charge'), async () => {
    try {
      const { message } = await frappe.call({
        method: 'imogi_finance.budget_control.workflow.create_internal_charge_from_expense_request',
        args: { er_name: frm.doc.name },
        freeze: true,
        freeze_message: __('Generating Internal Charge...'),
      });

      if (message) {
        frappe.show_alert({ message: __('Internal Charge Request {0} created.', [message]), indicator: 'green' });
        await frm.reload_doc();
      }
    } catch (error) {
      frappe.msgprint({
        title: __('Unable to Generate Internal Charge'),
        message: error?.message || __('An unexpected error occurred. Please try again.'),
        indicator: 'red',
      });
    }
  }, __('Actions'));
}

async function maybeRenderPurchaseInvoiceButton(frm) {
  const [ocrEnabled, requireVerified] = await Promise.all([
    frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr'),
    frappe.db.get_single_value(
      'Tax Invoice OCR Settings',
      'require_verification_before_create_pi_from_expense_request'
    ),
  ]);

  const isPpnApplicable = Boolean(frm.doc.is_ppn_applicable);
  const gateByVerification = Boolean(ocrEnabled && requireVerified && isPpnApplicable);
  const isVerified = frm.doc.ti_verification_status === 'Verified';
  const allowButton = !gateByVerification || isVerified;

  if (!allowButton) {
    frm.dashboard.add_indicator(
      __('Please verify Tax Invoice before creating Purchase Invoice'),
      'orange'
    );
    return;
  }

  frm.add_custom_button(__('Create Purchase Invoice'), async () => {
    frappe.confirm(
      __('Are you sure you want to create a Purchase Invoice from this Expense Request?'),
      async () => {
        try {
          frappe.show_progress(__('Creating...'), 0, 100);

          const { message } = await frappe.call({
            method: 'imogi_finance.accounting.create_purchase_invoice_from_request',
            args: { expense_request_name: frm.doc.name },
            freeze: true,
            freeze_message: __('Creating Purchase Invoice...'),
          });

          frappe.hide_progress();

          if (message) {
            frappe.show_alert({
              message: __('Purchase Invoice {0} created successfully!', [message]),
              indicator: 'green',
            }, 5);
            frm.reload_doc();
          }
        } catch (error) {
          frappe.hide_progress();
          frappe.msgprint({
            title: __('Error'),
            message: error?.message || __('Failed to create Purchase Invoice'),
            indicator: 'red',
          });
        }
      }
    );
  }, __('Actions'));
}

frappe.ui.form.on('Expense Request Item', {
  amount(frm) {
    updateTotalsSummary(frm);
  },
  pph_base_amount(frm) {
    updateTotalsSummary(frm);
  },
  is_pph_applicable(frm) {
    updateTotalsSummary(frm);
  },
});

frappe.ui.form.on('Expense Request Asset Item', {
  amount(frm) {
    updateTotalsSummary(frm);
  },
  qty(frm) {
    updateTotalsSummary(frm);
  },
});
