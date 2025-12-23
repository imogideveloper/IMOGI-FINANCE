const formatDate = (value) => (value ? frappe.datetime.str_to_user(value).split(' ')[0] : '');

const formatCurrency = (value) => frappe.format(value, { fieldtype: 'Currency' }, { inline: true });

const getColumn = (listview, fieldname, fallback) => {
  const existingIndex = listview.columns.findIndex(
    ({ fieldname: current, id }) => current === fieldname || id === fieldname,
  );

  if (existingIndex > -1) {
    return listview.columns.splice(existingIndex, 1)[0];
  }

  return fallback;
};

const refreshColumns = (listview) => {
  if (!listview || !Array.isArray(listview.columns) || !listview.columns.length || !listview.datatable)
    return;

  const idColumn = getColumn(listview, 'name', {
    id: 'name',
    fieldname: 'name',
    label: __('Reference'),
    width: 230,
  });

  const importedOnColumn = getColumn(listview, 'imported_on', {
    id: 'imported_on',
    fieldname: 'imported_on',
    label: __('Date'),
    fieldtype: 'Datetime',
    width: 120,
    format: (value) => formatDate(value),
  });

  const bankAccountColumn = getColumn(listview, 'bank_account', {
    id: 'bank_account',
    fieldname: 'bank_account',
    label: __('Journal'),
    width: 180,
    link_field: 'bank_account',
    fieldtype: 'Link',
  });

  const companyColumn = getColumn(listview, 'company', {
    id: 'company',
    fieldname: 'company',
    label: __('Company'),
    width: 180,
    link_field: 'company',
    fieldtype: 'Link',
  });

  const startingBalanceColumn = getColumn(listview, 'starting_balance', {
    id: 'starting_balance',
    fieldname: 'starting_balance',
    label: __('Starting Balance'),
    fieldtype: 'Currency',
    width: 170,
    align: 'right',
    format: (value) => formatCurrency(value),
  });

  const endingBalanceColumn = getColumn(listview, 'ending_balance', {
    id: 'ending_balance',
    fieldname: 'ending_balance',
    label: __('Ending Balance'),
    fieldtype: 'Currency',
    width: 170,
    align: 'right',
    format: (value) => formatCurrency(value),
  });

  const statusColumn = getColumn(listview, 'import_status', {
    id: 'import_status',
    fieldname: 'import_status',
    label: __('Status'),
    width: 140,
  });

  listview.columns = [
    idColumn,
    importedOnColumn,
    bankAccountColumn,
    companyColumn,
    startingBalanceColumn,
    endingBalanceColumn,
    statusColumn,
  ];

  listview.datatable.refresh(listview.get_data(), listview.columns);
};

frappe.listview_settings['BCA Bank Statement Import'] = {
  add_fields: [
    'imported_on',
    'company',
    'bank_account',
    'import_status',
    'hash_id',
    'starting_balance',
    'ending_balance',
  ],
  onload(listview) {
    refreshColumns(listview);
  },
  refresh(listview) {
    refreshColumns(listview);
  },
};
