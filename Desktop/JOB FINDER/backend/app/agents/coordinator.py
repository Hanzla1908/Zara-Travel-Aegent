"""
WorkflowCoordinator — orchestrates the job-finding workflow.

When an Anthropic API key is configured, Claude drives the workflow via
tool calling and writes a 2-sentence natural-language summary.  When no key
is available the coordinator falls back to a fixed sequential execution path
so the feature works without a key (minus the prose summary).

Security constraints enforced here:
  - search_external_jobs is a no-op unless confirmed=True is set in the
    request; this is the single gate before any external API call.
  - Scoring is always deterministic Python (MatchingAgent wraps rank_jobs).
  - Raw CV text is never logged, never passed to Claude.
  - Claude prompt strings are fully template-controlled; user-supplied
    keyword/location are injected only into structured fields, not the
    system prompt.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import MatchSummary, WorkflowPreferences, WorkflowResult
from app.agents.cv_agent import CVAnalysisAgent
from app.agents.matching_agent import MatchingAgent
from app.agents.search_agent import SearchAgent
from app.models.job import Job
from app.services.matcher import MatchWeights

logger = logging.getLogger(__name__)

_MAX_CLAUDE_ITERATIONS = 8
_CLAUDE_CALL_TIMEOUT   = 30  # seconds per Claude API call


# ---------------------------------------------------------------------------
# Claude tool definitions (what Claude sees)
# ---------------------------------------------------------------------------

_TOOLS: list[dict] = [
    {
        "name": "get_cv_profile",
        "description": (
            "Fetch the user's parsed CV profile: skills, experience years, "
            "past job titles, and location.  Always call this first."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"}
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "list_available_sources",
        "description": "Return which job-source adapters are configured and ready to use.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "load_db_jobs",
        "description": (
            "Load cached/seeded jobs from the local database.  "
            "Always call this — it has no external dependency."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":  {"type": "string"},
                "location": {"type": "string"},
                "limit":    {"type": "integer", "default": 50},
            },
            "required": [],
        },
    },
    {
        "name": "search_external_jobs",
        "description": (
            "Search external job sources (LinkedIn, Rozee.pk) via configured adapters.  "
            "ONLY call this when confirmed=true was set in the original request.  "
            "Returns raw job listings from external APIs."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "keyword":  {"type": "string"},
                "location": {"type": "string"},
                "sources":  {"type": "array", "items": {"type": "string"}},
                "limit":    {"type": "integer", "default": 20},
            },
            "required": [],
        },
    },
    {
        "name": "match_and_rank",
        "description": (
            "Score and rank all gathered jobs against the CV profile using "
            "deterministic weights.  Call this after load_db_jobs (and optionally "
            "search_external_jobs) have run."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "explain":            {"type": "boolean", "default": False},
                "skills_weight":      {"type": "number",  "default": 0.50},
                "experience_weight":  {"type": "number",  "default": 0.25},
                "title_weight":       {"type": "number",  "default": 0.15},
                "location_weight":    {"type": "number",  "default": 0.10},
            },
            "required": [],
        },
    },
]

_SYSTEM_PROMPT = """
You are a job-finding workflow coordinator. Your job is to:

1. Call get_cv_profile to understand the candidate.
2. Call list_available_sources to see which adapters are ready.
3. Call load_db_jobs to load cached/seeded jobs (always do this).
4. If the user confirmed external search, call search_external_jobs.
5. Call match_and_rank to score jobs against the CV.
6. Write a 2-sentence plain-text summary of the top results.

Rules:
- Never invent job listings or candidate details.
- Only call search_external_jobs when the request says confirmed=true.
- Keep the final summary under 60 words, plain prose, no bullet points.
""".strip()


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class WorkflowCoordinator:

    def __init__(self) -> None:
        self._cv_agent     = CVAnalysisAgent()
        self._search_agent = SearchAgent()
        self._match_agent  = MatchingAgent()

    async def run(
        self,
        preferences: WorkflowPreferences,
        db:          AsyncSession,
    ) -> WorkflowResult:
        """Execute the full workflow and return a validated result."""
        from app.config import settings

        state: dict[str, Any] = {
            "preferences": preferences,
            "db":          db,
            "cv":          None,
            "jobs":        [],
            "matches":     [],
            "fetched":     {},
            "errors":      {},
            "confirmed":   preferences.confirmed,
        }

        if settings.anthropic_api_key:
            try:
                return await self._claude_run(state, settings.anthropic_api_key)
            except Exception as exc:
                logger.warning("Claude coordinator failed (%s); using direct path.", exc)

        return await self._direct_run(state)

    # ------------------------------------------------------------------
    # Claude agentic loop
    # ------------------------------------------------------------------

    async def _claude_run(self, state: dict, api_key: str) -> WorkflowResult:
        import httpx
        import anthropic

        prefs      = state["preferences"]
        http_client = httpx.AsyncClient(headers={"accept-encoding": "identity"})
        client     = anthropic.AsyncAnthropic(api_key=api_key, http_client=http_client)

        messages: list[dict] = [
            {"role": "user", "content": self._initial_prompt(prefs)}
        ]
        summary = ""

        for _ in range(_MAX_CLAUDE_ITERATIONS):
            response = await asyncio.wait_for(
                client.messages.create(
                    model="claude-haiku-5-5",
                    max_tokens=1024,
                    system=_SYSTEM_PROMPT,
                    tools=_TOOLS,
                    messages=messages,
                ),
                timeout=_CLAUDE_CALL_TIMEOUT,
            )

            if response.stop_reason == "end_turn":
                summary = " ".join(
                    b.text for b in response.content if hasattr(b, "text")
                ).strip()
                break

            if response.stop_reason != "tool_use":
                break

            tool_results: list[dict] = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                result = await self._execute_tool(block.name, block.input, state)
                tool_results.append(
                    {
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     json.dumps(result, default=str),
                    }
                )

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user",      "content": tool_results})

        return self._build_result(state, summary)

    # ------------------------------------------------------------------
    # Direct sequential fallback (no Claude)
    # ------------------------------------------------------------------

    async def _direct_run(self, state: dict) -> WorkflowResult:
        prefs = state["preferences"]
        db    = state["db"]

        state["cv"] = await self._cv_agent.run(prefs.user_id, db)

        db_jobs = await self._load_db_jobs(db, prefs.keyword, prefs.location, limit=50)
        state["jobs"] = db_jobs

        if prefs.confirmed:
            search = await self._run_search(state)
            state["jobs"] = self._deduplicate(state["jobs"] + search.get("jobs", []))
            state["fetched"].update(search.get("fetched", {}))
            state["errors"].update(search.get("errors", {}))
        else:
            state["jobs"] = self._deduplicate(state["jobs"])

        if state["cv"] and state["jobs"]:
            state["matches"] = await self._run_match(state, prefs.explain)

        return self._build_result(state, "")

    # ------------------------------------------------------------------
    # Tool dispatcher
    # ------------------------------------------------------------------

    async def _execute_tool(
        self, name: str, args: dict, state: dict
    ) -> dict:
        prefs: WorkflowPreferences = state["preferences"]
        db:    AsyncSession         = state["db"]

        if name == "get_cv_profile":
            cv = await self._cv_agent.run(
                args.get("user_id", prefs.user_id), db
            )
            state["cv"] = cv
            if cv is None:
                return {"found": False, "message": "No CV uploaded yet."}
            return {"found": True, **cv}

        if name == "list_available_sources":
            from app.adapters.registry import _ADAPTERS
            return {
                a.source_id: {
                    "label":      a.source_label,
                    "configured": a.is_configured,
                }
                for a in _ADAPTERS
            }

        if name == "load_db_jobs":
            jobs = await self._load_db_jobs(
                db,
                keyword=args.get("keyword",  prefs.keyword),
                location=args.get("location", prefs.location),
                limit=int(args.get("limit", 50)),
            )
            state["jobs"] = self._deduplicate(state["jobs"] + jobs)
            return {"loaded": len(jobs), "total_in_state": len(state["jobs"])}

        if name == "search_external_jobs":
            if not state["confirmed"]:
                return {
                    "error": (
                        "User confirmation required before calling external APIs.  "
                        "The request must be re-sent with confirmed=true."
                    )
                }
            result = await self._run_search(state, args)
            new_jobs = result.get("jobs", [])
            state["jobs"] = self._deduplicate(state["jobs"] + new_jobs)
            state["fetched"].update(result.get("fetched", {}))
            state["errors"].update(result.get("errors", {}))
            return {
                "fetched":       result.get("fetched", {}),
                "new_jobs_added": len(new_jobs),
                "errors":        result.get("errors", {}),
            }

        if name == "match_and_rank":
            if not state["cv"]:
                return {"error": "No CV profile — call get_cv_profile first."}
            if not state["jobs"]:
                return {"error": "No jobs to match — load jobs first."}
            state["matches"] = await self._run_match(
                state,
                explain=bool(args.get("explain", False)),
                weight_args=args,
            )
            top = state["matches"][0]["score"] if state["matches"] else 0
            return {"ranked": len(state["matches"]), "top_score": top}

        return {"error": f"Unknown tool: {name}"}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _run_search(
        self, state: dict, args: dict | None = None
    ) -> dict:
        prefs = state["preferences"]
        args  = args or {}

        async def _attempt() -> dict:
            return await self._search_agent.run(
                keyword=args.get("keyword",  prefs.keyword),
                location=args.get("location", prefs.location),
                sources=args.get("sources") or (prefs.sources or None),
                experience=prefs.experience or None,
                job_type=prefs.job_type,
                limit=int(args.get("limit", prefs.limit)),
            )

        try:
            return await asyncio.wait_for(_attempt(), timeout=25)
        except asyncio.TimeoutError:
            return {"jobs": [], "fetched": {}, "errors": {"all": "Search timed out"}}
        except Exception as exc:
            return {"jobs": [], "fetched": {}, "errors": {"all": str(exc)}}

    async def _load_db_jobs(
        self,
        db:       AsyncSession,
        keyword:  str = "",
        location: str = "",
        limit:    int = 50,
    ) -> list[dict]:
        stmt = select(Job)
        if keyword:
            kw = f"%{keyword}%"
            stmt = stmt.where(
                or_(Job.title.ilike(kw), Job.description.ilike(kw), Job.company.ilike(kw))
            )
        if location:
            loc = f"%{location}%"
            stmt = stmt.where(
                or_(Job.location.ilike(loc), Job.location_type.ilike(loc))
            )
        stmt = stmt.limit(limit)
        rows = (await db.execute(stmt)).scalars().all()
        return [
            {c.name: getattr(j, c.name) for c in j.__table__.columns}
            for j in rows
        ]

    async def _run_match(
        self,
        state:       dict,
        explain:     bool        = False,
        weight_args: dict | None = None,
    ) -> list[dict]:
        prefs = state["preferences"]
        wa    = weight_args or {}
        sw = float(wa.get("skills_weight",     0.50))
        ew = float(wa.get("experience_weight", 0.25))
        tw = float(wa.get("title_weight",      0.15))
        lw = float(wa.get("location_weight",   0.10))
        total = sw + ew + tw + lw or 1.0
        weights = MatchWeights(
            skills=    round(sw / total, 6),
            experience=round(ew / total, 6),
            title=     round(tw / total, 6),
            location=  round(lw / total, 6),
        )
        all_results = await self._match_agent.run(
            state["cv"], state["jobs"], weights, explain=explain
        )
        return all_results[: prefs.limit]

    @staticmethod
    def _deduplicate(jobs: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out:  list[dict] = []
        for j in jobs:
            key = j.get("external_id") or f"id:{j.get('id', id(j))}"
            if key not in seen:
                seen.add(key)
                out.append(j)
        return out

    @staticmethod
    def _initial_prompt(prefs: WorkflowPreferences) -> str:
        lines = ["Run the job-finding workflow for this user."]
        if prefs.keyword:
            lines.append(f"Keyword: {prefs.keyword}")
        if prefs.location:
            lines.append(f"Location: {prefs.location}")
        if prefs.experience:
            lines.append(f"Experience levels: {', '.join(prefs.experience)}")
        if prefs.job_type:
            lines.append(f"Job type: {prefs.job_type}")
        if prefs.sources:
            lines.append(f"Sources: {', '.join(prefs.sources)}")
        lines.append(f"User ID: {prefs.user_id}")
        lines.append(f"External search confirmed: {prefs.confirmed}")
        lines.append(
            "Steps: (1) get_cv_profile, (2) list_available_sources, "
            "(3) load_db_jobs, (4) search_external_jobs if confirmed, "
            "(5) match_and_rank.  Then write a brief summary."
        )
        return "\n".join(lines)

    def _build_result(self, state: dict, summary: str) -> WorkflowResult:
        prefs = state["preferences"]
        raw_matches = state["matches"]

        match_summaries: list[MatchSummary] = []
        for m in raw_matches:
            try:
                match_summaries.append(MatchSummary(**m))
            except Exception:
                pass  # skip malformed entries

        return WorkflowResult(
            status="complete" if prefs.confirmed else "pending_confirmation",
            matches=match_summaries,
            sources_fetched=state["fetched"],
            total_jobs_searched=len(state["jobs"]),
            errors=state["errors"],
            plan="" if prefs.confirmed else self._describe_plan(prefs),
            cv_found=state["cv"] is not None,
            summary=summary,
        )

    @staticmethod
    def _describe_plan(prefs: WorkflowPreferences) -> str:
        sources = ", ".join(prefs.sources) if prefs.sources else "all configured sources"
        kw      = f' for "{prefs.keyword}"' if prefs.keyword else ""
        loc     = f" in {prefs.location}"   if prefs.location else ""
        return (
            f"Ready to search {sources}{kw}{loc}.  "
            "Confirm to proceed — this will call external job APIs."
        )
