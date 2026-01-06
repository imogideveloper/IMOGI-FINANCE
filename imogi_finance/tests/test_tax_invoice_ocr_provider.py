import pytest

from imogi_finance import tax_invoice_ocr


def _settings(endpoint: str) -> dict:
    return {
        "ocr_provider": "Google Vision",
        "google_vision_service_account_file": "dummy.json",
        "google_vision_endpoint": endpoint,
    }


def test_google_vision_accepts_files_annotate_endpoint():
    tax_invoice_ocr._validate_provider_settings(
        "Google Vision",
        _settings("https://vision.googleapis.com/v1/files:annotate"),
    )


def test_google_vision_rejects_images_endpoint():
    with pytest.raises(tax_invoice_ocr.ValidationError):
        tax_invoice_ocr._validate_provider_settings(
            "Google Vision",
            _settings("https://vision.googleapis.com/v1/images:annotate"),
        )
