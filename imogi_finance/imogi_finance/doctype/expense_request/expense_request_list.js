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

  const getStatusIndicator = (doc) => {
    if (doc.docstatus === 2) {
      return [__("Cancelled"), "darkgrey", "docstatus,=,2"];
    }

    const status = doc.status || doc.workflow_state;

    if (!status || doc.docstatus === 0) {
      return [__("Draft"), "blue", "docstatus,=,0"];
    }

    if (status === "Approved") {
      return [__("Approved"), "green", "status,=,Approved"];
    }

    if (status === "Pending Review") {
      return [__("Pending Review"), "orange", "status,=,Pending Review"];
    }

    if (status === "Rejected") {
      return [__("Rejected"), "red", "status,=,Rejected"];
    }

    if (status === "PI Created") {
      return [__("PI Created"), "blue", "status,=,PI Created"];
    }

    if (status === "Paid") {
      return [__("Paid"), "green", "status,=,Paid"];
    }

    return [__(status), "gray", `status,=,${status}`];
  };

  frappe.listview_settings["Expense Request"] = {
    add_fields: ["status", "workflow_state", "docstatus"],
    get_indicator: getStatusIndicator,
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
