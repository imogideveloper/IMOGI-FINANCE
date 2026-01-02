const getSelectedNames = (listview) => {
  if (!listview) return [];

  const checkedNames = listview.get_checked_items?.(true);
  if (Array.isArray(checkedNames) && checkedNames.length) {
    return checkedNames;
  }

  const checkedItems = listview.get_checked_items?.() || [];
  return checkedItems.map((item) => item.name).filter(Boolean);
};

const runBulkAction = async ({ listview, actionLabel, method, argsFactory, freezeMessage, successMessage }) => {
  const selectedNames = getSelectedNames(listview);

  if (!selectedNames.length) {
    frappe.msgprint(__("Please select at least one Tax Invoice OCR Upload."));
    return;
  }

  const confirmed = await new Promise((resolve) => {
    frappe.confirm(
      __("{0} selected documents?", [actionLabel]),
      () => resolve(true),
      () => resolve(false),
    );
  });

  if (!confirmed) return;

  frappe.dom.freeze(freezeMessage);
  try {
    await Promise.all(
      selectedNames.map((name) =>
        frappe.call({
          method,
          args: argsFactory(name),
        }),
      ),
    );
    frappe.show_alert({ message: successMessage, indicator: "green" });
    listview.refresh();
  } finally {
    frappe.dom.unfreeze();
  }
};

frappe.listview_settings["Tax Invoice OCR Upload"] = {
  onload(listview) {
    listview.page.add_action_item(__("Run OCR"), () => {
      runBulkAction({
        listview,
        actionLabel: __("Run OCR"),
        method: "imogi_finance.api.tax_invoice.run_ocr_for_upload",
        argsFactory: (name) => ({ upload_name: name }),
        freezeMessage: __("Queueing OCR..."),
        successMessage: __("OCR queued."),
      });
    });

    listview.page.add_action_item(__("Verify Tax Invoice"), () => {
      runBulkAction({
        listview,
        actionLabel: __("Verify Tax Invoice"),
        method: "imogi_finance.api.tax_invoice.verify_tax_invoice_upload",
        argsFactory: (name) => ({ upload_name: name }),
        freezeMessage: __("Verifying Tax Invoice..."),
        successMessage: __("Tax Invoice verification queued."),
      });
    });
  },
};
