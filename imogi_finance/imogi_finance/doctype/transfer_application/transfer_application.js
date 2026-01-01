frappe.ui.form.on('Transfer Application', {
  setup(frm) {
    load_reference_options(frm);
  },

  refresh(frm) {
    load_reference_options(frm);
    set_reference_query(frm);

    if (!frm.is_new() && frm.doc.docstatus !== 2) {
      add_payment_entry_button(frm);
      add_mark_printed_button(frm);
    }
  },

  reference_doctype(frm) {
    set_reference_query(frm);
  },
});

function load_reference_options(frm) {
  frappe.call({
    method: 'imogi_finance.imogi_finance.doctype.transfer_application.transfer_application.fetch_reference_doctype_options',
    callback: (r) => {
      if (Array.isArray(r.message)) {
        frm.set_df_property('reference_doctype', 'options', r.message.join('\n'));
      }
    },
  });
}

function set_reference_query(frm) {
  if (!frm.doc.reference_doctype || frm.doc.reference_doctype === 'Other') {
    frm.set_query('reference_name', null);
    return;
  }

  frm.set_query('reference_name', () => ({
    filters: { docstatus: 1 },
    doctype: frm.doc.reference_doctype,
  }));
}

function add_payment_entry_button(frm) {
  frm.add_custom_button(__('Create Payment Entry'), async () => {
    if (frm.is_dirty()) {
      await frm.save();
    }

    frm.call({
      doc: frm.doc,
      method: 'create_payment_entry',
      freeze: true,
      freeze_message: __('Creating Payment Entry...'),
      callback: (r) => {
        const pe = r?.message?.payment_entry;
        if (pe) {
          frappe.show_alert({ message: __('Payment Entry {0} created').format(pe), indicator: 'green' });
          frm.reload_doc().then(() => frappe.set_route('Form', 'Payment Entry', pe));
        }
      },
    });
  }, __('Actions'));
}

function add_mark_printed_button(frm) {
  frm.add_custom_button(__('Mark as Printed'), () => {
    frm.call({
      doc: frm.doc,
      method: 'mark_as_printed',
      freeze: true,
      callback: (r) => {
        if (r?.message?.printed_at) {
          frappe.show_alert({ message: __('Marked as printed'), indicator: 'blue' });
          frm.reload_doc();
        }
      },
    });
  }, __('Actions'));
}
