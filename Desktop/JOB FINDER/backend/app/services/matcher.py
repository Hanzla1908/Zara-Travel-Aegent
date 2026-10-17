"""
Deterministic job-match scoring service.

Python handles all numeric scoring so results are reproducible and testable.
Claude is called only to generate natural-language explanations — never for
scoring decisions.

Security notes:
  - Raw CV text is never passed to Claude in this module.
  - Only structured fields (skills list, years int, titles list, location str)
    are used for matching and for the Claude prompt.
  - Claude prompt strings are fully template-controlled; no user-supplied text
    is injected unescaped into the system prompt.
  - Missing job data returns a neutral score rather than zero — we never
    penalise the candidate for data the job listing chose not to provide.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class MatchWeights:
    """Configurable weights. Must sum to 1.0 (±0.001 tolerance)."""
    skills:     float = 0.50
    experience: float = 0.25
    title:      float = 0.15
    location:   float = 0.10

    def __post_init__(self) -> None:
        total = self.skills + self.experience + self.title + self.location
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"MatchWeights must sum to 1.0, got {total:.4f}. "
                "Normalise before constructing."
            )


DEFAULT_WEIGHTS = MatchWeights()

# Maps job experience level strings to (min_years, max_years) of a "perfect" score.
_EXPERIENCE_RANGES: dict[str, tuple[int, int]] = {
    "Junior": (0, 2),
    "Mid":    (2, 5),
    "Senior": (5, 9),
    "Lead":   (8, 20),
}

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class ScoreBreakdown:
    skills:     float   # 0–100
    experience: float   # 0–100
    title:      float   # 0–100
    location:   float   # 0–100
    total:      float   # 0–100 weighted


@dataclass
class MatchResult:
    job_id:         int
    score:          float           # 0–100, 1 dp
    breakdown:      ScoreBreakdown
    matched_skills: list[str]
    missing_skills: list[str]
    reasons:        list[str]       # deterministic bullet points
    explanation:    str = ""        # Claude-generated prose, filled later


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalise(text: str) -> str:
    return text.lower().strip()


def _tokenise(text: str) -> set[str]:
    """Split on non-alphanumeric chars; keep tokens of length ≥ 2."""
    return {t for t in re.split(r"[^a-z0-9#+.]+", _normalise(text)) if len(t) >= 2}


_STOP: frozenset[str] = frozenset({
    "and", "or", "the", "of", "in", "to", "for", "with", "on", "at",
    "an", "be", "is", "as", "by", "we", "our", "you", "your", "will",
    "are", "have", "has", "can", "not", "plus", "years", "year",
    "experience", "experiences", "skills", "skill", "strong", "good",
    "knowledge", "ability", "proficiency", "preferred", "required",
    "minimum", "equivalent", "related", "relevant", "looking", "join",
    "team", "role", "build", "work", "write", "use", "own", "drive",
    "mentor", "lead", "deliver", "implement", "design", "collaborate",
    "develop", "manage", "support", "ensure", "maintain", "create",
    "provide", "including", "across", "hiring", "clients", "global",
    "cutting", "edge", "entire", "modern", "tooling", "products",
    "domains", "autonomy", "stack", "growing", "senior", "junior",
    "level", "mid", "entry", "associate",
})

# Tokens that look like bare numbers or quantities ("3+", "5+", "10") are not skills.
_NUMERIC_RE = re.compile(r"^\d+\+?$")


def _is_skill_candidate(token: str) -> bool:
    return (
        len(token) >= 2
        and token not in _STOP
        and not _NUMERIC_RE.match(token)
    )


def _extract_skill_keywords(requirements: list[str], description: str = "") -> list[str]:
    """
    Extract candidate skill keywords from job requirements bullet-points.
    Description text is only used when requirements are empty.
    Never invents skills not present in the source text.
    """
    source = " ".join(requirements) if requirements else description
    tokens = _tokenise(source)
    return sorted(t for t in tokens if _is_skill_candidate(t))


# ---------------------------------------------------------------------------
# Component scorers — pure functions, no I/O
# ---------------------------------------------------------------------------

def score_skills(
    cv_skills: list[str],
    job_requirements: list[str],
    job_description: str = "",
) -> tuple[float, list[str], list[str]]:
    """
    Returns (score 0–100, matched_skills, missing_skills).

    If the job provides no requirements and no description, the score is 50
    (neutral) so the candidate is not penalised for the listing's omission.
    """
    job_keywords = _extract_skill_keywords(job_requirements, job_description)
    if not job_keywords:
        return 50.0, [], []

    cv_norm = {_normalise(s) for s in cv_skills}
    matched = [k for k in job_keywords if k in cv_norm]
    missing = [k for k in job_keywords if k not in cv_norm]
    score   = len(matched) / len(job_keywords) * 100
    return round(score, 1), matched, missing


def score_experience(cv_years: int, job_experience_level: str) -> float:
    """
    Returns 0–100.
    Perfect match within the target range → 100.
    Below minimum → linear ramp: 0 → 80 as years approach the minimum.
    Above maximum → 80 (overqualified; not heavily penalised).
    """
    level = job_experience_level.strip().title()
    lo, hi = _EXPERIENCE_RANGES.get(level, (2, 5))   # default: Mid
    if lo <= cv_years <= hi:
        return 100.0
    if cv_years < lo:
        if lo == 0:
            return 100.0
        return round(cv_years / lo * 80, 1)
    return 80.0   # overqualified


def score_title(cv_titles: list[str], job_title: str) -> float:
    """
    Returns 0–100 based on keyword overlap between the candidate's titles
    and the job title.
    """
    if not cv_titles:
        return 30.0   # no title data — neutral-low
    job_tokens = _tokenise(job_title)
    if not job_tokens:
        return 50.0
    best = 0.0
    for ct in cv_titles:
        cv_tokens = _tokenise(ct)
        if not cv_tokens:
            continue
        overlap = job_tokens & cv_tokens
        ratio   = len(overlap) / len(job_tokens) * 100
        best    = max(best, ratio)
    return round(min(best, 100.0), 1)


def score_location(
    cv_location: str,
    job_location: str,
    job_location_type: str,
) -> float:
    """
    Returns 0–100.
    Remote  → 100 for all candidates.
    Hybrid  → 70.
    On-site, exact city match → 100.
    On-site, same country     → 60.
    No location data          → 50 (neutral — don't punish missing data).
    Different regions         → 20.
    """
    loc_type = _normalise(job_location_type)
    if "remote" in loc_type:
        return 100.0
    if "hybrid" in loc_type:
        return 70.0
    if not cv_location or not job_location:
        return 50.0
    cv_parts  = [p.strip().lower() for p in cv_location.split(",")]
    job_parts = [p.strip().lower() for p in job_location.split(",")]
    if cv_parts[0] and cv_parts[0] == job_parts[0]:
        return 100.0
    if cv_parts[-1] and cv_parts[-1] == job_parts[-1]:
        return 60.0
    return 20.0


# ---------------------------------------------------------------------------
# Reason generator — deterministic, no I/O
# ---------------------------------------------------------------------------

def build_reasons(
    breakdown: ScoreBreakdown,
    matched_skills: list[str],
    missing_skills: list[str],
    cv_years: int,
    job_experience_level: str,
) -> list[str]:
    reasons: list[str] = []

    # Skills
    total_skills = len(matched_skills) + len(missing_skills)
    if total_skills == 0:
        reasons.append("Skill match: no structured requirements listed — rated neutral.")
    elif matched_skills:
        top = ", ".join(matched_skills[:5]) + ("…" if len(matched_skills) > 5 else "")
        reasons.append(
            f"Skill match: {len(matched_skills)}/{total_skills} required skills matched ({top})."
        )
    else:
        reasons.append("Skill match: none of the required skills found in your CV.")

    if missing_skills:
        top_m = ", ".join(missing_skills[:5]) + ("…" if len(missing_skills) > 5 else "")
        reasons.append(f"Missing skills: {top_m}.")

    # Experience
    level = job_experience_level.strip().title()
    lo, hi = _EXPERIENCE_RANGES.get(level, (2, 5))
    if cv_years < lo:
        gap = lo - cv_years
        reasons.append(
            f"Experience gap: role targets {level} ({lo}–{hi} yrs); "
            f"your CV shows {cv_years} yr{'s' if cv_years != 1 else ''} "
            f"({gap} yr{'s' if gap != 1 else ''} short)."
        )
    elif cv_years > hi:
        reasons.append(
            f"Overqualified for {level} level "
            f"(you have {cv_years} yrs; role targets {lo}–{hi} yrs)."
        )
    else:
        reasons.append(
            f"Experience aligned: {cv_years} yr{'s' if cv_years != 1 else ''} "
            f"fits the {level} range ({lo}–{hi} yrs)."
        )

    # Location
    loc = breakdown.location
    if loc >= 100.0:
        reasons.append("Location: remote or exact city match — no commute barrier.")
    elif loc >= 70.0:
        reasons.append("Location: hybrid role — occasional on-site required.")
    elif loc >= 60.0:
        reasons.append("Location: same country but different city.")
    elif loc >= 50.0:
        reasons.append("Location: insufficient data to assess.")
    else:
        reasons.append("Location: different region — relocation or remote arrangement needed.")

    return reasons


# ---------------------------------------------------------------------------
# Core match calculator — synchronous, pure
# ---------------------------------------------------------------------------

def calculate_match(
    cv: dict,
    job: dict,
    weights: MatchWeights = DEFAULT_WEIGHTS,
) -> MatchResult:
    """
    Score a single job against a CV profile dict.

    Expected cv keys : skills (list[str]), experience_years (int),
                       job_titles (list[str]), location (str).
    Expected job keys: id (int), title (str), requirements (list[str]),
                       description (str), experience (str),
                       location (str), location_type (str).
    Any missing key is treated as empty/zero — never invented.
    """
    cv_skills    = cv.get("skills") or []
    cv_years     = int(cv.get("experience_years") or 0)
    cv_titles    = cv.get("job_titles") or []
    cv_location  = cv.get("location") or ""

    job_id       = int(job.get("id") or 0)
    job_title    = job.get("title") or ""
    job_req      = job.get("requirements") or []
    job_desc     = job.get("description") or ""
    job_exp_lvl  = job.get("experience") or "Mid"
    job_location = job.get("location") or ""
    job_loc_type = job.get("location_type") or "On-site"

    s_skills, matched, missing = score_skills(cv_skills, job_req, job_desc)
    s_exp      = score_experience(cv_years, job_exp_lvl)
    s_title    = score_title(cv_titles, job_title)
    s_location = score_location(cv_location, job_location, job_loc_type)

    total = (
        weights.skills     * s_skills
        + weights.experience * s_exp
        + weights.title      * s_title
        + weights.location   * s_location
    )
    total = round(min(max(total, 0.0), 100.0), 1)

    breakdown = ScoreBreakdown(
        skills=s_skills,
        experience=s_exp,
        title=s_title,
        location=s_location,
        total=total,
    )
    reasons = build_reasons(breakdown, matched, missing, cv_years, job_exp_lvl)

    return MatchResult(
        job_id=job_id,
        score=total,
        breakdown=breakdown,
        matched_skills=matched,
        missing_skills=missing,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# Claude explanation — optional async enrichment
# ---------------------------------------------------------------------------

def _template_explanation(result: MatchResult, job_title: str, company: str) -> str:
    n_matched = len(result.matched_skills)
    n_total   = n_matched + len(result.missing_skills)
    skill_part = (
        f"You matched {n_matched} of {n_total} required skills"
        + (f", including {result.matched_skills[0]}" if result.matched_skills else "")
        + "."
    ) if n_total else "No structured skill requirements were listed for this role."
    gap_part = (
        f" Key gaps: {', '.join(result.missing_skills[:3])}." if result.missing_skills
        else " No critical skill gaps were identified."
    )
    return skill_part + gap_part


async def _explain_with_claude(result: MatchResult, job_title: str, company: str) -> str:
    """
    Returns a 2-sentence natural-language explanation.
    Falls back silently to a template string on any failure.
    """
    from app.config import settings
    if not settings.anthropic_api_key:
        return _template_explanation(result, job_title, company)
    try:
        import httpx
        import anthropic

        http_client = httpx.AsyncClient(headers={"accept-encoding": "identity"})
        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            http_client=http_client,
        )
        n_matched = len(result.matched_skills)
        n_missing = len(result.missing_skills)
        prompt = (
            f"Job: {job_title} at {company}\n"
            f"Match score: {result.score}/100\n"
            f"Matched skills ({n_matched}): {', '.join(result.matched_skills[:8]) or 'none'}\n"
            f"Missing skills ({n_missing}): {', '.join(result.missing_skills[:5]) or 'none'}\n"
            f"Experience component: {result.breakdown.experience}/100\n"
            f"Location component: {result.breakdown.location}/100\n\n"
            "Write exactly 2 short sentences (under 60 words total) explaining this match score. "
            "Be specific about the skills and gaps. No bullet points. No markdown."
        )
        msg = await client.messages.create(
            model="claude-haiku-5-5",
            max_tokens=120,
            system="You summarise job-match scores concisely. Output plain prose only.",
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception:
        logger.debug("Claude explanation unavailable; using template.")
        return _template_explanation(result, job_title, company)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def rank_jobs(
    cv: dict,
    jobs: list[dict],
    weights: MatchWeights = DEFAULT_WEIGHTS,
    explain: bool = False,
) -> list[MatchResult]:
    """
    Score and rank *jobs* against *cv*, returning results sorted by score
    descending.

    *explain=True* calls Claude for each job explanation (costs API tokens).
    Callers should only set explain=True when the user explicitly requests it.
    """
    pairs: list[tuple[MatchResult, dict]] = [
        (calculate_match(cv, job, weights), job)
        for job in jobs
    ]
    pairs.sort(key=lambda p: p[0].score, reverse=True)

    if explain:
        for result, job in pairs:
            result.explanation = await _explain_with_claude(
                result,
                job.get("title", ""),
                job.get("company", ""),
            )

    return [result for result, _ in pairs]
