frappe.query_reports["Digital Stamp Expense Report"] = {
  filters: [
    { fieldname: "start_date", label: "Start Date", fieldtype: "Date" },
    { fieldname: "end_date", label: "End Date", fieldtype: "Date" },
    { fieldname: "payment_status", label: "Payment Status", fieldtype: "Select", options: "\nDraft\nPaid\nCancelled" }
  ]
};
