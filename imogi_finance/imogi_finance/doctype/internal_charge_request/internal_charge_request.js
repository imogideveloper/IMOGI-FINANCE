// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Internal Charge Request', {
  refresh: function(frm) {
    // Add custom indicators and buttons
    calculateLineTotals(frm);
    
    // Refresh after workflow action
    if (frm.doc.docstatus === 1) {
      frm.trigger('setup_workflow_indicators');
    }
  },
  
  onload: function(frm) {
    // Setup field dependencies
    setupFieldDependencies(frm);
    
    // Auto-fetch from Expense Request if linked
    if (frm.doc.expense_request && frm.is_new()) {
      frm.trigger('fetch_expense_request_details');
    }
  },
  
  expense_request: function(frm) {
    if (frm.doc.expense_request) {
      frm.trigger('fetch_expense_request_details');
    }
  },
  
  fetch_expense_request_details: async function(frm) {
    if (!frm.doc.expense_request) {
      return;
    }
    
    try {
      const { message } = await frappe.call({
        method: 'frappe.client.get',
        args: {
          doctype: 'Expense Request',
          name: frm.doc.expense_request,
        },
      });
      
      if (message) {
        // Auto-populate fields from ER
        frm.set_value('company', message.company);
        frm.set_value('source_cost_center', message.cost_center);
        frm.set_value('total_amount', message.total_amount);
        
        // Set posting_date to ER request_date if available
        if (message.request_date) {
          frm.set_value('posting_date', message.request_date);
        }
        
        // Get fiscal year from ER or current date
        if (!frm.doc.fiscal_year && message.company) {
          const fy = await getFiscalYear(message.company, frm.doc.posting_date);
          if (fy) {
            frm.set_value('fiscal_year', fy);
          }
        }
      }
    } catch (error) {
      frappe.msgprint({
        title: __('Unable to Fetch Expense Request'),
        message: error?.message || __('An unexpected error occurred.'),
        indicator: 'red',
      });
    }
  },
  
  setup_workflow_indicators: function(frm) {
    if (!frm.doc.docstatus === 1) {
      return;
    }
    
    // Show workflow state with color
    const statusColors = {
      'Approved': 'green',
      'Partially Approved': 'orange',
      'Pending Approval': 'blue',
      'Rejected': 'red',
      'Draft': 'gray'
    };
    
    const color = statusColors[frm.doc.status] || 'gray';
    frm.dashboard.add_indicator(__('Status: {0}', [frm.doc.status]), color);
    
    // Show approval progress
    if (frm.doc.internal_charge_lines) {
      const total = frm.doc.internal_charge_lines.length;
      const approved = frm.doc.internal_charge_lines.filter(l => l.line_status === 'Approved').length;
      const pending = frm.doc.internal_charge_lines.filter(l => 
        ['Pending L1', 'Pending L2', 'Pending L3'].includes(l.line_status)
      ).length;
      
      if (approved > 0 || pending > 0) {
        frm.dashboard.add_indicator(
          __('Approval: {0}/{1} approved, {2} pending', [approved, total, pending]),
          approved === total ? 'green' : 'orange'
        );
      }
    }
  },
});

frappe.ui.form.on('Internal Charge Line', {
  amount: function(frm, cdt, cdn) {
    calculateLineTotals(frm);
  },
  
  internal_charge_lines_remove: function(frm) {
    calculateLineTotals(frm);
  },
  
  target_cost_center: function(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    
    // Validate target_cost_center is different from source
    if (row.target_cost_center === frm.doc.source_cost_center) {
      frappe.msgprint({
        title: __('Invalid Target Cost Center'),
        message: __('Target Cost Center cannot be the same as Source Cost Center ({0}).', [frm.doc.source_cost_center]),
        indicator: 'orange',
      });
      frappe.model.set_value(cdt, cdn, 'target_cost_center', '');
    }
  },
});

// Helper Functions

function calculateLineTotals(frm) {
  if (!frm.doc.internal_charge_lines || frm.doc.internal_charge_lines.length === 0) {
    return;
  }
  
  const lineTotal = frm.doc.internal_charge_lines.reduce((sum, line) => {
    return sum + (parseFloat(line.amount) || 0);
  }, 0);
  
  // Show warning if totals don't match
  if (frm.doc.total_amount && Math.abs(lineTotal - frm.doc.total_amount) > 0.01) {
    frm.dashboard.add_indicator(
      __('Warning: Line total ({0}) does not match Total Amount ({1})', 
        [format_currency(lineTotal), format_currency(frm.doc.total_amount)]),
      'red'
    );
  } else if (lineTotal > 0) {
    frm.dashboard.add_indicator(
      __('Line Total: {0}', [format_currency(lineTotal)]),
      'green'
    );
  }
  
  // Update status info
  if (frm.doc.internal_charge_lines.length > 0) {
    const statusCounts = {};
    frm.doc.internal_charge_lines.forEach(line => {
      const status = line.line_status || 'Draft';
      statusCounts[status] = (statusCounts[status] || 0) + 1;
    });
    
    const statusInfo = Object.entries(statusCounts)
      .map(([status, count]) => `${status}: ${count}`)
      .join(', ');
    
    frm.set_intro(__('Line Status: {0}', [statusInfo]), 'blue');
  }
}

function setupFieldDependencies(frm) {
  // Make source_cost_center, company, fiscal_year, total_amount readonly
  // These are auto-populated from Expense Request
  if (frm.doc.expense_request) {
    frm.set_df_property('source_cost_center', 'read_only', 1);
    frm.set_df_property('company', 'read_only', 1);
    frm.set_df_property('total_amount', 'read_only', 1);
  }
  
  // Disable editing after submit
  if (frm.doc.docstatus === 1) {
    frm.set_df_property('internal_charge_lines', 'read_only', 1);
  }
}

async function getFiscalYear(company, date) {
  try {
    const { message } = await frappe.call({
      method: 'erpnext.accounts.utils.get_fiscal_year',
      args: {
        date: date || frappe.datetime.get_today(),
        company: company,
      },
    });
    return message ? message[0] : null;
  } catch (error) {
    console.error('Error fetching fiscal year:', error);
    return null;
  }
}
