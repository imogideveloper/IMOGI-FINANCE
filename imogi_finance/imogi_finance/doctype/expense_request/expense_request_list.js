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
  add_fields: ["status", "docstatus"],
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
