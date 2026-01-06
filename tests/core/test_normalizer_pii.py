from unittest.mock import MagicMock, patch

from svalinn_ai.core.normalizer import AdvancedTextNormalizer


def test_pii_initialization_failure(caplog):
    """Test that we gracefully handle missing Presidio/models."""
    with patch("svalinn_ai.core.normalizer.AnalyzerEngine", side_effect=ImportError("No module")):
        norm = AdvancedTextNormalizer(config={"enabled_steps": {"pii_redaction": True}})
        assert norm.analyzer is None
        assert "Failed to initialize PII Redaction" in caplog.text


def test_pii_redaction_call():
    """Test that _redact_pii calls the analyzer and anonymizer."""
    mock_analyzer = MagicMock()
    mock_anonymizer = MagicMock()

    # Mock return values
    mock_results = [MagicMock()]
    mock_anonymized = MagicMock()
    mock_anonymized.text = "My phone is <PHONE_NUMBER>"

    mock_analyzer.analyze.return_value = mock_results
    mock_anonymizer.anonymize.return_value = mock_anonymized

    with (
        patch("svalinn_ai.core.normalizer.AnalyzerEngine", return_value=mock_analyzer),
        patch("svalinn_ai.core.normalizer.AnonymizerEngine", return_value=mock_anonymizer),
    ):
        norm = AdvancedTextNormalizer(config={"enabled_steps": {"pii_redaction": True}})

        result = norm.normalize("My phone is 555-0199")

        # Verify calls
        mock_analyzer.analyze.assert_called_once()
        mock_anonymizer.anonymize.assert_called_once()
        assert "<phone_number>" in result.lower()  # Normalize lowercases everything eventually


def test_pii_disabled():
    """Test that we skip PII if disabled."""
    norm = AdvancedTextNormalizer(config={"enabled_steps": {"pii_redaction": False}})
    # No mocks needed as it shouldn't try to init them
    assert norm.analyzer is None

    result = norm.normalize("My phone is 123-4567")
    assert "123-4567" in result
