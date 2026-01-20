// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Internal Charge Request', {
  refresh: function(frm) {
    // Add custom indicators and buttons
    calculateLineTotals(frm);
    validateAccountTotals(frm);
    
    // Refresh after workflow action
    if (frm.doc.docstatus === 1) {
      frm.trigger('setup_workflow_indicators');
    }
    
    // Add button to auto-populate lines from ER
    if (frm.doc.expense_request && frm.doc.docstatus === 0 && !frm.is_new()) {
      frm.add_custom_button(__('Repopulate from ER'), function() {
        frm.trigger('repopulate_lines_from_er');
      });
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
  
  repopulate_lines_from_er: async function(frm) {
    if (!frm.doc.expense_request) {
      return;
    }
    
    frappe.confirm(
      __('This will replace all existing lines with items from the Expense Request. Continue?'),
      async () => {
        try {
          const { message } = await frappe.call({
            method: 'frappe.client.get',
            args: {
              doctype: 'Expense Request',
              name: frm.doc.expense_request,
            },
          });
          
          if (message && message.items) {
            // Clear existing lines
            frm.clear_table('internal_charge_lines');
            
            // Add new lines from ER items
            message.items.forEach(item => {
              const child = frm.add_child('internal_charge_lines');
              frappe.model.set_value(child.doctype, child.name, 'target_cost_center', frm.doc.source_cost_center);
              frappe.model.set_value(child.doctype, child.name, 'expense_account', item.expense_account);
              frappe.model.set_value(child.doctype, child.name, 'description', item.description);
              frappe.model.set_value(child.doctype, child.name, 'amount', item.amount);
            });
            
            frm.refresh_field('internal_charge_lines');
            calculateLineTotals(frm);
            
            frappe.show_alert({
              message: __('Lines repopulated from Expense Request'),
              indicator: 'green'
            });
          }
        } catch (error) {
          frappe.msgprint({
            title: __('Error'),
            message: error?.message || __('Failed to repopulate lines'),
            indicator: 'red',
          });
        }
      }
    );
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
    validateAccountTotals(frm);
  },
  
  expense_account: function(frm, cdt, cdn) {
    validateAccountTotals(frm);
  },
  
  internal_charge_lines_remove: function(frm) {
    calculateLineTotals(frm);
    validateAccountTotals(frm);
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

function validateAccountTotals(frm) {
  if (!frm.doc.expense_request || !frm.doc.internal_charge_lines || frm.doc.internal_charge_lines.length === 0) {
    return;
  }
  
  // Get ICR line totals per account
  const icrAccountTotals = {};
  frm.doc.internal_charge_lines.forEach(line => {
    if (line.expense_account && line.amount) {
      icrAccountTotals[line.expense_account] = (icrAccountTotals[line.expense_account] || 0) + parseFloat(line.amount);
    }
  });
  
  // Fetch ER items and validate
  frappe.call({
    method: 'frappe.client.get',
    args: {
      doctype: 'Expense Request',
      name: frm.doc.expense_request,
    },
    callback: function(r) {
      if (r.message && r.message.items) {
        const erAccountTotals = {};
        r.message.items.forEach(item => {
          if (item.expense_account && item.amount) {
            erAccountTotals[item.expense_account] = (erAccountTotals[item.expense_account] || 0) + parseFloat(item.amount);
          }
        });
        
        // Check for mismatches
        let hasError = false;
        const errors = [];
        
        Object.keys(erAccountTotals).forEach(account => {
          const erTotal = erAccountTotals[account];
          const icrTotal = icrAccountTotals[account] || 0;
          
          if (Math.abs(erTotal - icrTotal) > 0.01) {
            hasError = true;
            errors.push(__('Account {0}: ER={1}, ICR={2}', [
              account,
              format_currency(erTotal),
              format_currency(icrTotal)
            ]));
          }
        });
        
        // Check for extra accounts in ICR
        Object.keys(icrAccountTotals).forEach(account => {
          if (!erAccountTotals[account]) {
            hasError = true;
            errors.push(__('Account {0} in ICR but not in ER', [account]));
          }
        });
        
        if (hasError) {
          frm.dashboard.add_indicator(
            __('Account Allocation Mismatch'),
            'red'
          );
          frm.set_intro(__('Allocation errors: {0}', [errors.join('; ')]), 'red');
        } else if (Object.keys(icrAccountTotals).length > 0) {
          frm.set_intro(__('Account allocations match ER items'), 'green');
        }
      }
    }
  });
}
