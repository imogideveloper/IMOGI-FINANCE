frappe.ui.form.on('Cash Bank Daily Report', {
  refresh(frm) {
    if (!frm.is_new()) {
      frm.add_custom_button(__('Regenerate Snapshot'), () => {
        frappe.call({
          method: 'imogi_finance.imogi_finance.doctype.cash_bank_daily_report.cash_bank_daily_report.regenerate',
          args: { name: frm.doc.name },
          freeze: true,
          freeze_message: __('Regenerating daily report...'),
          callback(r) {
            if (r.message) {
              frm.set_value('snapshot_json', r.message.snapshot_json);
              frm.set_value('status', r.message.status);
              frm.set_value('opening_balance', r.message.opening_balance);
              frm.set_value('inflow', r.message.inflow);
              frm.set_value('outflow', r.message.outflow);
              frm.set_value('closing_balance', r.message.closing_balance);
            }
            frm.reload_doc();
          },
        });
      });
    }

    // Render read-only preview from snapshot_json
    render_daily_report_preview(frm);
  },
});

function render_daily_report_preview(frm) {
  const wrapper = frm.fields_dict.preview_html && frm.fields_dict.preview_html.$wrapper;
  if (!wrapper) return;

  let data;
  try {
    data = frm.doc.snapshot_json ? JSON.parse(frm.doc.snapshot_json) : null;
  } catch (e) {
    wrapper.html('<div class="text-muted">Snapshot JSON is invalid.</div>');
    return;
  }

  if (!data) {
    wrapper.html('<div class="text-muted">No snapshot available. Save the document to generate the daily report.</div>');
    return;
  }

  const consolidated = data.consolidated || {};
  const branches = data.branches || [];

  let html = '';
  html += '<div class="mb-2"><strong>Summary</strong></div>';
  html += '<table class="table table-bordered table-condensed">';
  html += '<thead><tr>';
  html += '<th>Opening</th><th>Inflow</th><th>Outflow</th><th>Closing</th>';
  html += '</tr></thead><tbody><tr>';
  html += `<td class="text-right">${format_currency(consolidated.opening_balance || 0)}</td>`;
  html += `<td class="text-right">${format_currency(consolidated.inflow || 0)}</td>`;
  html += `<td class="text-right">${format_currency(consolidated.outflow || 0)}</td>`;
  html += `<td class="text-right">${format_currency(consolidated.closing_balance || 0)}</td>`;
  html += '</tr></tbody></table>';

  branches.forEach((br) => {
    const txs = br.transactions || [];
    html += `<div class="mt-3"><strong>Branch: ${frappe.utils.escape_html(br.branch || '')}</strong></div>`;
    if (!txs.length) {
      html += '<div class="text-muted small">No transactions</div>';
      return;
    }
    html += '<table class="table table-bordered table-condensed">';
    html += '<thead><tr>';
    html += '<th style="width:18%">Date</th>';
    html += '<th style="width:32%">Reference</th>';
    html += '<th style="width:20%" class="text-right">Direction</th>';
    html += '<th style="width:30%" class="text-right">Amount</th>';
    html += '</tr></thead><tbody>';
    txs.forEach((tx) => {
      const date = tx.posting_date ? frappe.datetime.str_to_user(tx.posting_date) : '';
      const ref = frappe.utils.escape_html(tx.reference || '');
      const direction = (tx.direction || '').toUpperCase();
      const amount = format_currency(tx.amount || 0);
      html += '<tr>';
      html += `<td>${date}</td>`;
      html += `<td>${ref}</td>`;
      html += `<td class="text-right">${direction}</td>`;
      html += `<td class="text-right">${amount}</td>`;
      html += '</tr>';
    });
    html += '</tbody></table>';
  });

  wrapper.html(html);
}

function format_currency(value) {
  try {
    return frappe.format(value, { fieldtype: 'Currency' });
  } catch (e) {
    return (value || 0).toString();
  }
}
