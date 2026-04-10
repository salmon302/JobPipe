from jobpipe.scoring.extractors import extract_years_required, infer_remote


def test_extract_years_required_range_uses_upper_bound() -> None:
    text = "We are looking for engineers with 2-4 years experience."
    assert extract_years_required(text) == 4


def test_extract_years_required_single_value() -> None:
    text = "3+ years of backend engineering experience"
    assert extract_years_required(text) == 3


def test_infer_remote_returns_true_when_remote_keywords_present() -> None:
    assert infer_remote("Fully remote role in US timezone") is True


def test_infer_remote_returns_false_for_onsite_only() -> None:
    assert infer_remote("On-site role in San Francisco") is False
