from __future__ import annotations

import frappe

from imogi_finance.imogi_finance.indonesia_tax_setup import (
    AccountResolver,
    ensure_tax_template,
    ensure_withholding_category,
    ensure_withholding_tax,
    load_payroll_account_names,
)


def _resolve_accounts(resolver: AccountResolver) -> dict[str, str | None]:
    accounts = {
        "ppn_output": resolver.resolve(
            "ppn_output",
            ["Tax Payable PPN"],
            keywords=["PPN", "VAT"],
            root_type="Liability",
            account_type="Tax",
        ),
        "ppn_input": resolver.resolve(
            "ppn_input",
            ["PPN Lebih Bayar"],
            keywords=["PPN", "VAT", "Input", "Lebih"],
            root_type="Asset",
            account_type="Tax",
        ),
        "ppnbm": resolver.resolve(
            "ppnbm",
            ["PPNBM Payable"],
            keywords=["PPNBM"],
            root_type="Liability",
            account_type="Tax",
        ),
        "pb1": resolver.resolve(
            "pb1",
            ["PB1 Payable", "PB1 Tax Payable"],
            keywords=["PB1"],
            root_type="Liability",
            account_type="Tax",
        ),
        "pph22": resolver.resolve(
            "pph22",
            ["Tax Payable PPh 22", "Tax Payable PPh"],
            keywords=["PPh 22", "Withholding"],
            root_type="Liability",
        ),
        "pph23": resolver.resolve(
            "pph23",
            ["Tax Payable PPh 23", "Tax Payable PPh"],
            keywords=["PPh 23", "Withholding"],
            root_type="Liability",
        ),
        "pph26": resolver.resolve(
            "pph26",
            ["Tax Payable PPh 26", "Tax Payable PPh"],
            keywords=["PPh 26", "Withholding"],
            root_type="Liability",
        ),
        "pph42": resolver.resolve(
            "pph42",
            ["Tax Payable PPh Final", "Tax Payable PPh 4(2)"],
            keywords=["PPh Final", "PPh 4(2)", "Withholding"],
            root_type="Liability",
        ),
    }
    return accounts


def _setup_tax_templates(company: str, accounts: dict[str, str | None], logger) -> None:
    templates = []
    ppn_output = accounts.get("ppn_output")
    ppn_input = accounts.get("ppn_input")
    ppnbm_account = accounts.get("ppnbm") or ppn_output
    pb1_account = accounts.get("pb1")

    if ppn_output:
        templates.append(
            ensure_tax_template(
                title="ID - PPN 11% Output",
                company=company,
                account=ppn_output,
                rate=11.0,
                template_type="Sales",
            )
        )
        templates.append(
            ensure_tax_template(
                title="ID - PPN 12% Output",
                company=company,
                account=ppn_output,
                rate=12.0,
                template_type="Sales",
            )
        )
        templates.append(
            ensure_tax_template(
                title="ID - PPN 0% Export",
                company=company,
                account=ppn_output,
                rate=0.0,
                template_type="Sales",
            )
        )

    if ppn_input:
        templates.append(
            ensure_tax_template(
                title="ID - PPN 11% Input",
                company=company,
                account=ppn_input,
                rate=11.0,
                template_type="Purchase",
            )
        )
        templates.append(
            ensure_tax_template(
                title="ID - PPN 12% Input",
                company=company,
                account=ppn_input,
                rate=12.0,
                template_type="Purchase",
            )
        )

    if ppnbm_account:
        for rate in (10, 20, 30, 40, 50, 70, 95):
            templates.append(
                ensure_tax_template(
                    title=f"ID - PPNBM {rate}%",
                    company=company,
                    account=ppnbm_account,
                    rate=float(rate),
                    template_type="Sales",
                )
            )

    if pb1_account:
        templates.append(
            ensure_tax_template(
                title="ID - PB1 10%",
                company=company,
                account=pb1_account,
                rate=10.0,
                template_type="Sales",
            )
        )

    templates = [name for name in templates if name]
    if templates:
        logger.info({"company": company, "templates": templates})


def _setup_withholding(company: str, accounts: dict[str, str | None], logger) -> None:
    withholding_defs = [
        {
            "category": "ID - PPh 23",
            "items": [
                {"name": "ID - PPh 23 2%", "rate": 2.0, "account": accounts.get("pph23")},
                {"name": "ID - PPh 23 15%", "rate": 15.0, "account": accounts.get("pph23")},
            ],
        },
        {
            "category": "ID - PPh 26",
            "items": [
                {"name": "ID - PPh 26 20%", "rate": 20.0, "account": accounts.get("pph26")},
            ],
        },
        {
            "category": "ID - PPh 22",
            "items": [
                {"name": "ID - PPh 22 1.5%", "rate": 1.5, "account": accounts.get("pph22")},
                {"name": "ID - PPh 22 2.5%", "rate": 2.5, "account": accounts.get("pph22")},
                {"name": "ID - PPh 22 7.5%", "rate": 7.5, "account": accounts.get("pph22")},
            ],
        },
        {
            "category": "ID - PPh 4(2)",
            "items": [
                {"name": "ID - PPh 4(2) 10%", "rate": 10.0, "account": accounts.get("pph42")},
                {"name": "ID - PPh 4(2) 0.5%", "rate": 0.5, "account": accounts.get("pph42")},
                {"name": "ID - PPh 4(2) 3%", "rate": 3.0, "account": accounts.get("pph42")},
            ],
        },
    ]

    for entry in withholding_defs:
        created: list[str] = []
        for item in entry["items"]:
            if not item.get("account"):
                continue
            wt_name = ensure_withholding_tax(company, item["name"], item["account"], item["rate"])
            if wt_name:
                created.append(wt_name)

        if created:
            category_name = ensure_withholding_category(company, entry["category"], created)
            logger.info({"company": company, "withholding_category": category_name, "withholding_taxes": created})


def execute():
    if not frappe.db.table_exists("Company"):
        return

    payroll_accounts = load_payroll_account_names()
    companies = frappe.get_all("Company", filters={"is_group": 0}, fields=["name", "abbr"])
    logger = frappe.logger("imogi_finance.indonesia_tax_setup")

    for company in companies:
        resolver = AccountResolver(company["name"], company.get("abbr"), payroll_accounts)
        accounts = _resolve_accounts(resolver)
        if resolver.log:
            logger.info({"company": company["name"], "account_resolution": resolver.log})

        _setup_tax_templates(company["name"], accounts, logger)
        _setup_withholding(company["name"], accounts, logger)
