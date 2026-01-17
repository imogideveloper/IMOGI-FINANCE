# Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
# For license information, please see license.txt

"""
Budget Control Dashboard - Consolidated Hybrid Report

HYBRID APPROACH:
This report combines data from multiple sources to provide complete budget visibility:

1. Native ERPNext Budget (allocated amount)
   - Source: Budget and Budget Account doctypes
   - Shows: Total allocated budget per Cost Center + Account

2. GL Entry (actual spent)
   - Source: Posted GL Entries
   - Shows: Actual expenses already posted to ledger

3. Budget Control Entry (reserved/locked amount)
   - Source: Budget Control Entry doctype (custom ledger)
   - Shows: Reserved amounts from approved Expense Requests (not yet in GL)

FIELD COMPATIBILITY:
Report columns are aligned with Budget Control Entry structure:
- Dimensions: fiscal_year, cost_center, account, project, branch
- Aggregates: allocated, actual, reserved, committed, available, variance
- Status: Dynamic status based on utilization

Users can drill-down from this summary to detailed Budget Control Entries
by clicking the "View Budget Control Entries" button with auto-filtered list.

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
    message = get_info_message()
    
    return columns, data, message, chart, summary


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


def get_info_message():
    """Display information banner about how to read the dashboard."""
    return """
        <div style="padding: 12px; background: #e8f5e9; border-left: 4px solid #4caf50; margin-bottom: 15px; border-radius: 4px;">
            <h4 style="margin: 0 0 10px 0; color: #2e7d32;">📊 Cara Membaca Budget Control Dashboard</h4>
            <div style="font-size: 13px; line-height: 1.6; color: #1b5e20;">
                <p style="margin: 5px 0;"><strong>Formula Perhitungan:</strong></p>
                <ul style="margin: 5px 0 10px 20px;">
                    <li><strong>Net Reserved</strong> = Reservation - Consumption + Reversal</li>
                    <li><strong>Committed</strong> = Actual (GL) + Net Reserved</li>
                    <li><strong>Available</strong> = Allocated - Committed</li>
                </ul>
                <p style="margin: 5px 0;"><strong>Arti Kolom:</strong></p>
                <ul style="margin: 5px 0 10px 20px;">
                    <li><strong>Reservation (+)</strong>: Budget di-lock untuk Expense Request yang approved</li>
                    <li><strong>Consumption (-)</strong>: Budget yang dikonsumsi oleh Purchase Invoice yang submitted</li>
                    <li><strong>Reversal (+)</strong>: Budget yang dikembalikan saat Purchase Invoice di-cancel</li>
                    <li><strong>Net Reserved</strong>: Budget yang masih di-hold untuk ER yang belum jadi PI</li>
                    <li><strong>Committed</strong>: Total budget terpakai (actual + reserved)</li>
                    <li><strong>Available</strong>: Budget yang masih bisa digunakan untuk ER baru</li>
                </ul>
                <p style="margin: 5px 0;"><strong>Status Budget:</strong> 
                    <span style="color: #4caf50;">✓ In Use (<75%)</span> | 
                    <span style="color: #ff9800;">⚠ Warning (75-90%)</span> | 
                    <span style="color: #f44336;">✗ Critical (>90%)</span>
                </p>
            </div>
        </div>
    """


def get_columns():
    """Define report columns - combines native budget + Budget Control Entry breakdown."""
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
            "fieldname": "project",
            "label": _("Project"),
            "fieldtype": "Link",
            "options": "Project",
            "width": 150
        },
        {
            "fieldname": "branch",
            "label": _("Branch"),
            "fieldtype": "Link",
            "options": "Branch",
            "width": 150
        },
        {
            "fieldname": "allocated",
            "label": _("Allocated"),
            "fieldtype": "Currency",
            "width": 120,
            "description": _("Total budget yang dialokasikan dari ERPNext Budget")
        },
        {
            "fieldname": "actual",
            "label": _("Actual (GL)"),
            "fieldtype": "Currency",
            "width": 120,
            "description": _("Pengeluaran aktual yang sudah di-posting ke General Ledger (PI, Payment)")
        },
        {
            "fieldname": "reservation",
            "label": _("Reservation (+)"),
            "fieldtype": "Currency",
            "width": 120,
            "description": _("Budget yang di-lock untuk Expense Request yang approved (entry OUT)")
        },
        {
            "fieldname": "consumption",
            "label": _("Consumption (-)"),
            "fieldtype": "Currency",
            "width": 120,
            "description": _("Budget yang dikonsumsi saat Purchase Invoice submit (entry IN, mengurangi reservation)")
        },
        {
            "fieldname": "reversal",
            "label": _("Reversal (+)"),
            "fieldtype": "Currency",
            "width": 120,
            "description": _("Budget yang dikembalikan saat Purchase Invoice di-cancel (entry OUT, restore reservation)")
        },
        {
            "fieldname": "reclass",
            "label": _("Reclass"),
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "fieldname": "supplement",
            "label": _("Supplement"),
            "fieldtype": "Currency",
            "width": 120
        },
        {
            "fieldname": "net_reserved",
            "label": _("Net Reserved"),
            "fieldtype": "Currency",
            "width": 120,
            "description": _("Reservation - Consumption + Reversal = Budget masih di-hold untuk ER belum jadi PI")
        },
        {
            "fieldname": "committed",
            "label": _("Committed"),
            "fieldtype": "Currency",
            "width": 120,
            "description": _("Actual + Net Reserved = Total budget yang sudah terpakai atau akan terpakai")
        },
        {
            "fieldname": "committed_pct",
            "label": _("Committed %"),
            "fieldtype": "Percent",
            "width": 100,
            "description": _("Persentase committed dari allocated (target <75% = aman, >90% = kritis)")
        },
        {
            "fieldname": "available",
            "label": _("Available"),
            "fieldtype": "Currency",
            "width": 120,
            "description": _("Allocated - Committed = Budget yang masih bisa digunakan untuk ER baru")
        },
        {
            "fieldname": "status",
            "label": _("Status"),
            "fieldtype": "Data",
            "width": 120,
            "description": _("Status budget: Unused/In Use/Warning/Critical/Over Budget")
        }
    ]


def get_budget_control_breakdown(dims, from_date=None, to_date=None):
    """
    Get breakdown of Budget Control Entry by entry_type.
    
    New Simplified Flow (No RELEASE):
    - RESERVATION: Budget locked for Expense Request (OUT)
    - CONSUMPTION: Consumes reserved budget when PI submit (IN)
    - REVERSAL: Restores reserved budget when PI cancel (OUT)
    - RECLASS: Budget movement between accounts
    - SUPPLEMENT: Additional budget allocation
    
    Reserved = RESERVATION - CONSUMPTION + REVERSAL
    
    Returns dict with keys: reservation, consumption, reversal, reclass, supplement
    """
    filters = {
        "company": dims.company,
        "fiscal_year": dims.fiscal_year,
        "cost_center": dims.cost_center,
        "account": dims.account,
        "docstatus": 1
    }
    
    if dims.project:
        filters["project"] = dims.project
    if dims.branch:
        filters["branch"] = dims.branch
    if from_date and to_date:
        filters["posting_date"] = ["between", [from_date, to_date]]
    
    try:
        entries = frappe.get_all(
            "Budget Control Entry",
            filters=filters,
            fields=["entry_type", "direction", "amount"]
        )
    except:
        entries = []
    
    breakdown = {
        "reservation": 0.0,
        "consumption": 0.0,
        "reversal": 0.0,
        "reclass": 0.0,
        "supplement": 0.0
    }
    
    for entry in entries:
        entry_type = entry.get("entry_type", "").lower()
        direction = entry.get("direction")
        amount = float(entry.get("amount") or 0.0)
        
        if entry_type in breakdown:
            # Signed amount based on direction
            if direction == "OUT":
                breakdown[entry_type] += amount  # OUT = positive (reserve/restore)
            elif direction == "IN":
                breakdown[entry_type] -= amount  # IN = negative (consume)
    
    return breakdown


def get_data(filters):
    """
    Get consolidated budget data with Budget Control Entry breakdown.
    
    Combines:
    1. Budget allocation (from native Budget)
    2. Actual spending (from GL Entry)
    3. Budget Control Entry breakdown (RESERVATION, CONSUMPTION, RELEASE, etc.)
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
            
            # Get Budget Control Entry breakdown by entry_type
            breakdown = get_budget_control_breakdown(dims, from_date=from_date, to_date=to_date)
            
            # Net reserved = RESERVATION - CONSUMPTION + REVERSAL
            # Simplified flow: no RELEASE needed
            # - RESERVATION: +100 (locked for ER)
            # - CONSUMPTION: -100 (consumed by PI)
            # - REVERSAL: +100 (restored on PI cancel)
            net_reserved = breakdown["reservation"] + breakdown["consumption"] + breakdown["reversal"]
            
            # Calculate committed = actual + net reserved
            committed = actual + net_reserved
            committed_pct = (committed / allocated * 100) if allocated > 0 else 0
            
            # Skip if no activity (optional filter)
            if filters.get("hide_zero") and allocated == 0 and actual == 0 and net_reserved == 0:
                continue
            
            # Determine status
            status = get_status(allocated, actual, net_reserved, available)
            
            data.append({
                "cost_center": budget.cost_center,
                "account": ba.account,
                "project": dims.project or "",
                "branch": dims.branch or "",
                "allocated": allocated or 0,
                "acservation": breakdown["reservation"] or 0,
                "consumption": breakdown["consumption"] or 0,
                "release": breakdown["release"] or 0,
                "reversal": breakdown["reversal"] or 0,
                "reclass": breakdown["reclass"] or 0,
                "supplement": breakdown["supplement"] or 0,
                "net_reserved": net_reserved or 0,
                "committed": committed or 0,
                "committed_pct": committed_pct or 0,
                "available": available or 0,
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
    """Generate stacked bar chart for top 10 accounts with Budget Control Entry breakdown."""
    if not data:
        return None
    
    # Take top 10 by committed amount
    top_data = sorted(data, key=lambda x: x.get("committed", 0) or 0, reverse=True)[:10]
    
    if not top_data:
        return None
    
    labels = []
    actual_values = []
    reservation_values = []
    consumption_values = []
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
        # Show absolute values for chart
        reservation_values.append(abs(float(row.get("reservation", 0) or 0)))
        consumption_values.append(abs(float(row.get("consumption", 0) or 0)))
        available_values.append(max(0, float(row.get("available", 0) or 0)))  # Don't show negative in chart
    
    chart_data = {
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "name": _("Actual (GL)"),
                    "values": actual_values
                },
                {
                    "name": _("Reservation"),
                    "values": reservation_values
                },
                {
                    "name": _("Consumption"),
                    "values": consumption_values
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
        "colors": ["#FF6B6B", "#FFA726", "#42A5F5", "#66BB6A"]
    }
    
    return chart_data


def get_summary(data):
    """Generate summary cards with Budget Control Entry breakdown."""
    if not data:
        return []
    
    total_allocated = sum(row.get("allocated", 0) or 0 for row in data)
    total_actual = sum(row.get("actual", 0) or 0 for row in data)
    total_reservation = sum(row.get("reservation", 0) or 0 for row in data)
    total_consumption = sum(row.get("consumption", 0) or 0 for row in data)
    total_release = sum(row.get("release", 0) or 0 for row in data)
    total_net_reserved = sum(row.get("net_reserved", 0) or 0 for row in data)
    total_committed = sum(row.get("committed", 0) or 0 for row in data)
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
            "label": _("Total Actual (GL)"),
            "datatype": "Currency"
        },
        {
            "value": abs(total_reservation),
            "indicator": "red",
            "label": _("Total Reservation"),
            "datatype": "Currency"
        },
        {
            "value": abs(total_consumption),
            "indicator": "blue",
            "label": _("Total Consumption"),
            "datatype": "Currency"
        },
        {
            "value": abs(total_release),
            "indicator": "green",
            "label": _("Total Release"),
            "datatype": "Currency"
        },
        {
            "value": abs(total_net_reserved),
            "indicator": "purple",
            "label": _("Net Reserved"),
            "datatype": "Currency"
        },
        {
            "value": total_committed,
            "indicator": "orange",
            "label": _("Total Committed"),
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
