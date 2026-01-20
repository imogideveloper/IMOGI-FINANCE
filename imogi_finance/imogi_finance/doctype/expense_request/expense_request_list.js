(() => {
  const ACTION_LABEL_CREATE_PI = __("Create PI");

  const getSelectedItems = (listview) => listview.get_checked_items?.() || [];

  const shouldShowCreatePi = (selectedItems) => {
    if (!selectedItems.length) {
      return false;
    }

    return selectedItems.every(
      (item) => item.docstatus === 1 && item.status === "Approved"
    );
  };

  const toggleCreatePiAction = (listview) => {
    const selectedItems = getSelectedItems(listview);
    const showAction = shouldShowCreatePi(selectedItems);
    const $actions =
      listview?.page?.actions || listview?.page?.page_actions || listview?.page?.wrapper;

    if (!$actions?.find) {
      return;
    }

    $actions
      .find("a")
      .filter(function () {
        return $(this).text().trim() === ACTION_LABEL_CREATE_PI;
      })
      .each(function () {
        $(this).toggle(showAction);
      });
  };

  frappe.listview_settings["Expense Request"] = {
    add_fields: ["status", "docstatus", "request_type", "supplier", "total_amount"],
    
    get_indicator(doc) {
      // Status-based indicators
      if (doc.status === "Paid") {
        return [__("💰 Paid"), "green", "status,=,Paid"];
      }
      if (doc.status === "Return") {
        return [__("🔄 Return"), "purple", "status,=,Return"];
      }
      if (doc.status === "PI Created") {
        return [__("📄 PI Created"), "blue", "status,=,PI Created"];
      }
      if (doc.status === "Approved") {
        return [__("✅ Approved"), "green", "status,=,Approved"];
      }
      if (doc.status === "Pending Review") {
        return [__("⏳ Pending Review"), "orange", "status,=,Pending Review"];
      }
      if (doc.status === "Rejected") {
        return [__("❌ Rejected"), "red", "status,=,Rejected"];
      }
      if (doc.status === "Cancelled") {
        return [__("🚫 Cancelled"), "darkgrey", "status,=,Cancelled"];
      }
      
      return [__(doc.status || "📝 Draft"), "blue", "status,=," + (doc.status || "Draft")];
    },
    
    onload(listview) {
      const refreshActions = () => toggleCreatePiAction(listview);

      listview.page.wrapper.on(
        "change",
        'input[type="checkbox"]',
        refreshActions
      );
      listview.page.wrapper.on("click", ".list-row, .list-check-all", refreshActions);
      if (listview.on) {
        listview.on("refresh", refreshActions);
      }

      refreshActions();
    },
  };
})();
