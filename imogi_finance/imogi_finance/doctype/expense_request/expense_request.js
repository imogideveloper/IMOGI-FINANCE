frappe.ui.form.on('Expense Request', {
  refresh(frm) {
    frm.dashboard.clear_headline();

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
      return;
    }

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

    if (canCreatePurchaseInvoice) {
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
    } else {
      showPurchaseInvoiceAvailability();
    }
  },
});
