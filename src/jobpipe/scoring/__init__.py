"""Scoring primitives for JobPipe."""
from jobpipe.scoring.calculator import (
    ScoreBreakdown,
    ScoreWeights,
    SectionWeights,
    compute_blended_relevance,
    compute_confidence,
    compute_section_weighted_relevance,
    compute_total_match_score,
    select_weights_for_job_type,
)
from jobpipe.scoring.cv_parser import ParsedCV, parse_cv_file, parse_cv_text
from jobpipe.scoring.domain_matcher import domain_alignment_score
from jobpipe.scoring.keyword_scorer import build_keyword_lexicon, keyword_density_score
