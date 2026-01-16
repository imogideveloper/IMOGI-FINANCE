/**
 * Browser Console Debug Commands for Budget Control Entry
 * 
 * Jalankan di browser console untuk troubleshoot Budget Control Entry
 * 
 * Usage:
 * 1. Buka Expense Request di browser
 * 2. Buka browser console (F12 atau Cmd+Option+I)
 * 3. Copy-paste command yang diperlukan
 */

// ============================================================================
// 1. CEK APAKAH BUDGET CONTROL ENTRY SUDAH DIBUAT
// ============================================================================
window.check_bce_exists = function(expense_request_name) {
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Budget Control Entry',
            filters: {
                ref_doctype: 'Expense Request',
                ref_name: expense_request_name || cur_frm.doc.name
            },
            fields: ['name', 'entry_type', 'amount', 'direction', 'posting_date', 'docstatus']
        },
        callback: function(r) {
            console.log('=== Budget Control Entries ===');
            if (r.message && r.message.length > 0) {
                console.table(r.message);
                console.log(`Found ${r.message.length} entries`);
            } else {
                console.log('❌ NO Budget Control Entry found!');
            }
        }
    });
}

// ============================================================================
// 2. CEK KONFIGURASI BUDGET CONTROL SETTING
// ============================================================================
window.check_budget_settings = function() {
    frappe.call({
        method: 'imogi_finance.budget_control.utils.get_settings_for_ui',
        callback: function(r) {
            console.log('=== Budget Control Settings ===');
            if (r.message) {
                console.log('Enable Budget Lock:', r.message.enable_budget_lock);
                console.log('Lock on Workflow State:', r.message.lock_on_workflow_state);
                console.log('Budget Controller Role:', r.message.budget_controller_role);
                console.log('Allow Budget Overrun Role:', r.message.allow_budget_overrun_role);
                console.log('Enable Budget Reclass:', r.message.enable_budget_reclass);
                console.log('Enable Additional Budget:', r.message.enable_additional_budget);
                console.log('Enforce Mode:', r.message.enforce_mode);
                console.log('\n✅ Settings loaded successfully');
            } else {
                console.log('❌ Budget Control Setting not found!');
            }
        },
        error: function(r) {
            console.error('❌ Error loading settings:', r);
        }
    });
}

// ============================================================================
// 3. CEK DIMENSI BUDGET (COST CENTER, ACCOUNT, DLL)
// ============================================================================
window.check_budget_dimensions = function() {
    if (!cur_frm || cur_frm.doctype !== 'Expense Request') {
        console.error('Please open an Expense Request first!');
        return;
    }
    
    const doc = cur_frm.doc;
    console.log('=== Budget Dimensions ===');
    console.log('Cost Center:', doc.cost_center);
    console.log('Project:', doc.project);
    console.log('Branch:', doc.branch);
    console.log('Company:', doc.company || '⚠️ NOT SET - will resolve from Cost Center');
    console.log('Fiscal Year:', doc.fiscal_year || '⚠️ NOT SET - will resolve from defaults');
    console.log('Status:', doc.status);
    console.log('Workflow State:', doc.workflow_state);
    console.log('Allocation Mode:', doc.allocation_mode);
    console.log('Budget Lock Status:', doc.budget_lock_status);
    console.log('Budget Workflow State:', doc.budget_workflow_state);
    
    // Check fiscal year resolution
    if (!doc.fiscal_year && !doc.company) {
        console.warn('\n⚠️ WARNING: Both fiscal_year and company are not set!');
        console.log('Run check_fiscal_year() to diagnose');
    }
    
    console.log('\n=== Items ===');
    if (doc.items && doc.items.length > 0) {
        console.table(doc.items.map(item => ({
            item_code: item.item_code,
            expense_account: item.expense_account,
            amount: item.amount,
            qty: item.qty,
            rate: item.rate
        })));
    } else {
        console.log('❌ No items found!');
    }
}

// ============================================================================
// 4. MANUAL TRIGGER RESERVE BUDGET
// ============================================================================
window.trigger_reserve_budget = function(expense_request_name) {
    const docname = expense_request_name || (cur_frm && cur_frm.doc.name);
    
    if (!docname) {
        console.error('Please provide expense request name or open the document!');
        return;
    }
    
    console.log('🔄 Triggering reserve_budget_for_request for:', docname);
    console.log('⏳ Please wait...');
    
    frappe.call({
        method: 'imogi_finance.budget_control.workflow.reserve_budget_for_request_api',
        args: {
            expense_request: docname
        },
        freeze: true,
        freeze_message: __('Creating Budget Control Entry...'),
        callback: function(r) {
            console.log('\n=== Reserve Budget Result ===');
            if (r.message && r.message.length > 0) {
                console.log('✅ Success! Created entries:', r.message);
                console.table(r.message.map(name => ({entry: name})));
                
                // Reload document to show updated fields
                if (cur_frm && cur_frm.doc.name === docname) {
                    console.log('🔄 Reloading document...');
                    cur_frm.reload_doc();
                }
            } else if (r.exc) {
                console.error('❌ Error:', r.exc);
            } else {
                console.log('⚠️ Completed but no entries returned');
                console.log('Possible reasons:');
                console.log('- Budget lock disabled');
                console.log('- Document not in target state');
                console.log('- No budget configured');
            }
            
            // Check if entries were created
            setTimeout(() => {
                console.log('\n🔍 Verifying entries...');
                window.check_bce_exists(docname);
            }, 1500);
        },
        error: function(r) {
            console.error('❌ Error calling reserve_budget:', r);
            console.log('\n💡 Possible reasons:');
            console.log('1. Budget lock is disabled in settings');
            console.log('2. Document status is not "Approved"');
            console.log('3. No items with expense accounts');
            console.log('4. Fiscal year not found');
            console.log('5. Insufficient budget available');
            console.log('\nRun debug_budget_control() to investigate');
        }
    });
}

// ============================================================================
// 5. CEK APAKAH BUDGET DOCUMENT ADA
// ============================================================================
window.check_budget_exists = function() {
    if (!cur_frm || cur_frm.doctype !== 'Expense Request') {
        console.error('Please open an Expense Request first!');
        return;
    }
    
    const doc = cur_frm.doc;
    
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Budget',
            filters: {
                company: doc.company,
                cost_center: doc.cost_center
            },
            fields: ['name', 'fiscal_year', 'cost_center', 'docstatus']
        },
        callback: function(r) {
            console.log('=== Budget Documents ===');
            if (r.message && r.message.length > 0) {
                console.table(r.message);
                console.log(`✅ Found ${r.message.length} budget(s)`);
            } else {
                console.log('❌ NO Budget found for this Cost Center!');
                console.log('Cost Center:', doc.cost_center);
                console.log('Company:', doc.company);
            }
        }
    });
}

// ============================================================================
// 6. FULL DEBUG - JALANKAN SEMUA CHECKS
// ============================================================================
window.debug_budget_control = function(expense_request_name) {
    const docname = expense_request_name || (cur_frm && cur_frm.doc.name);
    
    console.log('======================================');
    console.log('BUDGET CONTROL FULL DEBUG');
    console.log('======================================');
    console.log('Document:', docname);
    console.log('Time:', new Date().toISOString());
    console.log('');
    
    // 1. Check settings
    check_budget_settings();
    
    setTimeout(() => {
        // 2. Check dimensions
        check_budget_dimensions();
        
        setTimeout(() => {
            // 3. Check budget exists
            check_budget_exists();
            
            setTimeout(() => {
                // 4. Check BCE exists
                check_bce_exists(docname);
                
                console.log('\n======================================');
                console.log('DEBUG COMPLETED');
                console.log('======================================');
            }, 500);
        }, 500);
    }, 500);
}

// ============================================================================
// 7. HELPER: RELOAD DOCUMENT
// ============================================================================
window.reload_doc = function() {
    if (cur_FISCAL YEAR
// ============================================================================
window.check_fiscal_year = function() {
    console.log('=== Checking Fiscal Year Configuration ===\n');
    
    // Check System Settings
    frappe.db.get_single_value('System Settings', 'current_fiscal_year')
        .then(fy => {
            console.log('System Settings > Current Fiscal Year:', fy || '❌ NOT SET');
            return frappe.call({
                method: 'frappe.client.get_value',
                args: {
                    doctype: 'User',
                    filters: { name: frappe.session.user },
                    fieldname: ['defaults']
                }
            });
        })
        .then(r => {
            console.log('User Defaults for', frappe.session.user + ':');
            if (r.message && r.message.defaults) {
                try {
                    const defaults = JSON.parse(r.message.defaults);
                    console.log('  Fiscal Year:', defaults.fiscal_year || '❌ NOT SET');
                } catch(e) {
                    console.log('  ❌ No defaults set');
                }
            } else {
                console.log('  ❌ No defaults set');
            }
            
            // List all fiscal years
   11        return frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Fiscal Year',
                    fields: ['name', 'year_start_date', 'year_end_date', 'disabled'],
                    order_by: 'year_start_date desc',
                    limit: 5
                }
            });
        })
        .then(r => {
            console.log('\nAvailable Fiscal Years:');
            if (r.message && r.message.length > 0) {
                console.table(r.message);
            } else {
                console.log('❌ No Fiscal Years found!');
            }
            
            console.log('\n💡 To fix:');
            console.log('Option 1: Set default in System Settings');
            console.log('  Setup > System Settings > Current Fiscal Year');
            console.log('');
            console.log('Option 2: Set for your user');
            console.log('  set_fiscal_year("2026")');
        })
        .catch(err => {
            console.error('Error:', err);
        });
}

// ============================================================================
// 9. SET FISCAL YEAR FOR CURRENT USER
// ============================================================================
window.set_fiscal_year = function(fiscal_year) {
    if (!fiscal_year) {
        console.error('Please provide fiscal year name, e.g., set_fiscal_year("2026")');
        return;
    }
    
    console.log('🔄 Setting fiscal_year to:', fiscal_year);
    
    frappe.call({
        method: 'frappe.defaults.set_user_default',
        args: {
            key: 'fiscal_year',
            value: fiscal_year
        },
        callback: function(r) {
            if (!r.exc) {
                console.log('✅ Fiscal year set successfully!');
                console.log('Now try: trigger_reserve_budget()');
            } else {
                console.error('❌ Failed to set fiscal year');
            }
        }
    });
}

// ============================================================================
// 10. CHECK IF HOOKS ARE WORKING
// ============================================================================
window.check_hooks = function() {
    console.log('=== Checking Event Hooks ===');
    
    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype: 'Error Log',
            filters: {
                error: ['like', '%handle_budget_workflow%']
            },
            fields: ['name', 'creation', 'error'],
            order_by: 'creation desc',
            limit: 5
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                console.log('⚠️ Found errors related to budget workflow:');
                console.table(r.message);
            } else {
                console.log('✅ No errors found for budget workflow hooks');
            }
        }
    });
    
    console.log('\n💡 To verify hooks are active:');
    console.log('1. Edit and save ER → Check browser console for log messages');
    console.log('2. Or check: Setup > System Console > View Logs');
}

// ============================================================================
// 11. SIMULATE APPROVAL (FOR TESTING)
// ============================================================================
window.simulate_approval = function() {
    if (!cur_frm || cur_frm.doctype !== 'Expense Request') {
        console.error('Please open an Expense Request first!');
        return;
    }
    
    console.log('⚠️ SIMULATING APPROVAL WORKFLOW');
    console.log('This will manually call handle_budget_workflow');
    console.log('');
    
    const doc = cur_frm.doc;
    
    if (doc.workflow_state !== 'Approved') {
        console.error('❌ Document must be in Approved state first!');
        console.log('Current state:', doc.workflow_state);
        return;
    }
    
    console.log('🔄 Calling handle_budget_workflow...');
    
    frappe.call({
        method: 'imogi_finance.events.expense_request.handle_budget_workflow',
        args: {
            doc: doc,
            method: 'on_update_after_submit'
        },
        freeze: true,
        callback: function(r) {
            console.log('✅ Hook called!');
            if (r.message) {
                console.log('Result:', r.message);
            }
            
            setTimeout(() => {
                cur_frm.reload_doc();
                window.check_bce_exists(doc.name);
            }, 1000);
        },
        error: function(r) {
            console.error('❌ Error:', r);
        }
    });
}

// ============================================================================
// INSTRUCTIONS
// ============================================================================
console.log('==============================================');
console.log('Budget Control Debug Commands Loaded!');
console.log('==============================================');
console.log('');
console.log('Available Commands:');
console.log('1. check_bce_exists()         - Cek apakah Budget Control Entry sudah dibuat');
console.log('Quick Start:');
console.log('1. Buka Expense Request yang sudah Approved');
console.log('2. Run: debug_budget_control()');
console.log('3. If fiscal year error: check_fiscal_year() then set_fiscal_year("2026")');
console.log('4. Try again: trigger_reserve_budget()');
console.log('');
console.log('Manual Trigger:');
console.log('trigger_reserve_budget()');
console.log('');
console.log('Fix Fiscal Year Error:');
console.log('1. check_fiscal_year()');
console.log('2. set_fiscal_year("2026")');
console.log('3. trigger_reserve_budget(
        args: {
            doctype: 'Error Log',
            filters: {
                error: ['like', '%handle_budget_workflow%']
            },
            fields: ['name', 'creation', 'error'],
            order_by: 'creation desc',
            limit: 5
        },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                console.log('⚠️ Found errors related to budget workflow:');
                console.table(r.message);
            } else {
                console.log('✅ No errors found for budget workflow hooks');
            }
        }
    });
    
    console.log('\n💡 To verify hooks are active:');
    console.log('1. Edit and save ER → Check browser console for log messages');
    console.log('2. Or check: Setup > System Console > View Logs');
}

// ============================================================================
// 9. SIMULATE APPROVAL (FOR TESTING)
// ============================================================================
window.simulate_approval = function() {
    if (!cur_frm || cur_frm.doctype !== 'Expense Request') {
        console.error('Please open an Expense Request first!');
        return;
    }
    
    console.log('⚠️ SIMULATING APPROVAL WORKFLOW');
    console.log('This will manually call handle_budget_workflow');
    console.log('');
    
    const doc = cur_frm.doc;
    
    if (doc.workflow_state !== 'Approved') {
        console.error('❌ Document must be in Approved state first!');
        console.log('Current state:', doc.workflow_state);
        return;
    }
    
    console.log('🔄 Calling handle_budget_workflow...');
    
    frappe.call({
        method: 'imogi_finance.events.expense_request.handle_budget_workflow',
        args: {
            doc: doc,
            method: 'on_update_after_submit'
        },
        freeze: true,
        callback: function(r) {
            console.log('✅ Hook called!');
            if (r.message) {
                console.log('Result:', r.message);
            }
            
            setTimeout(() => {
                cur_frm.reload_doc();
                window.check_bce_exists(doc.name);
            }, 1000);
        },
        error: function(r) {
            console.error('❌ Error:', r);
        }
    });
}

// ============================================================================
// INSTRUCTIONS
// ============================================================================
console.log('==============================================');
console.log('Budget Control Debug Commands Loaded!');
console.log('==============================================');
console.log('');
console.log('Available Commands:');
console.log('1. check_bce_exists()        - Cek apakah Budget Control Entry sudah dibuat');
console.log('2. check_budget_settings()   - Cek konfigurasi Budget Control Setting');
console.log('3. check_budget_dimensions() - Cek dimensi budget (cost center, account, dll)');
console.log('4. trigger_reserve_budget()  - Manual trigger reserve budget');
console.log('5. check_budget_exists()     - Cek apakah Budget document ada');
console.log('6. debug_budget_control()    - Jalankan semua checks');
console.log('7. reload_doc()              - Reload document');
console.log('8. check_hooks()             - Check if hooks are working');
console.log('9. simulate_approval()       - Simulate approval workflow (for testing)');
console.log('');
console.log('Quick Start:');
console.log('1. Buka Expense Request yang sudah Approved');
console.log('2. Run: debug_budget_control()');
console.log('3. Lihat hasil di console');
console.log('');
console.log('Manual Trigger (RECOMMENDED):');
console.log('trigger_reserve_budget()');
console.log('');
console.log('Or for specific document:');
console.log('trigger_reserve_budget("ER-2026-000027")');
console.log('==============================================');
