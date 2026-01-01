frappe.query_reports["Customer Receipt Control Report"] = {
  filters: [
    { fieldname: "date_from", label: "From Date", fieldtype: "Date" },
    { fieldname: "date_to", label: "To Date", fieldtype: "Date" },
    { fieldname: "receipt_no", label: "Receipt No", fieldtype: "Link", options: "Customer Receipt" },
    { fieldname: "status", label: "Status", fieldtype: "Select", options: "\nDraft\nIssued\nPartially Paid\nPaid\nCancelled" },
    { fieldname: "customer", label: "Customer", fieldtype: "Link", options: "Customer" },
    { fieldname: "customer_reference_no", label: "Customer Ref No", fieldtype: "Data" },
    { fieldname: "sales_order_no", label: "Sales Order", fieldtype: "Link", options: "Sales Order" },
    { fieldname: "billing_no", label: "Sales Invoice", fieldtype: "Link", options: "Sales Invoice" },
    { fieldname: "sales_invoice_no", label: "Billing No (Alt)", fieldtype: "Link", options: "Sales Invoice" },
    {
      fieldname: "receipt_purpose",
      label: "Purpose",
      fieldtype: "Select",
      options: "\nBefore Billing (Sales Order)\nBilling (Sales Invoice)"
    },
    {
      fieldname: "stamp_mode",
      label: "Stamp Mode",
      fieldtype: "Select",
      options: "\nNone\nPhysical\nDigital"
    },
    {
      fieldname: "digital_stamp_status",
      label: "Digital Stamp Status",
      fieldtype: "Select",
      options: "\nDraft\nRequested\nIssued\nFailed\nCancelled"
    }
  ]
};
