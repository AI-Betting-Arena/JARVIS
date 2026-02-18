"""IssueAnalyzerNode — extracts structured signals from a GitHub issue.

Responsibility (SRP): parse the raw issue text into keywords, symbol names,
and file path hints that downstream nodes can use for code navigation.
No file I/O, no LLM tool calls — only a single LLM invoke.
"""
import json
import re

from langchain_core.messages import HumanMessage

from state import PrWriterState

# Prompt instructs the LLM to return strict JSON so we can parse
# deterministically without fragile regex on prose output.
_PROMPT_TEMPLATE = """You are a code navigation assistant.
Given the GitHub issue below, extract structured information that will be used
to locate relevant source files in a TypeScript codebase.

Return ONLY a JSON object with these exact keys (no markdown fences, no prose):
{{
  "keywords": ["<broad search term>", ...],
  "symbols": ["<FunctionName>", "<ClassName>", "<interfaceName>", ...],
  "file_hints": ["<partial/path/or/filename>", ...]
}}

Rules:
- keywords: 3-8 lowercase words or short phrases useful for grep/ripgrep
- symbols: PascalCase or camelCase identifiers explicitly named in the issue
- file_hints: partial file paths or directory names mentioned in the issue
  (e.g. "auth/login.ts", "UserService", "prisma/schema.prisma")
- If a category has nothing, return an empty list []

GitHub Issue Title: {title}
GitHub Issue Body:
{body}
"""


def issue_analyzer_node(state: PrWriterState, model) -> dict:
    """Extract keywords, symbols, and file hints from the GitHub issue.

    Args:
        state: Current pipeline state. Reads issue_title and issue_body.
        model: LangChain chat model (injected by workflow.py).

    Returns:
        Partial state dict with keywords, symbols, and file_hints populated.
    """
    print("--- ANALYZING ISSUE ---")

    title = state.get("issue_title", "")
    body = state.get("issue_body", "")

    prompt = _PROMPT_TEMPLATE.format(title=title, body=body)
    response = model.invoke([HumanMessage(content=prompt)])

    raw = response.content.strip()

    # Strip accidental markdown code fences the LLM may still emit
    raw = re.sub(r"^```[a-z]*\n?", "", raw)
    raw = re.sub(r"\n?```$", "", raw)

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Graceful degradation: fall back to simple keyword split so the
        # pipeline can continue even if the LLM misbehaves.
        print(f"[IssueAnalyzerNode] Warning: could not parse LLM JSON, falling back. Raw: {raw[:200]}")
        words = re.findall(r"[a-zA-Z]{3,}", title + " " + body)
        parsed = {
            "keywords": list(dict.fromkeys(w.lower() for w in words[:8])),
            "symbols": [],
            "file_hints": [],
        }

    return {
        "keywords": parsed.get("keywords", []),
        "symbols": parsed.get("symbols", []),
        "file_hints": parsed.get("file_hints", []),
        "logs": [f"Issue analyzed: {len(parsed.get('keywords', []))} keywords, "
                 f"{len(parsed.get('symbols', []))} symbols, "
                 f"{len(parsed.get('file_hints', []))} file hints"],
    }
