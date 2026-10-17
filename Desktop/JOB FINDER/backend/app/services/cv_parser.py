"""
CV text extraction and Claude-powered structured profile extraction.

Security notes:
- Raw CV text is never logged.
- Only the extracted structured fields are stored in the database.
- The Anthropic API key is read from environment via settings, never hardcoded.
"""

import io
import json
import re
import logging

from pydantic import ValidationError

from app.schemas.cv import ClaudeExtractedProfile

logger = logging.getLogger(__name__)

# Maximum characters of CV text sent to Claude (keeps cost low; covers ~2 pages)
_MAX_CV_CHARS = 4_000

_FALLBACK_SKILLS = [
    "Python", "JavaScript", "TypeScript", "React", "Vue", "Angular", "Node.js",
    "FastAPI", "Django", "Flask", "SQL", "PostgreSQL", "MySQL", "MongoDB",
    "Docker", "Kubernetes", "AWS", "GCP", "Azure", "Git", "REST APIs",
    "GraphQL", "Redux", "CSS", "HTML", "SCSS", "Tailwind", "Jest", "pytest",
    "Machine Learning", "TensorFlow", "PyTorch", "Pandas", "NumPy",
    "React Native", "Swift", "Kotlin",
]


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def _extract_text_from_pdf(data: bytes) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:
        return ""


def _extract_text_from_docx(data: bytes) -> str:
    try:
        import docx
        doc = docx.Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return ""


def _extract_text(file_bytes: bytes, content_type: str) -> str:
    if "pdf" in content_type:
        text = _extract_text_from_pdf(file_bytes)
    elif "word" in content_type or "docx" in content_type:
        text = _extract_text_from_docx(file_bytes)
    else:
        text = file_bytes.decode("utf-8", errors="ignore")
    # If library-based extraction yields nothing, try a plain UTF-8 decode
    # (handles test fixtures and rare encoding edge-cases)
    if not text.strip():
        text = file_bytes.decode("utf-8", errors="ignore")
    return text


# ---------------------------------------------------------------------------
# Claude extraction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are a CV/resume parser. Extract structured information from the provided CV text \
and return ONLY valid JSON with this exact structure — no markdown fences, no extra text:

{
  "skills": ["list of technical skills only"],
  "experience_years": 0,
  "education": "highest degree, e.g. BSc Computer Science",
  "job_titles": ["Most Recent Title", "Earlier Title"],
  "location": "City, Country"
}

Rules:
- skills: technical skills only (languages, frameworks, tools, platforms). Max 20 items.
- experience_years: total years of professional experience as an integer (0 if unknown).
- education: highest qualification as a short string, empty string if none found.
- job_titles: roles the person has held or is targeting, most recent first. Max 5 items.
- location: city/country from the CV header or contact section, empty string if absent.
"""


async def _call_claude(text: str) -> ClaudeExtractedProfile | None:
    """Call Claude to extract structured CV data. Returns None on any failure."""
    from app.config import settings  # imported here to allow test overrides

    if not settings.anthropic_api_key:
        return None

    try:
        # The bundled httpx2 library in anthropic<=1.15.0 has a decompression bug
        # (process() does not accept output_buffer_limit). Passing Accept-Encoding: identity
        # in a custom httpx client forces uncompressed responses and sidesteps the bug.
        import httpx
        import anthropic

        http_client = httpx.AsyncClient(
            headers={"accept-encoding": "identity"},
        )
        client = anthropic.AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            http_client=http_client,
        )

        message = await client.messages.create(
            model="claude-haiku-5-5",
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text[:_MAX_CV_CHARS]}],
        )

        raw = message.content[0].text.strip()

        # Strip any accidental markdown code fences
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw)

        parsed = json.loads(raw)
        return ClaudeExtractedProfile(**parsed)

    except (json.JSONDecodeError, ValidationError):
        logger.warning("Claude returned unparseable CV extraction; using fallback.")
        return None
    except Exception:
        logger.warning("Claude CV extraction unavailable; using fallback.")
        return None


# ---------------------------------------------------------------------------
# Regex fallback (used when Claude is unavailable or fails)
# ---------------------------------------------------------------------------

def _fallback_extract(text: str) -> ClaudeExtractedProfile:
    text_lower = text.lower()
    skills = [s for s in _FALLBACK_SKILLS if s.lower() in text_lower]

    years_matches = re.findall(r"(\d+)\+?\s*(?:years?|yrs?)", text, re.IGNORECASE)
    experience_years = max((int(m) for m in years_matches), default=0)

    education = ""
    for degree in ["PhD", "Ph.D", "Masters", "MSc", "M.Sc", "Bachelor", "BSc", "B.Sc", "MBA", "BE"]:
        if degree.lower() in text_lower:
            education = degree
            break

    return ClaudeExtractedProfile(
        skills=skills,
        experience_years=experience_years,
        education=education,
        job_titles=[],
        location="",
    )


# ---------------------------------------------------------------------------
# Profile strength
# ---------------------------------------------------------------------------

def _compute_strength(profile: ClaudeExtractedProfile) -> int:
    score = 10  # baseline
    score += min(len(profile.skills) * 4, 40)
    score += min(profile.experience_years * 5, 25)
    if profile.education:
        score += 15
    if profile.location:
        score += 5
    score += min(len(profile.job_titles) * 3, 10)
    return min(score, 100)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def parse_cv(file_bytes: bytes, content_type: str) -> dict:
    text = _extract_text(file_bytes, content_type)

    profile = await _call_claude(text) or _fallback_extract(text)

    return {
        "raw_text": text[:5_000],
        "skills": profile.skills[:20],
        "experience_years": profile.experience_years,
        "education": profile.education,
        "job_titles": profile.job_titles[:5],
        "location": profile.location,
        "profile_strength": _compute_strength(profile),
    }
