from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, Optional

import frappe
from frappe import _


def get_receipt_control_settings():
    """Fetch Finance Control Settings with sane defaults."""

    from imogi_finance.branching import BRANCH_SETTING_DEFAULTS

    defaults = frappe._dict(
        {
            "enable_customer_receipt": 0,
            "receipt_mode": "OFF",
            "allow_mixed_payment": 0,
            "default_receipt_design": None,
            "enable_digital_stamp": 0,
            "digital_stamp_policy": "Optional",
            "digital_stamp_threshold_amount": 0,
            "allow_physical_stamp_fallback": 0,
            "digital_stamp_provider": None,
            "provider_mode": None,
        }
    )
    defaults.update(BRANCH_SETTING_DEFAULTS)

    if not frappe.db.exists("DocType", "Finance Control Settings"):
        return defaults

    try:
        settings = frappe.get_single("Finance Control Settings")
    except Exception:
        # Avoid breaking desk if single is missing in early migrations
        return defaults

    for key in defaults.keys():
        defaults[key] = getattr(settings, key, defaults[key])

    return defaults


def terbilang_id(amount: float | int | Decimal, suffix: str = "rupiah") -> str:
    """Convert numbers into Indonesian words.

    This is intentionally lightweight to avoid additional dependencies while
    remaining suitable for printing on receipts.
    """

    units = [
        "",
        "satu",
        "dua",
        "tiga",
        "empat",
        "lima",
        "enam",
        "tujuh",
        "delapan",
        "sembilan",
    ]

    def _spell_below_thousand(value: int) -> str:
        hundreds, rem = divmod(value, 100)
        tens, ones = divmod(rem, 10)
        words = []
        if hundreds:
            if hundreds == 1:
                words.append("seratus")
            else:
                words.append(f"{units[hundreds]} ratus")
        if tens > 1:
            words.append(f"{units[tens]} puluh")
            if ones:
                words.append(units[ones])
        elif tens == 1:
            if ones == 0:
                words.append("sepuluh")
            elif ones == 1:
                words.append("sebelas")
            else:
                words.append(f"{units[ones]} belas")
        else:
            if ones:
                words.append(units[ones])
        return " ".join(words).strip()

    def _spell_chunk(value: int, magnitude: str) -> str:
        return f"{_spell_below_thousand(value)} {magnitude}".strip()

    def _split_chunks(number: int) -> Iterable[int]:
        while number:
            number, remainder = divmod(number, 1000)
            yield remainder

    magnitudes = ["", "ribu", "juta", "miliar", "triliun"]

    quantized = Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    integer_part = int(quantized)
    fraction = int((quantized - Decimal(integer_part)) * 100)

    if integer_part == 0:
        words = "nol"
    else:
        words = []
        for idx, chunk in enumerate(_split_chunks(integer_part)):
            if not chunk:
                continue
            if idx == 1 and chunk == 1:
                words.append("seribu")
            else:
                words.append(_spell_chunk(chunk, magnitudes[idx]))
        words = " ".join(reversed(words))

    if fraction:
        words = f"{words} koma {_spell_below_thousand(fraction)}"

    if suffix:
        words = f"{words} {suffix}".strip()

    return words


def build_verification_url(pattern: Optional[str], stamp_ref: Optional[str]) -> Optional[str]:
    if not pattern or not stamp_ref:
        return None
    return pattern.replace("{{stamp_ref}}", stamp_ref)
