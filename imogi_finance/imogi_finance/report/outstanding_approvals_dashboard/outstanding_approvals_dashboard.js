// Copyright (c) 2024, PT DAS and contributors
// For license information, please see license.txt

frappe.query_reports["Outstanding Approvals Dashboard"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"label": __("From Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "to_date",
			"label": __("To Date"),
			"fieldtype": "Date"
		},
		{
			"fieldname": "doctype",
			"label": __("Document Type"),
			"fieldtype": "MultiSelectList",
			"get_data": function(txt) {
				return [
					{ value: "Expense Request", description: "Expense Request" },
					{ value: "Branch Expense Request", description: "Branch Expense Request" },
					{ value: "Additional Budget Request", description: "Additional Budget Request" },
					{ value: "Budget Reclass Request", description: "Budget Reclass Request" },
					{ value: "Internal Charge Request", description: "Internal Charge Request" },
					{ value: "Administrative Payment Voucher", description: "Administrative Payment Voucher" },
					{ value: "Cash Bank Daily Report", description: "Cash Bank Daily Report" }
				];
			}
		},
		{
			"fieldname": "approval_level",
			"label": __("Approval Level"),
			"fieldtype": "Select",
			"options": ["", "1", "2", "3"]
		},
		{
			"fieldname": "cost_center",
			"label": __("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center"
		},
		{
			"fieldname": "branch",
			"label": __("Branch"),
			"fieldtype": "Link",
			"options": "Branch"
		}
	],
	
	"onload": function(report) {
		// Clear any invalid date values from URL parameters
		const from_date = report.get_filter_value('from_date');
		const to_date = report.get_filter_value('to_date');
		
		// Function to check if date is valid
		function isValidDate(dateString) {
			if (!dateString) return true; // empty is valid
			
			// Try to parse date
			const date = frappe.datetime.str_to_obj(dateString);
			if (!date) return false;
			
			// Check if year is reasonable (between 2000 and 2100)
			const year = date.getFullYear();
			return year >= 2000 && year <= 2100;
		}
		
		// Clear invalid dates
		if (!isValidDate(from_date)) {
			report.set_filter_value('from_date', '');
		}
		if (!isValidDate(to_date)) {
			report.set_filter_value('to_date', '');
		}
	}
};
