import types

import imogi_finance.api.payroll_sync as payroll_sync


def test_is_payroll_installed_handles_errors(monkeypatch):
    calls = {"count": 0}

    def failing_installed_apps():
        calls["count"] += 1
        raise RuntimeError("apps unavailable")

    monkeypatch.setattr(payroll_sync.frappe, "get_installed_apps", failing_installed_apps, raising=False)

    assert payroll_sync.is_payroll_installed() is False
    assert calls["count"] == 1


def test_bpjs_contributions_fallback_to_gl(monkeypatch):
    profile = types.SimpleNamespace(bpjs_payable_account="2100")
    monkeypatch.setattr(payroll_sync, "_get_tax_profile", lambda *_args, **_kwargs: profile)
    monkeypatch.setattr(payroll_sync, "_get_gl_total", lambda *_args, **_kwargs: 7500.0)
    monkeypatch.setattr(payroll_sync, "is_payroll_installed", lambda: False)

    summary = payroll_sync.get_bpjs_contributions("Comp", "2024-01-01", "2024-01-31")

    assert summary["gl_total"] == 7500.0
    assert summary["rows"] == []
    assert summary["source"] == "GL"


def test_salary_component_gl_rows(monkeypatch):
    profile = types.SimpleNamespace(
        bpjs_payable_account="2100",
        pph_accounts=[types.SimpleNamespace(pph_type="PPh 21", payable_account="2200")],
    )

    doc = types.SimpleNamespace(
        earnings=[types.SimpleNamespace(salary_component="BPJS Kesehatan", amount=1000000)],
        deductions=[types.SimpleNamespace(salary_component="PPh 21", amount=250000)],
    )

    rows = payroll_sync._build_salary_component_gl_rows(doc, profile)

    assert any(row["account"] == "2100" and row["share"] == "employer" for row in rows)
    assert any(row["account"] == "2200" and row["share"] == "withholding" for row in rows)
