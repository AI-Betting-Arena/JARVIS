"""PRCreatorNode — applies the patch and opens a GitHub Pull Request.

Responsibility (SRP): take the generated unified diff, apply it to a new
branch in the target repository via the GitHub API, and open a PR against
the default branch.

Strategy for applying the patch without a local checkout:
- Parse the diff to identify changed files and their new content.
- For each changed file: fetch the current blob SHA via the GitHub API,
  then create/update the file on the new branch.
- This avoids the need for git on the agent machine and works inside any
  cloud runtime.

Assumptions:
- GITHUB_TOKEN env var has `repo` scope (read + write + PR creation).
- GITHUB_REPO env var is "owner/repo" (same as issue-creator agent).
- The patch is a well-formed unified diff produced by PatchGeneratorNode.
- PR is opened against the repo's default branch.
"""
import base64
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from github import Github, GithubException

from state import PrWriterState

# ---------------------------------------------------------------------------
# Unified diff parser
# ---------------------------------------------------------------------------

_FILE_HEADER_RE = re.compile(r"^---\s+(?:a/)?(.+)$", re.MULTILINE)
_HUNK_HEADER_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", re.MULTILINE)


def _parse_diff_files(patch: str) -> List[str]:
    """Return relative file paths of all files touched by the diff."""
    paths = []
    for m in _FILE_HEADER_RE.finditer(patch):
        path = m.group(1).strip()
        if path != "/dev/null":
            paths.append(path)
    return list(dict.fromkeys(paths))  # deduplicate, preserve order


def _apply_patch_to_content(original: str, patch_block: str) -> str:
    """Apply a single-file unified diff hunk block to original source.

    This is a line-level patch applier. It handles standard unified diff
    hunk format. Does not support binary files or fuzzy matching.

    Args:
        original:    Current file content as a string.
        patch_block: The portion of the unified diff for this file only.

    Returns:
        The patched file content as a string.
    """
    lines = original.splitlines(keepends=True)
    output: List[str] = list(lines)
    offset = 0  # cumulative line offset from previous hunks

    for hunk in _HUNK_HEADER_RE.finditer(patch_block):
        orig_start = int(hunk.group(1)) - 1  # 0-indexed
        orig_count = int(hunk.group(2)) if hunk.group(2) is not None else 1

        # Extract hunk body (lines after the @@ header until next @@ or EOF)
        hunk_end = hunk.end()
        next_hunk = _HUNK_HEADER_RE.search(patch_block, hunk_end)
        body = patch_block[hunk_end: next_hunk.start() if next_hunk else len(patch_block)]

        new_lines: List[str] = []
        for line in body.splitlines(keepends=True):
            if line.startswith("+"):
                new_lines.append(line[1:])
            elif line.startswith("-"):
                pass  # remove this line
            else:
                # context line (space or \\ no newline at end)
                new_lines.append(line[1:] if line.startswith(" ") else line)

        insert_at = orig_start + offset
        output[insert_at: insert_at + orig_count] = new_lines
        offset += len(new_lines) - orig_count

    return "".join(output)


def _split_diff_by_file(patch: str) -> Dict[str, str]:
    """Split a multi-file unified diff into per-file blocks.

    Returns:
        Dict mapping relative file path → the diff text for that file.
    """
    file_blocks: Dict[str, str] = {}
    # Split on "--- " markers that start a new file section
    sections = re.split(r"(?=^--- )", patch, flags=re.MULTILINE)
    for section in sections:
        m = _FILE_HEADER_RE.match(section)
        if not m:
            continue
        path = m.group(1).strip()
        if path != "/dev/null":
            file_blocks[path] = section
    return file_blocks


# ---------------------------------------------------------------------------
# GitHub interaction helpers
# ---------------------------------------------------------------------------

def _get_file_sha_and_content(repo, path: str, branch: str) -> Tuple[Optional[str], str]:
    """Fetch a file's current blob SHA and decoded content from GitHub.

    Returns:
        (sha, content) — sha is None if the file does not exist yet.
    """
    try:
        contents = repo.get_contents(path, ref=branch)
        if isinstance(contents, list):
            # Path is a directory, not a file — should not happen in practice
            return None, ""
        decoded = base64.b64decode(contents.content).decode("utf-8", errors="ignore")
        return contents.sha, decoded
    except GithubException as exc:
        if exc.status == 404:
            return None, ""
        raise


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def pr_creator_node(state: PrWriterState) -> dict:
    """Apply the generated patch and open a GitHub Pull Request.

    Args:
        state: Current pipeline state. Reads patch, issue_number,
               issue_title, issue_body.

    Returns:
        Partial state dict with pr_url populated.
    """
    print("--- CREATING PULL REQUEST ---")

    patch: str = state.get("patch", "").strip()
    issue_number: int = state.get("issue_number", 0)
    issue_title: str = state.get("issue_title", "Fix from AI agent")

    if not patch:
        msg = "PRCreator skipped: patch is empty"
        print(f"[PRCreatorNode] {msg}")
        return {"logs": [msg]}

    token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPO")

    if not token or not repo_name:
        msg = f"PRCreator error: GitHub config missing TOKEN={'set' if token else 'missing'} REPO={repo_name}"
        print(f"[PRCreatorNode] {msg}")
        return {"logs": [msg]}

    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        default_branch = repo.default_branch

        # Create a unique feature branch
        branch_name = f"ai-fix/issue-{issue_number}-{int(time.time())}"
        source_sha = repo.get_branch(default_branch).commit.sha
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source_sha)
        print(f"[PRCreatorNode] Created branch: {branch_name}")

        # Apply each file change from the diff
        file_blocks = _split_diff_by_file(patch)
        for rel_path, block in file_blocks.items():
            sha, current_content = _get_file_sha_and_content(repo, rel_path, default_branch)
            patched_content = _apply_patch_to_content(current_content, block)

            if sha is None:
                # New file
                repo.create_file(
                    path=rel_path,
                    message=f"fix: apply AI-generated patch for issue #{issue_number}",
                    content=patched_content,
                    branch=branch_name,
                )
            else:
                repo.update_file(
                    path=rel_path,
                    message=f"fix: apply AI-generated patch for issue #{issue_number}",
                    content=patched_content,
                    sha=sha,
                    branch=branch_name,
                )
            print(f"[PRCreatorNode] Committed change to {rel_path}")

        # Open the pull request
        pr = repo.create_pull(
            title=f"[AI Fix] {issue_title}",
            body=(
                f"Resolves #{issue_number}\n\n"
                "## AI-Generated Patch\n\n"
                "This PR was automatically generated by the pr-writer agent.\n\n"
                "**Review carefully before merging.** The patch is AI-generated and "
                "should be validated by a human engineer.\n\n"
                f"```diff\n{patch}\n```"
            ),
            head=branch_name,
            base=default_branch,
        )

        print(f"[PRCreatorNode] PR created: {pr.html_url}")
        return {
            "pr_url": pr.html_url,
            "logs": [f"PR created: {pr.html_url}"],
        }

    except GithubException as exc:
        msg = f"GitHub API error {exc.status}: {exc.data.get('message', str(exc))}"
        print(f"[PRCreatorNode] {msg}")
        return {"logs": [msg]}
    except Exception as exc:
        msg = f"PRCreator unexpected error: {exc}"
        print(f"[PRCreatorNode] {msg}")
        return {"logs": [msg]}
