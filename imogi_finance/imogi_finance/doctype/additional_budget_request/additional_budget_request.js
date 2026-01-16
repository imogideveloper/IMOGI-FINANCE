// Copyright (c) 2026, PT. Inovasi Terbaik Bangsa and contributors
// For license information, please see license.txt

frappe.ui.form.on('Additional Budget Request', {
	refresh(frm) {
		// Show workflow buttons based on permissions
		if (frm.doc.workflow_state === 'Pending Approval' && frm.doc.docstatus === 1) {
			const current_level = frm.doc.current_approval_level || 1;
			const required_approver = frm.doc[`level_${current_level}_user`];
			const current_user = frappe.session.user;
			const is_system_manager = frappe.user_roles.includes('System Manager');
			
			// Show approve/reject buttons if user has permission
			if (is_system_manager || current_user === required_approver) {
				// Buttons will be shown by workflow
				// This just ensures proper state
				frm.page.clear_actions();
				
				// Show approval info
				frappe.show_alert({
					message: __('You can approve this request (Level {0})', [current_level]),
					indicator: 'green'
				}, 5);
			} else if (required_approver) {
				// Show info about who should approve
				frappe.show_alert({
					message: __('Waiting for approval from {0} (Level {1})', [required_approver, current_level]),
					indicator: 'orange'
				}, 5);
			}
		}
		
		// Show amount and cost center in the title
		if (frm.doc.amount) {
			frm.set_intro(__('Additional Budget Amount: {0}', [format_currency(frm.doc.amount, frm.doc.company)]), 'blue');
		}
	},
	
	before_submit(frm) {
		// Validate before submit
		if (!frm.doc.cost_center) {
			frappe.throw(__('Cost Center is required'));
		}
		if (!frm.doc.account) {
			frappe.throw(__('Account is required'));
		}
		if (!frm.doc.amount || frm.doc.amount <= 0) {
			frappe.throw(__('Amount must be greater than zero'));
		}
	}
});
