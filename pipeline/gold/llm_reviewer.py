"""LLM-assisted validation of fuzzy name matches using a local LM Studio model.

Sends each review candidate to the local model and asks it to determine
whether two names refer to the same NFL player.  Results:
  YES       → auto-accept (promote to 'llm_accepted')
  NO        → auto-reject (method = 'llm_rejected')
  UNCERTAIN → leave in 'fuzzy_review' for human eyes
"""

from __future__ import annotations

import json
import re
import time
from typing import Literal

import httpx
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn

console = Console()

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"
DEFAULT_MODEL  = "google/gemma-4-26b-a4b"

SYSTEM_PROMPT = """\
You are an expert on NFL players. Your task is to determine whether two player \
names refer to the same real person.

Rules:
- Common nicknames count as the same person (e.g. "Matt" = "Matthew", "Gabe" = "Gabriel", \
"Frank" = "Franklin").
- Jr./Sr./II suffixes that distinguish a father from his son are DIFFERENT people.
- If you are not confident, answer UNCERTAIN.

Think through your reasoning, then end your response with EXACTLY these two lines:
VERDICT: YES
REASON: <one sentence explaining why>

(Replace YES with NO or UNCERTAIN as appropriate.)
"""


Verdict = Literal["YES", "NO", "UNCERTAIN"]


def _parse_response(text: str) -> tuple[Verdict, str]:
    """Extract VERDICT and REASON from model output.

    Handles chain-of-thought models that wrap reasoning in <|channel>thought
    blocks before giving the final answer.
    """
    verdict: Verdict = "UNCERTAIN"
    reason = ""

    # Strip thinking blocks — use simple string split (more reliable than regex
    # when model uses special chars like | in tag names).
    # Gemma format:  <|channel>thought ... <channel|>  then final answer
    # Others:        <think> ... </think>  then final answer
    if '<channel|>' in text:
        # Take everything after the last closing tag
        clean = text.rsplit('<channel|>', 1)[-1]
    elif '</think>' in text:
        clean = text.rsplit('</think>', 1)[-1]
    else:
        clean = text

    # Search the cleaned text first; fall back to full text if nothing found
    search_in = clean.strip() or text

    # Find last VERDICT occurrence (post-reasoning answer is what we want)
    all_verdicts = re.findall(r'VERDICT\s*[:\-]\s*(YES|NO|UNCERTAIN)', search_in, re.IGNORECASE)
    if all_verdicts:
        verdict = all_verdicts[-1].upper()  # type: ignore[assignment]
    else:
        # Fallback: scan full text for verdict
        all_verdicts = re.findall(r'VERDICT\s*[:\-]\s*(YES|NO|UNCERTAIN)', text, re.IGNORECASE)
        if all_verdicts:
            verdict = all_verdicts[-1].upper()  # type: ignore[assignment]

    all_reasons = re.findall(r'REASON\s*[:\-]\s*(.+)', search_in, re.IGNORECASE)
    if all_reasons:
        reason = all_reasons[-1].strip().rstrip('*').strip()
    elif all_verdicts:
        reason = f"Model verdict: {verdict}"

    return verdict, reason


def query_model(
    raw_name: str,
    suggested_name: str,
    source: str,
    model: str = DEFAULT_MODEL,
    timeout: int = 30,
) -> tuple[Verdict, str]:
    """Ask the local LLM whether two names are the same player."""
    user_msg = (
        f'Name A: "{raw_name}"\n'
        f'Name B: "{suggested_name}"\n'
        f'Source context: {source}\n\n'
        f'Are these the same NFL player?'
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_msg},
        ],
        "temperature": 0.0,
        "max_tokens": 500,
    }
    try:
        resp = httpx.post(LM_STUDIO_URL, json=payload, timeout=timeout)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _parse_response(content)
    except httpx.TimeoutException:
        return "UNCERTAIN", "Request timed out"
    except Exception as e:
        return "UNCERTAIN", f"Error: {e}"


def run_llm_review(
    con,
    model: str = DEFAULT_MODEL,
    dry_run: bool = False,
    batch_size: int = 5,
    source_filter: str | None = None,
) -> dict[str, int]:
    """Process all fuzzy_review rows through the LLM.

    Returns counts: {accepted, rejected, uncertain, errors}
    """
    source_clause = f"AND source LIKE '%{source_filter}%'" if source_filter else ""
    candidates = con.execute(f"""
        SELECT raw_name, source, resolved_gsis_id, canonical_name, confidence
        FROM name_resolution
        WHERE method = 'fuzzy_review'
        {source_clause}
        ORDER BY source, confidence DESC
    """).fetchall()

    if not candidates:
        console.print("  [green]No rows pending LLM review.[/green]")
        return {"accepted": 0, "rejected": 0, "uncertain": 0, "errors": 0}

    console.print(f"  Model: [bold]{model}[/bold]")
    console.print(f"  Candidates: {len(candidates):,}  |  dry_run={dry_run}")

    counts = {"accepted": 0, "rejected": 0, "uncertain": 0, "errors": 0}
    updates = []        # (method, raw_name, source, gsis_id, canonical_name)
    decisions = []      # full log for preview/dry-run inspection

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Reviewing...", total=len(candidates))

        for raw_name, source, gsis_id, canonical_name, confidence in candidates:
            verdict, reason = query_model(raw_name, canonical_name or "", source, model=model)

            if verdict == "YES":
                counts["accepted"] += 1
                updates.append(("llm_accepted", raw_name, source, gsis_id, canonical_name))
            elif verdict == "NO":
                counts["rejected"] += 1
                updates.append(("llm_rejected", raw_name, source, None, None))
            else:
                counts["uncertain"] += 1

            decisions.append((verdict, raw_name, canonical_name, source, round(confidence * 100, 1), reason))
            progress.advance(task)

    if not dry_run and updates:
        for method, raw_name, source, gsis_id, canonical_name in updates:
            if method == "llm_accepted":
                con.execute("""
                    UPDATE name_resolution
                    SET method = 'llm_accepted', resolved_gsis_id = ?, canonical_name = ?
                    WHERE raw_name = ? AND source = ?
                """, [gsis_id, canonical_name, raw_name, source])
            else:
                con.execute("""
                    UPDATE name_resolution
                    SET method = 'llm_rejected', resolved_gsis_id = NULL, canonical_name = NULL
                    WHERE raw_name = ? AND source = ?
                """, [raw_name, source])

    return counts, decisions
