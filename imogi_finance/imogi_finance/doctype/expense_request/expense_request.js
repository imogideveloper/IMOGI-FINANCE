const ER_TAX_INVOICE_FIELDS = {
  fp_no: 'ti_fp_no',
  fp_date: 'ti_fp_date',
  npwp: 'ti_fp_npwp',
  dpp: 'ti_fp_dpp',
  ppn: 'ti_fp_ppn',
  ppnbm: 'ti_fp_ppnbm',
  ppn_type: 'ti_fp_ppn_type',
  verification_status: 'ti_verification_status',
  verification_notes: 'ti_verification_notes',
  duplicate_flag: 'ti_duplicate_flag',
  npwp_match: 'ti_npwp_match',
};

async function syncErUpload(frm) {
  if (!frm.doc.ti_tax_invoice_upload) {
    return;
  }
  const cachedUpload = frm.taxInvoiceUploadCache?.[frm.doc.ti_tax_invoice_upload];
  const upload = cachedUpload || await frappe.db.get_doc('Tax Invoice OCR Upload', frm.doc.ti_tax_invoice_upload);
  const updates = {};
  Object.entries(ER_TAX_INVOICE_FIELDS).forEach(([source, target]) => {
    updates[target] = upload[source] ?? null;
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

async function setErUploadQuery(frm) {
  let usedUploads = [];
  let verifiedUploads = [];

  try {
    const { message } = await frappe.call({
      method: 'imogi_finance.api.tax_invoice.get_tax_invoice_upload_context_api',
      args: { target_doctype: 'Expense Request', target_name: frm.doc.name },
    });
    usedUploads = message?.used_uploads || [];
    verifiedUploads = message?.verified_uploads || [];
  } catch (error) {
    console.error('Unable to load available Tax Invoice uploads', error);
  }

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

frappe.ui.form.on('Expense Request', {
  async refresh(frm) {
    hideErOcrStatus(frm);
    lockErTaxInvoiceFields(frm);
    frm.dashboard.clear_headline();
    await setErUploadQuery(frm);
    await syncErUpload(frm);
    maybeAddDeferredExpenseActions(frm);

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

            frappe.msgprint({
              title: __('Approval Route'),
              message: rows
                ? `<ul>${rows}</ul>`
                : __('No approver configured for the current route.'),
              indicator: 'green',
            });
            return;
          }

          frappe.msgprint({
            title: __('Approval Route'),
            message: message?.message
              ? message.message
              : __('Approval route could not be determined. Please ask your System Manager to configure an Expense Approval Setting.'),
            indicator: 'orange',
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
    const allowedStatuses = ['Approved'];
    const isAllowedStatus = allowedStatuses.includes(frm.doc.status);
    const isLinked = frm.doc.status === 'Linked';
    const hasLinkedPurchaseInvoice = Boolean(frm.doc.linked_purchase_invoice);
    const canCreatePurchaseInvoice = isSubmitted && isAllowedStatus && !hasLinkedPurchaseInvoice;

    const showPurchaseInvoiceAvailability = () => {
      if (hasLinkedPurchaseInvoice) {
        frm.dashboard.set_headline(__('Purchase Invoice {0} already linked to this request.', [
          frm.doc.linked_purchase_invoice,
        ]));
        return;
      }

      if (!isAllowedStatus) {
        frappe.show_alert({
          message: __('Purchase Invoice can be created after this request is Approved.'),
          indicator: 'orange',
        });
      }
    };

    if (isSubmitted && isLinked && hasLinkedPurchaseInvoice) {
      frm.dashboard.set_headline(__('Purchase Invoice {0} already linked to this request.', [
        frm.doc.linked_purchase_invoice,
      ]));
    }

    if (isSubmitted && isAllowedStatus && !hasLinkedPurchaseInvoice) {
      frm.dashboard.set_headline(
        '<span class="indicator orange">' +
        __('Expense Request is Approved and awaiting Purchase Invoice creation.') +
        '</span>',
      );
    }

    const maybeRenderPurchaseInvoiceButton = async () => {
      if (!canCreatePurchaseInvoice) {
        showPurchaseInvoiceAvailability();
        return;
      }

      const [ocrEnabled, requireVerified] = await Promise.all([
        frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr'),
        frappe.db.get_single_value(
          'Tax Invoice OCR Settings',
          'require_verification_before_create_pi_from_expense_request'
        ),
      ]);

      const gateByVerification = Boolean(ocrEnabled && requireVerified);
      const isVerified = frm.doc.ti_verification_status === 'Verified';
      const allowButton = !gateByVerification || isVerified;

      if (!allowButton) {
        frappe.show_alert({
          message: __('Please verify the Tax Invoice before creating a Purchase Invoice.'),
          indicator: 'orange',
        });
        return;
      }

      const purchaseInvoiceBtn = frm.add_custom_button(__('Create Purchase Invoice'), async () => {
        purchaseInvoiceBtn.prop('disabled', true);

        try {
          const r = await frm.call('create_purchase_invoice', {
            expense_request: frm.doc.name,
          });

          if (r && r.message) {
            frappe.msgprint({
              title: __('Purchase Invoice Created'),
              message: __('Purchase Invoice {0} created from this request.', [r.message]),
              indicator: 'green',
            });
            frm.reload_doc();
          }
        } catch (error) {
          frappe.msgprint({
            title: __('Unable to Create Purchase Invoice'),
            message: error && error.message
              ? error.message
              : __('An unexpected error occurred while creating the Purchase Invoice. Please try again.'),
            indicator: 'red',
          });
        } finally {
          purchaseInvoiceBtn.prop('disabled', false);
        }
      }, __('Create'));
    };

    maybeRenderPurchaseInvoiceButton();

    const maybeAddOcrButton = async () => {
      const enabled = await frappe.db.get_single_value('Tax Invoice OCR Settings', 'enable_tax_invoice_ocr');
      if (!enabled || !frm.doc.ti_tax_invoice_upload) {
        return;
      }

      frm.add_custom_button(__('Run OCR'), async () => {
        await frappe.call({
          method: 'imogi_finance.api.tax_invoice.run_ocr_for_upload',
          args: { upload_name: frm.doc.ti_tax_invoice_upload },
          freeze: true,
          freeze_message: __('Queueing OCR...'),
        });
        frappe.show_alert({ message: __('OCR queued.'), indicator: 'green' });
        await syncErUpload(frm);
      }, __('Tax Invoice'));
    };

    const maybeAddTaxInvoiceActions = () => {
      if (!frm.doc.ti_tax_invoice_upload) {
        return;
      }

      frm.add_custom_button(__('Open Tax Invoice Upload'), () => {
        frappe.set_route('Form', 'Tax Invoice OCR Upload', frm.doc.ti_tax_invoice_upload);
      }, __('Tax Invoice'));

      frm.add_custom_button(__('Refresh Tax Invoice Data'), async () => {
        await frappe.call({
          method: 'imogi_finance.api.tax_invoice.apply_tax_invoice_upload',
          args: { target_doctype: 'Expense Request', target_name: frm.doc.name },
          freeze: true,
          freeze_message: __('Refreshing...'),
        });
        await frm.reload_doc();
      }, __('Tax Invoice'));
    };

    maybeAddOcrButton();
    maybeAddTaxInvoiceActions();
  },

  async ti_tax_invoice_upload(frm) {
    await syncErUpload(frm);
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
