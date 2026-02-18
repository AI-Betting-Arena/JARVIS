from typing import Annotated, List
import operator
from typing_extensions import TypedDict


class BaseState(TypedDict):
    """Common fields shared across all agents."""
    message_id: int
    channel_id: int
    raw_log: str
    logs: Annotated[List[str], operator.add]
