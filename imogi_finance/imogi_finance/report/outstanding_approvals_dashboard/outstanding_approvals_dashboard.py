# Copyright (c) 2024, PT DAS and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import date_diff, getdate, now_datetime, get_datetime


def execute(filters=None):
	"""
	Main entry point for Outstanding Approvals Dashboard report.
	Returns columns and data for all pending approvals assigned to the filtered user.
	"""
	if not filters:
		filters = {}
	
	# Default user to current session user if not provided
	if not filters.get("user"):
		filters["user"] = frappe.session.user
	
	# Default date range to last 30 days if not provided
	if not filters.get("from_date"):
		filters["from_date"] = frappe.utils.add_days(frappe.utils.nowdate(), -30)
	
	if not filters.get("to_date"):
		filters["to_date"] = frappe.utils.nowdate()
	
	columns = get_columns()
	data = get_data(filters)
	chart = get_chart_data(data)
	report_summary = get_report_summary(data)
	
	return columns, data, None, chart, report_summary


def get_columns():
	"""
	Define report columns with proper field types and widths.
	"""
	return [
		{
			"fieldname": "doctype",
			"label": _("Document Type"),
			"fieldtype": "Data",
			"width": 150
		},
		{
			"fieldname": "document",
			"label": _("Document"),
			"fieldtype": "Dynamic Link",
			"options": "doctype",
			"width": 180
		},
		{
			"fieldname": "creation",
			"label": _("Created On"),
			"fieldtype": "Datetime",
			"width": 140
		},
		{
			"fieldname": "owner",
			"label": _("Created By"),
			"fieldtype": "Link",
			"options": "User",
			"width": 150
		},
		{
			"fieldname": "workflow_state",
			"label": _("Status"),
			"fieldtype": "Data",
			"width": 120
		},
		{
			"fieldname": "current_approval_level",
			"label": _("Level"),
			"fieldtype": "Int",
			"width": 60
		},
		{
			"fieldname": "amount",
			"label": _("Amount"),
			"fieldtype": "Currency",
			"width": 120
		},
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Link",
			"options": "Cost Center",
			"width": 150
		},
		{
			"fieldname": "branch",
			"label": _("Branch"),
			"fieldtype": "Link",
			"options": "Branch",
			"width": 120
		},
		{
			"fieldname": "days_pending",
			"label": _("Days Pending"),
			"fieldtype": "Int",
			"width": 100
		},
		{
			"fieldname": "aging_category",
			"label": _("Aging"),
			"fieldtype": "Data",
			"width": 100
		},
		{
			"fieldname": "approver",
			"label": _("Approver"),
			"fieldtype": "Data",
			"width": 150
		}
	]


def get_data(filters):
	"""
	Query all approval doctypes and return pending approvals assigned to the filtered user.
	"""
	# Define approval doctypes to query
	approval_doctypes = [
		{
			"doctype": "Expense Request",
			"amount_field": "amount",
			"cost_center_field": "cost_center",
			"branch_field": "branch",
			"pending_states": ["Pending Review"]
		},
		{
			"doctype": "Branch Expense Request",
			"amount_field": "amount",
			"cost_center_field": "cost_center",
			"branch_field": "branch",
			"pending_states": ["Pending Review"]
		},
		{
			"doctype": "Additional Budget Request",
			"amount_field": "amount",
			"cost_center_field": "cost_center",
			"branch_field": None,
			"pending_states": ["Pending Approval"]
		},
		{
			"doctype": "Budget Reclass Request",
			"amount_field": "amount",
			"cost_center_field": "cost_center",
			"branch_field": None,
			"pending_states": ["Pending Approval"]
		},
		{
			"doctype": "Internal Charge Request",
			"amount_field": "total_amount",
			"cost_center_field": "cost_center",
			"branch_field": "branch",
			"pending_states": ["Pending L1 Approval", "Pending L2 Approval", "Pending L3 Approval"]
		},
		{
			"doctype": "Administrative Payment Voucher",
			"amount_field": "total_amount",
			"cost_center_field": "cost_center",
			"branch_field": None,
			"pending_states": ["Pending Approval"]
		},
		{
			"doctype": "Cash Bank Daily Report",
			"amount_field": None,
			"cost_center_field": None,
			"branch_field": "branch",
			"pending_states": ["Generated"]
		}
	]
	
	all_data = []
	user = filters.get("user")
	from_date = filters.get("from_date")
	to_date = filters.get("to_date")
	doctype_filter = filters.get("doctype")
	approval_level_filter = filters.get("approval_level")
	cost_center_filter = filters.get("cost_center")
	branch_filter = filters.get("branch")
	
	for doctype_config in approval_doctypes:
		doctype = doctype_config["doctype"]
		
		# Skip if doctype filter is applied and this doctype is not selected
		if doctype_filter and doctype not in doctype_filter:
			continue
		
		# Check if doctype exists
		if not frappe.db.exists("DocType", doctype):
			continue
		
		# Query for each approval level (1, 2, 3)
		for level in [1, 2, 3]:
			# Skip if approval level filter is applied and this level doesn't match
			if approval_level_filter and level != approval_level_filter:
				continue
			
			level_user_field = f"level_{level}_user"
			
			# Check if level field exists in doctype
			if not frappe.db.exists("DocField", {"parent": doctype, "fieldname": level_user_field}):
				continue
			
			# Build filter conditions
			filter_conditions = {
				"workflow_state": ["in", doctype_config["pending_states"]],
				"docstatus": 1,
				"current_approval_level": level,
				level_user_field: user
			}
			
			# Add date filters
			if from_date:
				filter_conditions["modified"] = [">=", from_date]
			if to_date:
				filter_conditions["modified"] = ["<=", to_date]
			
			# Add cost center filter if applicable
			if cost_center_filter and doctype_config["cost_center_field"]:
				filter_conditions[doctype_config["cost_center_field"]] = cost_center_filter
			
			# Add branch filter if applicable
			if branch_filter and doctype_config["branch_field"]:
				filter_conditions[doctype_config["branch_field"]] = branch_filter
			
			# Build fields list
			fields = [
				"name", "creation", "modified", "owner", "workflow_state", 
				"current_approval_level", level_user_field
			]
			
			if doctype_config["amount_field"]:
				fields.append(doctype_config["amount_field"])
			if doctype_config["cost_center_field"]:
				fields.append(doctype_config["cost_center_field"])
			if doctype_config["branch_field"]:
				fields.append(doctype_config["branch_field"])
			
			try:
				# Execute query
				pending_docs = frappe.get_all(
					doctype,
					filters=filter_conditions,
					fields=fields,
					order_by="modified desc"
				)
				
				# Process results
				for doc in pending_docs:
					# Calculate days pending
					days_pending = date_diff(getdate(), getdate(doc.modified))
					
					# Determine aging category
					aging_category = get_aging_category(days_pending)
					
					# Get approver full name
					approver_user = doc.get(level_user_field)
					approver_name = frappe.db.get_value("User", approver_user, "full_name") or approver_user
					
					# Build row data
					row = {
						"doctype": doctype,
						"document": doc.name,
						"creation": doc.creation,
						"owner": doc.owner,
						"workflow_state": doc.workflow_state,
						"current_approval_level": doc.current_approval_level,
						"amount": doc.get(doctype_config["amount_field"]) if doctype_config["amount_field"] else 0,
						"cost_center": doc.get(doctype_config["cost_center_field"]) if doctype_config["cost_center_field"] else None,
						"branch": doc.get(doctype_config["branch_field"]) if doctype_config["branch_field"] else None,
						"days_pending": days_pending,
						"aging_category": aging_category,
						"approver": approver_name
					}
					
					all_data.append(row)
					
			except Exception as e:
				frappe.log_error(f"Error querying {doctype} for approval level {level}: {str(e)}")
				continue
	
	return all_data


def get_aging_category(days):
	"""
	Categorize approval aging into buckets with color indicators.
	"""
	if days <= 7:
		return "0-7 days"
	elif days <= 14:
		return "8-14 days"
	elif days <= 30:
		return "15-30 days"
	else:
		return ">30 days"


def get_report_summary(data):
	"""
	Generate summary cards for the report.
	"""
	if not data:
		return []
	
	total_pending = len(data)
	
	# Calculate average days pending
	total_days = sum(row["days_pending"] for row in data)
	avg_days = round(total_days / total_pending, 1) if total_pending > 0 else 0
	
	# Find oldest document
	oldest_days = max(row["days_pending"] for row in data) if data else 0
	
	# Count critical approvals (>30 days)
	critical_count = sum(1 for row in data if row["days_pending"] > 30)
	
	return [
		{
			"value": total_pending,
			"label": _("Total Pending"),
			"indicator": "blue",
			"datatype": "Int"
		},
		{
			"value": avg_days,
			"label": _("Avg Days Pending"),
			"indicator": "orange" if avg_days > 14 else "green",
			"datatype": "Float"
		},
		{
			"value": oldest_days,
			"label": _("Oldest (Days)"),
			"indicator": "red" if oldest_days > 30 else "orange",
			"datatype": "Int"
		},
		{
			"value": critical_count,
			"label": _("Critical (>30 Days)"),
			"indicator": "red" if critical_count > 0 else "green",
			"datatype": "Int"
		}
	]


def get_chart_data(data):
	"""
	Generate chart data for visualizations.
	"""
	if not data:
		return None
	
	# Chart 1: Approvals by Document Type (Pie Chart)
	doctype_counts = {}
	for row in data:
		doctype = row["doctype"]
		doctype_counts[doctype] = doctype_counts.get(doctype, 0) + 1
	
	# Chart 2: Approvals by Aging Category (Bar Chart)
	aging_counts = {
		"0-7 days": 0,
		"8-14 days": 0,
		"15-30 days": 0,
		">30 days": 0
	}
	for row in data:
		aging_category = row["aging_category"]
		aging_counts[aging_category] = aging_counts.get(aging_category, 0) + 1
	
	return {
		"data": {
			"labels": list(aging_counts.keys()),
			"datasets": [
				{
					"name": _("Approvals by Aging"),
					"values": list(aging_counts.values())
				}
			]
		},
		"type": "bar",
		"colors": ["#28a745", "#ffc107", "#fd7e14", "#dc3545"],
		"barOptions": {
			"stacked": 0
		}
	}
