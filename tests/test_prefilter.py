from jobpipe.scoring.prefilter import critical_skill_hits, passes_prefilter


def test_critical_skill_hits_returns_expected_matches() -> None:
    text = "Backend role with Python, SQL, and API design"
    hits = critical_skill_hits(text, ["python", "aws", "sql"])
    assert hits == ["python", "sql"]


def test_passes_prefilter_false_for_reject_terms() -> None:
    allowed = passes_prefilter(
        title="Senior Backend Engineer",
        description="Python FastAPI services",
        critical_skills=["python", "fastapi"],
        reject_terms=["senior"],
    )
    assert allowed is False


def test_passes_prefilter_true_for_matching_skill_without_reject_terms() -> None:
    allowed = passes_prefilter(
        title="Backend Engineer",
        description="Build APIs in Python and SQL",
        critical_skills=["python", "go"],
        reject_terms=["principal"],
    )
    assert allowed is True
