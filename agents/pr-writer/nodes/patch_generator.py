"""PatchGeneratorNode — generates a unified diff patch using the LLM.

Responsibility (SRP): given the GitHub issue description and full source
file contents, ask the LLM to produce a minimal unified diff that resolves
the issue. The node does NOT apply the patch — that is PRCreatorNode's job.

Assumptions:
- file_contents contains complete source (no chunked excerpts).
- The LLM is instructed to output ONLY the diff, no prose, so the output
  can be passed directly to the GitHub API without post-processing.
- If the LLM produces extra prose, we extract the first diff block found.
"""
import re

from langchain_core.messages import HumanMessage

from state import PrWriterState

_PROMPT_TEMPLATE = """You are an expert TypeScript backend engineer.
Your task is to produce a minimal, correct unified diff that resolves the
GitHub issue described below.

Rules:
- Output ONLY a unified diff (--- / +++ / @@ lines). No explanations.
- Use paths relative to the project root (e.g. src/user/user.service.ts).
- Make the smallest change that fixes the issue — do not refactor unrelated code.
- If multiple files need to change, include all of them in the same diff.
- Follow the existing code style (spacing, naming, import order) exactly.

GitHub Issue:
Title: {title}
Body:
{body}

Relevant source files:
{files_block}

Unified diff:
"""

_DIFF_RE = re.compile(r"(---\s.+\n\+\+\+\s.+\n(?:@@.+@@.*\n(?:[+\- @\\].*\n?)*)+)", re.MULTILINE)


def _format_files_block(file_contents: dict) -> str:
    """Format file_contents into a readable block for the prompt."""
    parts = []
    for path, source in file_contents.items():
        parts.append(f"### File: {path}\n```typescript\n{source}\n```")
    return "\n\n".join(parts)


def patch_generator_node(state: PrWriterState, model) -> dict:
    """Generate a unified diff patch for the GitHub issue.

    Args:
        state: Current pipeline state. Reads issue_title, issue_body,
               file_contents.
        model: LangChain chat model (injected by workflow.py).

    Returns:
        Partial state dict with patch populated as a unified diff string.
    """
    print("--- GENERATING PATCH ---")

    title = state.get("issue_title", "")
    body = state.get("issue_body", "")
    file_contents = state.get("file_contents", {})

    if not file_contents:
        print("[PatchGeneratorNode] Warning: no file contents available, patch will be empty")
        return {
            "patch": "",
            "logs": ["PatchGenerator skipped: no file contents"],
        }

    files_block = _format_files_block(file_contents)
    prompt = _PROMPT_TEMPLATE.format(title=title, body=body, files_block=files_block)

    response = model.invoke([HumanMessage(content=prompt)])
    raw = response.content.strip()

    # Extract just the diff block if the LLM added surrounding prose
    match = _DIFF_RE.search(raw)
    patch = match.group(0).strip() if match else raw

    print(f"[PatchGeneratorNode] Patch generated ({len(patch)} chars)")

    return {
        "patch": patch,
        "logs": [f"Patch generated ({len(patch)} chars)"],
    }
