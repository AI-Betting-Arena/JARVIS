"""FileLocatorNode — deterministic, structure-aware file locator.

Replaces CodeRAG entirely. No embeddings, no vector DB.

Two complementary strategies run on every invocation:

Strategy 1 — Keyword Search (ripgrep)
    For each symbol and keyword extracted by IssueAnalyzerNode, run:
        rg --json <term> <project_path>
    Parse JSON output and collect file paths + match counts.
    Requires: `rg` (ripgrep) installed — `brew install ripgrep`

Strategy 2 — Symbol Index
    A pre-built JSON file that maps exported TypeScript symbol names to the
    file(s) where they are defined:
        { "UserService": ["/abs/path/src/user/user.service.ts"], ... }
    The index is built lazily on first run and cached at SYMBOL_INDEX_PATH.
    Set env var REBUILD_SYMBOL_INDEX=1 to force a rebuild.

Results from both strategies are merged, deduplicated, and sorted by total
hit frequency (most matches first). The top MAX_FILES files are kept.
"""
import json
import os
import re
import subprocess
from collections import defaultdict
from typing import Dict, List

from state import PrWriterState

# ---------------------------------------------------------------------------
# Configuration (all overridable via environment variables)
# ---------------------------------------------------------------------------

# Absolute path to the TypeScript project to analyse.
# Assumption: the target codebase lives at ~/Desktop/aba/ababe as confirmed
# by the user. Override with env var PROJECT_PATH if needed.
PROJECT_PATH: str = os.getenv(
    "PROJECT_PATH",
    os.path.expanduser("~/Desktop/aba/ababe"),
)

# Where to persist the symbol index JSON file.
SYMBOL_INDEX_PATH: str = os.getenv(
    "SYMBOL_INDEX_PATH",
    os.path.join(os.path.dirname(__file__), "..", ".symbol_index.json"),
)

# Maximum number of files to surface to CodeReaderNode.
MAX_FILES: int = int(os.getenv("MAX_LOCATED_FILES", "5"))


# ---------------------------------------------------------------------------
# Symbol index builder
# ---------------------------------------------------------------------------

# Regex that matches TypeScript exported declarations at the top level.
# Captures: export (default)? (async)? function|class|interface|const|type <Name>
_EXPORT_RE = re.compile(
    r"\bexport\s+(?:default\s+)?(?:async\s+)?(?:function|class|interface|const|type|enum)\s+([A-Za-z_$][A-Za-z0-9_$]*)"
)


def build_symbol_index(project_path: str) -> Dict[str, List[str]]:
    """Walk project_path and build a {symbol_name: [file_path, ...]} map.

    Only inspects .ts files; skips generated/, node_modules/, dist/.

    Args:
        project_path: Absolute path to the TypeScript project root.

    Returns:
        Dict mapping each exported symbol name to a list of absolute file
        paths where it is defined (a symbol may appear in multiple files).
    """
    index: Dict[str, List[str]] = defaultdict(list)
    skip_dirs = {"node_modules", "dist", "generated", ".git", "coverage"}

    for root, dirs, files in os.walk(project_path):
        # Prune skipped directories in-place so os.walk doesn't descend
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        for fname in files:
            if not fname.endswith(".ts"):
                continue
            abs_path = os.path.join(root, fname)
            try:
                with open(abs_path, encoding="utf-8", errors="ignore") as fh:
                    for match in _EXPORT_RE.finditer(fh.read()):
                        symbol = match.group(1)
                        if abs_path not in index[symbol]:
                            index[symbol].append(abs_path)
            except OSError:
                # Silently skip unreadable files
                continue

    return dict(index)


def _load_or_build_index(project_path: str) -> Dict[str, List[str]]:
    """Return the cached symbol index, rebuilding it when necessary.

    Rebuild conditions:
    - The index file does not exist yet.
    - REBUILD_SYMBOL_INDEX env var is set to a non-empty value.
    """
    force_rebuild = bool(os.getenv("REBUILD_SYMBOL_INDEX", ""))
    index_path = os.path.normpath(SYMBOL_INDEX_PATH)

    if force_rebuild or not os.path.exists(index_path):
        print(f"[FileLocatorNode] Building symbol index for {project_path} ...")
        index = build_symbol_index(project_path)
        os.makedirs(os.path.dirname(index_path), exist_ok=True)
        with open(index_path, "w", encoding="utf-8") as fh:
            json.dump(index, fh, indent=2)
        print(f"[FileLocatorNode] Symbol index written to {index_path} ({len(index)} symbols)")
        return index

    with open(index_path, encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Strategy 1 — ripgrep keyword search
# ---------------------------------------------------------------------------

def _rg_search(term: str, project_path: str) -> Dict[str, int]:
    """Run ripgrep for a single term and return {file_path: match_count}.

    Uses --json output format for reliable machine-readable parsing.
    Silently returns an empty dict if rg is not installed or the project
    path does not exist (the symbol index strategy still runs).

    Args:
        term:         The keyword or symbol to search for.
        project_path: Root directory to search within.

    Returns:
        Mapping of absolute file path to number of matching lines found.
    """
    hits: Dict[str, int] = defaultdict(int)

    if not os.path.isdir(project_path):
        return hits

    try:
        result = subprocess.run(
            [
                "rg",
                "--json",
                "--type", "ts",          # only TypeScript files
                "--glob", "!node_modules",
                "--glob", "!dist",
                "--glob", "!generated",
                term,
                project_path,
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError:
        # rg not installed — degrade gracefully
        print("[FileLocatorNode] Warning: ripgrep (rg) not found. Install with: brew install ripgrep")
        return hits
    except subprocess.TimeoutExpired:
        print(f"[FileLocatorNode] Warning: rg timed out searching for '{term}'")
        return hits

    for line in result.stdout.splitlines():
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") == "match":
            path = obj["data"]["path"]["text"]
            hits[path] += 1

    return hits


# ---------------------------------------------------------------------------
# Strategy 2 — symbol index lookup
# ---------------------------------------------------------------------------

def _index_search(symbols: List[str], index: Dict[str, List[str]]) -> Dict[str, int]:
    """Look up symbol names in the pre-built index.

    Each file path that contains one of the symbols gets a score equal to
    the number of matching symbols it satisfies (not just 1 per file).

    Args:
        symbols: List of symbol names from IssueAnalyzerNode.
        index:   The loaded symbol index dict.

    Returns:
        Mapping of file path to number of matched symbols.
    """
    hits: Dict[str, int] = defaultdict(int)
    for sym in symbols:
        for path in index.get(sym, []):
            hits[path] += 1
    return hits


# ---------------------------------------------------------------------------
# Node entry point
# ---------------------------------------------------------------------------

def file_locator_node(state: PrWriterState) -> dict:
    """Locate relevant source files using ripgrep + symbol index.

    Args:
        state: Current pipeline state. Reads keywords, symbols, file_hints.

    Returns:
        Partial state dict with located_files populated (ranked list of
        absolute file paths, most relevant first).
    """
    print("--- LOCATING FILES ---")

    keywords: List[str] = state.get("keywords", [])
    symbols: List[str] = state.get("symbols", [])
    file_hints: List[str] = state.get("file_hints", [])
    project_path = PROJECT_PATH

    # Aggregate scores across all strategies: {file_path: total_score}
    scores: Dict[str, int] = defaultdict(int)

    # --- Strategy 1: ripgrep over keywords + symbols ---
    search_terms = list(dict.fromkeys(symbols + keywords))  # symbols first, then keywords
    for term in search_terms:
        for path, count in _rg_search(term, project_path).items():
            scores[path] += count

    # --- Strategy 2: symbol index ---
    if symbols:
        index = _load_or_build_index(project_path)
        for path, count in _index_search(symbols, index).items():
            # Weight symbol index hits more heavily (×2) because they are
            # exact definition matches, not just textual occurrences.
            scores[path] += count * 2

    # --- Bonus: file_hints substring matching against discovered paths ---
    # For any hint that resembles a path fragment, boost files whose path
    # contains that fragment.
    for hint in file_hints:
        hint_norm = hint.replace("\\", "/")
        for path in list(scores.keys()):
            if hint_norm in path.replace("\\", "/"):
                scores[path] += 1

    # Sort by score descending, cap at MAX_FILES
    ranked = sorted(scores.keys(), key=lambda p: scores[p], reverse=True)[:MAX_FILES]

    print(f"[FileLocatorNode] Located {len(ranked)} file(s): {[os.path.basename(p) for p in ranked]}")

    return {
        "located_files": ranked,
        "logs": [f"FileLocator found {len(ranked)} file(s) via ripgrep + symbol index"],
    }
