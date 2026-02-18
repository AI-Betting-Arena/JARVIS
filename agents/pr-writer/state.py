"""State definition for the pr-writer agent."""
import operator
from typing import Annotated, Dict, List, Optional

from shared.base_state import BaseState


class PrWriterState(BaseState, total=False):
    """State for the pr-writer agent.

    Inherits common fields from BaseState and adds pr-writer-specific fields.
    Data flows forward through each node; no node mutates fields set by a
    previous node unless explicitly documented.

    Fields populated by IssueAnalyzerNode:
        issue_number:   GitHub issue number (int)
        issue_title:    Title of the GitHub issue
        issue_body:     Full body text of the GitHub issue
        keywords:       Broad search terms extracted from the issue
        symbols:        Specific function/class/interface names mentioned
        file_hints:     Partial file paths or directory names mentioned

    Fields populated by FileLocatorNode:
        located_files:  Absolute file paths ranked by hit frequency (most hits first)

    Fields populated by CodeReaderNode:
        file_contents:  Mapping of absolute file path → full source text

    Fields populated by PatchGeneratorNode:
        patch:          Unified diff string (--- a/... +++ b/... format)

    Fields populated by PRCreatorNode:
        pr_url:         URL of the created GitHub pull request
    """

    issue_number: int
    issue_title: str
    issue_body: str
    keywords: List[str]
    symbols: List[str]
    file_hints: List[str]
    located_files: List[str]
    file_contents: Dict[str, str]
    patch: str
    pr_url: str
