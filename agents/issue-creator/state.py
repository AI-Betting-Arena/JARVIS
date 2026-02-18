from typing import Optional
from shared.base_state import BaseState


class IssueCreatorState(BaseState, total=False):
    """State for the issue-creator agent.

    Inherits common fields from BaseState and adds issue-creator-specific fields.
    """
    is_backend_issue: bool
    analysis_report: Optional[str]
    suggested_fix: Optional[str]
    thread_id: Optional[int]
    github_issue_url: Optional[str]
