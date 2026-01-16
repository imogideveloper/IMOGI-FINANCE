// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.query_reports["Budget Control Dashboard"] = {
	"filters": [
		{
			"fieldname": "company",
			"label": __("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"default": frappe.defaults.get_user_default("Company"),
			"reqd": 1
		},
		{
			"fieldname": "fiscal_year",
			"label": __("Fiscal Year"),
			"fieldtype": "Link",
			"options": "Fiscal Year",
			"reqd": 1,
			"get_query": function() {
				return {
					"filters": {
						"disabled": 0
					}
				}
			}
		},
		{
			"fieldname": "cost_center",
			"label": __("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"reqd": 0
		},
		{
			"fieldname": "account",
			"label": __("Account"),
			"fieldtype": "Link",
			"options": "Account",
			"reqd": 0,
			"get_query": function() {
				return {
					"filters": {
						"is_group": 0,
						"root_type": "Expense"
					}
				}
			}
		},
		{
			"fieldname": "project",
			"label": __("Project"),
			"fieldtype": "Link",
			"options": "Project",
			"reqd": 0
		},
		{
			"fieldname": "branch",
			"label": __("Branch"),
			"fieldtype": "Link",
			"options": "Branch",
			"reqd": 0
		},
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date",
			"reqd": 0
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date",
			"reqd": 0
		},
		{
			"fieldname": "hide_zero",
			"label": __("Hide Zero Balances"),
			"fieldtype": "Check",
			"default": 0
		}
	],
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Skip formatting for total row or if data is undefined
		if (!data || data.isTotal || row.isTotal) {
			return value;
		}
		
		// Color code status
		if (column.fieldname == "status" && data.status) {
			if (data.status == "Over Budget" || data.status == "Over Committed") {
				value = `<span class="indicator-pill red filterable" data-filter="status,=,${data.status}">${data.status}</span>`;
			} else if (data.status == "Critical") {
				value = `<span class="indicator-pill orange filterable" data-filter="status,=,Critical">${data.status}</span>`;
			} else if (data.status == "Warning") {
				value = `<span class="indicator-pill yellow filterable" data-filter="status,=,Warning">${data.status}</span>`;
			} else if (data.status == "In Use") {
				value = `<span class="indicator-pill blue filterable" data-filter="status,=,In Use">${data.status}</span>`;
			} else if (data.status == "Unused") {
				value = `<span class="indicator-pill grey filterable" data-filter="status,=,Unused">${data.status}</span>`;
			} else if (data.status == "Fully Used") {
				value = `<span class="indicator-pill darkgrey filterable" data-filter="status,=,Fully Used">${data.status}</span>`;
			} else {
				value = `<span class="indicator-pill grey">${data.status}</span>`;
			}
		}
		
		// Color code available
		if (column.fieldname == "available" && data.available !== undefined) {
			if (data.available < 0) {
				value = `<span style="color: #d9534f; font-weight: bold;">${frappe.format(data.available, {fieldtype: 'Currency'})}</span>`;
			} else if (data.available == 0) {
				value = `<span style="color: #f0ad4e; font-weight: bold;">${frappe.format(data.available, {fieldtype: 'Currency'})}</span>`;
			} else {
				value = `<span style="color: #5cb85c;">${frappe.format(data.available, {fieldtype: 'Currency'})}</span>`;
			}
		}
		
		// Color code percentages
		if (column.fieldname == "actual_pct" || column.fieldname == "reserved_pct" || column.fieldname == "committed_pct" || column.fieldname == "available_pct") {
			let pct_value = data[column.fieldname];
			if (pct_value !== undefined && pct_value !== null && !isNaN(pct_value)) {
				if (column.fieldname == "committed_pct") {
					if (pct_value >= 100) {
						value = `<span style="color: #d9534f; font-weight: bold;">${pct_value.toFixed(1)}%</span>`;
					} else if (pct_value > 90) {
						value = `<span style="color: #f0ad4e; font-weight: bold;">${pct_value.toFixed(1)}%</span>`;
					} else if (pct_value > 75) {
						value = `<span style="color: #ffc107;">${pct_value.toFixed(1)}%</span>`;
					} else {
						value = `<span style="color: #5cb85c;">${pct_value.toFixed(1)}%</span>`;
					}
				} else {
					value = `<span>${pct_value.toFixed(1)}%</span>`;
				}
			}
		}
		
		// Color code variance
		if (column.fieldname == "variance" && data.variance !== undefined) {
			if (data.variance < 0) {
				value = `<span style="color: #d9534f;">${frappe.format(data.variance, {fieldtype: 'Currency'})}</span>`;
			} else if (data.variance > 0) {
				value = `<span style="color: #5cb85c;">${frappe.format(data.variance, {fieldtype: 'Currency'})}</span>`;
			}
		}
		
		return value;
	},
	
	"onload": function(report) {
		// Set default filters if not already set
		if (!report.get_filter_value('company')) {
			let default_company = frappe.defaults.get_user_default("Company");
			if (default_company) {
				report.set_filter_value('company', default_company);
			}
		}
		
		if (!report.get_filter_value('fiscal_year')) {
			// Get current fiscal year
			frappe.call({
				method: 'erpnext.accounts.utils.get_fiscal_year',
				args: {
					date: frappe.datetime.get_today(),
					company: report.get_filter_value('company') || frappe.defaults.get_user_default("Company")
				},
				callback: function(r) {
					if (r.message && r.message[0]) {
						report.set_filter_value('fiscal_year', r.message[0]);
					}
				}
			});
		}
		
		// Add custom button to view details
		report.page.add_inner_button(__("View Budget Control Entries"), function() {
			frappe.set_route("List", "Budget Control Entry");
		});
		
		// Add refresh button
		report.page.add_inner_button(__("Refresh"), function() {
			report.refresh();
		});
	}
};
