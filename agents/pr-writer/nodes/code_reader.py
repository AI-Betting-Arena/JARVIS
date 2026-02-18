"""CodeReaderNode — reads located source files and loads their full content.

Responsibility (SRP): given a list of file paths, read each file from disk
and populate file_contents in the state. No LLM, no chunking, no embeddings.
The full raw source is passed downstream so the patch generator has complete
context — not truncated snippets.

File size guard: files larger than MAX_FILE_BYTES are truncated with a clear
marker so the LLM is not overwhelmed by auto-generated or minified files.
"""
import os
from typing import Dict, List

from state import PrWriterState

# Files larger than this byte limit are truncated.
# 100 KB covers virtually all hand-written TypeScript source files.
MAX_FILE_BYTES: int = int(os.getenv("MAX_FILE_BYTES", str(100 * 1024)))

_TRUNCATION_MARKER = "\n\n... [TRUNCATED: file exceeds size limit] ...\n"


def code_reader_node(state: PrWriterState) -> dict:
    """Read the content of every file in located_files.

    Args:
        state: Current pipeline state. Reads located_files.

    Returns:
        Partial state dict with file_contents populated as
        {absolute_file_path: source_code_string}.
    """
    print("--- READING SOURCE FILES ---")

    located_files: List[str] = state.get("located_files", [])
    file_contents: Dict[str, str] = {}
    skipped: List[str] = []

    for path in located_files:
        if not os.path.isfile(path):
            skipped.append(path)
            continue

        try:
            with open(path, encoding="utf-8", errors="ignore") as fh:
                raw = fh.read(MAX_FILE_BYTES + 1)

            if len(raw) > MAX_FILE_BYTES:
                raw = raw[:MAX_FILE_BYTES] + _TRUNCATION_MARKER

            file_contents[path] = raw
        except OSError as exc:
            skipped.append(path)
            print(f"[CodeReaderNode] Could not read {path}: {exc}")

    if skipped:
        print(f"[CodeReaderNode] Skipped {len(skipped)} unreadable file(s): {skipped}")

    print(f"[CodeReaderNode] Loaded {len(file_contents)} file(s)")

    return {
        "file_contents": file_contents,
        "logs": [f"CodeReader loaded {len(file_contents)} file(s)"],
    }
