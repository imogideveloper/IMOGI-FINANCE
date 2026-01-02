frappe.listview_settings["Branch Expense Request"] = {
	add_fields: ["branch", "employee", "requester", "total_amount", "status"],
	get_indicator(doc) {
		if (doc.status === "Approved") {
			return [__("Approved"), "green", "status,=,Approved"];
		}
		if (doc.status === "Pending Approval") {
			return [__("Pending Approval"), "orange", "status,=,Pending Approval"];
		}
		if (doc.status === "Rejected") {
			return [__("Rejected"), "red", "status,=,Rejected"];
		}
		return [__(doc.status || "Draft"), "blue", "status,=," + (doc.status || "Draft")];
	},
};
