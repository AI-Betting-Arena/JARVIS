# DEPRECATED: This module is superseded by shared/base_state.py and
# agents/issue-creator/state.py. Do not add new fields here.
# It is kept temporarily while agents/backend-expert/ is still in use.
# Remove once agents/backend-expert/ is fully decommissioned.
from typing import TypedDict, Optional, Annotated, List
import operator

class AgentState(TypedDict):
    message_id: int
    channel_id: int
    raw_log: str

    is_backend_issue: bool
    analysis_report: Optional[str]
    suggested_fix: Optional[str]

    thread_id: Optional[int]
    github_issue_url: Optional[str]

    logs: Annotated[List[str], operator.add]
