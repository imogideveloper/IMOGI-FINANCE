# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Budget Control Dashboard - Consolidated Report

Combines data from:
1. Native ERPNext Budget (allocated amount)
2. GL Entry (actual spent)
3. Budget Control Entry (reserved/locked amount)

This is the MAIN report that users should use - combines all budget tracking in one place.
"""

import frappe
from frappe import _
from imogi_finance.budget_control import ledger, utils


def execute(filters=None):
    validate_filters(filters)
    columns = get_columns()
    data = get_data(filters)
    chart = get_chart_data(data, filters)
    summary = get_summary(data)
    
    return columns, data, None, chart, summary


def validate_filters(filters):
    """Validate required filters."""
    if not filters:
        filters = {}
    
    if not filters.get("company"):
        filters["company"] = frappe.defaults.get_user_default("Company")
        if not filters["company"]:
            frappe.throw(_("Please select a Company"))
    
    if not filters.get("fiscal_year"):
        # Try to get current fiscal year
        try:
            from erpnext.accounts.utils import get_fiscal_year
            fiscal_year = get_fiscal_year(date=frappe.utils.today(), company=filters["company"])
            if fiscal_year:
                filters["fiscal_year"] = fiscal_year[0]
        except:
            pass
        
        if not filters.get("fiscal_year"):
            frappe.throw(_("Please select a Fiscal Year"))


def get_columns():
    """Define report columns - combines native budget + reservation data."""
    return [
        {
            "fieldname": "cost_center",
            "label": _("Cost Center"),
            "fieldtype": "Link",
            "options": "Cost Center",
            "width": 200
        },
        {
            "fieldname": "account",
            "label": _("Account"),
            "fieldtype": "Link",
            "options": "Account",
            "width": 200
        },
        {
            "fieldname": "allocated",
            "label": _("Allocated"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "actual",
            "label": _("Actual Spent"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "actual_pct",
            "label": _("Actual %"),
            "fieldtype": "Percent",
            "width": 100
        },
        {
            "fieldname": "reserved",
            "label": _("Reserved"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "reserved_pct",
            "label": _("Reserved %"),
            "fieldtype": "Percent",
            "width": 100
        },
        {
            "fieldname": "committed",
            "label": _("Committed"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "committed_pct",
            "label": _("Committed %"),
            "fieldtype": "Percent",
            "width": 100
        },
        {
            "fieldname": "available",
            "label": _("Available"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "available_pct",
            "label": _("Available %"),
            "fieldtype": "Percent",
            "width": 100
        },
        {
            "fieldname": "variance",
            "label": _("Variance"),
            "fieldtype": "Currency",
            "width": 130
        },
        {
            "fieldname": "status",
            "label": _("Status"),
            "fieldtype": "Data",
            "width": 120
        }
    ]


def get_data(filters):
    """
    Get consolidated budget data.
    
    Combines:
    1. Budget allocation (from native Budget)
    2. Actual spending (from GL Entry)
    3. Reserved amount (from Budget Control Entry)
    """
    company = filters.get("company")
    fiscal_year = filters.get("fiscal_year")
    
    # Get all budgets for company/fiscal year
    budget_filters = {
        "company": company,
        "fiscal_year": fiscal_year,
        "docstatus": 1
    }
    
    if filters.get("cost_center"):
        budget_filters["cost_center"] = filters.get("cost_center")
    
    budgets = frappe.get_all(
        "Budget",
        filters=budget_filters,
        fields=["name", "cost_center"]
    )
    
    if not budgets:
        frappe.msgprint(_("No Budget found for {0} - {1}").format(company, fiscal_year))
        return []
    
    data = []
    from_date = filters.get("from_date")
    to_date = filters.get("to_date")
    
    for budget in budgets:
        # Get budget accounts from native Budget
        budget_accounts = frappe.get_all(
            "Budget Account",
            filters={"parent": budget.name},
            fields=["account", "budget_amount"]
        )
        
        for ba in budget_accounts:
            # Apply filters
            if filters.get("account") and ba.account != filters.get("account"):
                continue
            
            # Build dimensions
            dims = utils.Dimensions(
                company=company,
                fiscal_year=fiscal_year,
                cost_center=budget.cost_center,
                account=ba.account,
                project=filters.get("project"),
                branch=filters.get("branch")
            )
            
            # Get availability data (combines all 3 sources)
            availability = ledger.get_availability(dims, from_date=from_date, to_date=to_date)
            
            allocated = availability["allocated"]
            actual = availability["actual"]
            reserved = availability["reserved"]
            available = availability["available"]
            
            # Calculate percentages
            actual_pct = (actual / allocated * 100) if allocated > 0 else 0
            reserved_pct = (reserved / allocated * 100) if allocated > 0 else 0
            committed = actual + reserved
            committed_pct = (committed / allocated * 100) if allocated > 0 else 0
            available_pct = (available / allocated * 100) if allocated > 0 else 0
            variance = allocated - actual
            
            # Skip if no activity (optional filter)
            if filters.get("hide_zero") and allocated == 0 and actual == 0 and reserved == 0:
                continue
            
            # Determine status
            status = get_status(allocated, actual, reserved, available)
            
            data.append({
                "cost_center": budget.cost_center,
                "account": ba.account,
                "allocated": allocated or 0,
                "actual": actual or 0,
                "actual_pct": actual_pct or 0,
                "reserved": reserved or 0,
                "reserved_pct": reserved_pct or 0,
                "committed": committed or 0,
                "committed_pct": committed_pct or 0,
                "available": available or 0,
                "available_pct": available_pct or 0,
                "variance": variance or 0,
                "status": status
            })
    
    # Sort by allocated descending, then by committed percentage
    data.sort(key=lambda x: (x["allocated"], x["committed_pct"]), reverse=True)
    
    return data


def get_status(allocated, actual, reserved, available):
    """Determine budget status."""
    if allocated <= 0:
        return "No Budget"
    
    committed_pct = ((actual + reserved) / allocated) * 100
    
    if available < 0:
        return "Over Budget"
    elif available == 0:
        return "Fully Used"
    elif committed_pct >= 100:
        return "Over Committed"
    elif committed_pct > 90:
        return "Critical"
    elif committed_pct > 75:
        return "Warning"
    elif actual > 0 or reserved > 0:
        return "In Use"
    else:
        return "Unused"


def get_chart_data(data, filters):
    """Generate stacked bar chart for top 10 accounts."""
    if not data:
        return None
    
    # Take top 10 by committed amount
    top_data = sorted(data, key=lambda x: x.get("committed", 0) or 0, reverse=True)[:10]
    
    if not top_data:
        return None
    
    labels = []
    actual_values = []
    reserved_values = []
    available_values = []
    
    for row in top_data:
        # Shorten labels for better display
        cc = row.get('cost_center', '') or ''
        acc = row.get('account', '') or ''
        cc_short = cc.split(' - ')[-1][:12] if cc else "N/A"
        acc_short = acc.split(' - ')[-1][:15] if acc else "N/A"
        label = f"{cc_short} - {acc_short}"
        
        labels.append(label)
        actual_values.append(float(row.get("actual", 0) or 0))
        reserved_values.append(float(row.get("reserved", 0) or 0))
        available_values.append(max(0, float(row.get("available", 0) or 0)))  # Don't show negative in chart
    
    chart_data = {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": _("Actual Spent"),
                    "values": actual_values
                },
                {
                    "name": _("Reserved"),
                    "values": reserved_values
                },
                {
                    "name": _("Available"),
                    "values": available_values
                }
            ]
        },
        "type": "bar",
        "barOptions": {
            "stacked": 1,
            "spaceRatio": 0.5
        },
        "height": 350,
        "colors": ["#FF6B6B", "#FFA726", "#66BB6A"]
    }
    
    return chart_data


def get_summary(data):
    """Generate summary cards."""
    if not data:
        return []
    
    total_allocated = sum(row.get("allocated", 0) or 0 for row in data)
    total_actual = sum(row.get("actual", 0) or 0 for row in data)
    total_reserved = sum(row.get("reserved", 0) or 0 for row in data)
    total_available = sum(row.get("available", 0) or 0 for row in data)
    
    over_budget_count = len([r for r in data if (r.get("available", 0) or 0) < 0])
    critical_count = len([r for r in data if r.get("status") in ("Critical", "Warning")])
    
    return [
        {
            "value": total_allocated,
            "indicator": "blue",
            "label": _("Total Allocated"),
            "datatype": "Currency"
        },
        {
            "value": total_actual,
            "indicator": "orange",
            "label": _("Total Actual Spent"),
            "datatype": "Currency"
        },
        {
            "value": total_reserved,
            "indicator": "purple",
            "label": _("Total Reserved"),
            "datatype": "Currency"
        },
        {
            "value": total_available,
            "indicator": "green" if total_available > 0 else "red",
            "label": _("Total Available"),
            "datatype": "Currency"
        },
        {
            "value": over_budget_count,
            "indicator": "red" if over_budget_count > 0 else "grey",
            "label": _("Over Budget Accounts")
        },
        {
            "value": critical_count,
            "indicator": "yellow" if critical_count > 0 else "grey",
            "label": _("Critical/Warning Accounts")
        }
    ]
