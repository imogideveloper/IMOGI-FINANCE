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
	
	"onload": function(report) {
		// Add help button with detailed guide
		report.page.add_inner_button(__('📖 Panduan Dashboard'), function() {
			frappe.msgprint({
				title: __('Cara Membaca Budget Control Dashboard'),
				indicator: 'blue',
				message: `
					<div style="font-size: 13px; line-height: 1.7;">
						<h4 style="margin-top: 0; color: #2e7d32;">📊 Formula Perhitungan</h4>
						<div style="background: #f5f5f5; padding: 12px; border-radius: 4px; margin-bottom: 15px; font-family: monospace;">
							<strong>Net Reserved</strong> = Reservation - Consumption + Reversal<br>
							<strong>Committed</strong> = Actual (GL) + Net Reserved<br>
							<strong>Available</strong> = Allocated - Committed
						</div>
						
						<h4 style="color: #1976d2;">💡 Arti Kolom Budget Control Entries</h4>
						<ul style="margin-bottom: 15px;">
							<li><strong style="color: #ff9800;">Reservation (+)</strong>: Budget di-lock saat Expense Request approved<br>
							    <small>Entry OUT - Mengurangi available</small></li>
							<li><strong style="color: #2196f3;">Consumption (-)</strong>: Budget dikonsumsi saat Purchase Invoice submit<br>
							    <small>Entry IN - Mengurangi reservation (bukan available!)</small></li>
							<li><strong style="color: #4caf50;">Reversal (+)</strong>: Budget dikembalikan saat Purchase Invoice cancel<br>
							    <small>Entry OUT - Menambah kembali reservation</small></li>
						</ul>
						
						<h4 style="color: #e91e63;">🎯 Contoh Skenario</h4>
						<div style="background: #fff3e0; padding: 12px; border-radius: 4px; margin-bottom: 15px;">
							<strong>Allocated: 100jt</strong><br><br>
							
							<strong>1. ER Submit (30jt)</strong><br>
							• Reservation: +30jt<br>
							• Net Reserved: 30jt<br>
							• Available: 70jt<br><br>
							
							<strong>2. PI Submit (30jt)</strong><br>
							• Consumption: -30jt (mengurangi reservation!)<br>
							• Actual: 30jt (dari GL Entry)<br>
							• Net Reserved: 30jt - 30jt = 0jt<br>
							• Available: 100jt - 30jt - 0jt = 70jt ✅ (tetap!)<br><br>
							
							<strong>3. PI Cancel</strong><br>
							• Reversal: +30jt<br>
							• Actual: 0jt (GL reversed)<br>
							• Net Reserved: 30jt - 30jt + 30jt = 30jt<br>
							• Available: 70jt ✅ (kembali!)
						</div>
						
						<h4 style="color: #9c27b0;">📈 Status Budget</h4>
						<ul style="list-style: none; padding-left: 0;">
							<li><span class="indicator-pill grey">Unused</span> - Budget belum dipakai</li>
							<li><span class="indicator-pill blue">In Use</span> - Normal, <75% committed</li>
							<li><span class="indicator-pill yellow">Warning</span> - Perhatian, 75-90% committed</li>
							<li><span class="indicator-pill orange">Critical</span> - Kritis, >90% committed</li>
							<li><span class="indicator-pill red">Over Budget</span> - Sudah melebihi alokasi!</li>
						</ul>
						
						<div style="background: #e3f2fd; padding: 12px; border-radius: 4px; margin-top: 15px;">
							<strong>💡 Tips Monitoring:</strong>
							<ul>
								<li>Available > 20% = Budget aman ✅</li>
								<li>Net Reserved > 50% = Banyak ER pending, percepat proses PI 🔄</li>
								<li>Committed > 90% = Stop approve ER baru ⛔</li>
							</ul>
						</div>
					</div>
				`
			});
		}, __('Help'));
	},
	
	"formatter": function(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		
		// Skip formatting for total row or if data is undefined
		if (!data || data.isTotal || row.isTotal) {
			return value;
		}
		
		// Color code Budget Control Entry types
		// Reservation: Orange (positive = mengurangi available)
		if (column.fieldname == "reservation" && data.reservation !== undefined && data.reservation !== 0) {
			const color = data.reservation > 0 ? "#ff9800" : "#d9534f";
			value = `<span style="color: ${color}; font-weight: bold;">${frappe.format(data.reservation, {fieldtype: 'Currency'})}</span>`;
		}
		
		// Consumption: Blue when negative (consuming reservation), Red when positive
		if (column.fieldname == "consumption" && data.consumption !== undefined && data.consumption !== 0) {
			const color = data.consumption < 0 ? "#2196f3" : "#d9534f";
			value = `<span style="color: ${color}; font-weight: bold;">${frappe.format(data.consumption, {fieldtype: 'Currency'})}</span>`;
		}
		
		// Reversal: Green (positive = restoring reservation)
		if (column.fieldname == "reversal" && data.reversal !== undefined && data.reversal !== 0) {
			const color = data.reversal > 0 ? "#4caf50" : "#d9534f";
			value = `<span style="color: ${color}; font-weight: bold;">${frappe.format(data.reversal, {fieldtype: 'Currency'})}</span>`;
		}
		
		if (column.fieldname == "reclass" && data.reclass !== undefined && data.reclass !== 0) {
			value = `<span style="color: #5bc0de;">${frappe.format(data.reclass, {fieldtype: 'Currency'})}</span>`;
		}
		
		if (column.fieldname == "supplement" && data.supplement !== undefined && data.supplement > 0) {
			value = `<span style="color: #5cb85c; font-weight: bold;">${frappe.format(data.supplement, {fieldtype: 'Currency'})}</span>`;
		}
		
		if (column.fieldname == "net_reserved" && data.net_reserved !== undefined) {
			if (data.net_reserved < 0) {
				value = `<span style="color: #d9534f; font-weight: bold;">${frappe.format(data.net_reserved, {fieldtype: 'Currency'})}</span>`;
			} else if (data.net_reserved > 0) {
				value = `<span style="color: #f0ad4e; font-weight: bold;">${frappe.format(data.net_reserved, {fieldtype: 'Currency'})}</span>`;
			}
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
		
		// Color code committed percentage
		if (column.fieldname == "committed_pct") {
			let pct_value = data[column.fieldname];
			if (pct_value !== undefined && pct_value !== null && !isNaN(pct_value)) {
				if (pct_value >= 100) {
					value = `<span style="color: #d9534f; font-weight: bold;">${pct_value.toFixed(1)}%</span>`;
				} else if (pct_value > 90) {
					value = `<span style="color: #f0ad4e; font-weight: bold;">${pct_value.toFixed(1)}%</span>`;
				} else if (pct_value > 75) {
					value = `<span style="color: #ffc107;">${pct_value.toFixed(1)}%</span>`;
				} else {
					value = `<span style="color: #5cb85c;">${pct_value.toFixed(1)}%</span>`;
				}
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
