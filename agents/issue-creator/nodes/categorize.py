from langchain_core.messages import HumanMessage
from state import IssueCreatorState


def categorize_node(state: IssueCreatorState, model):
    """Check the log And Determine whether the issue is a backend issue or not"""
    prompt = f"Say YES or NO. Is the following log related to a backend issue?: {state['raw_log']}"

    response = model.invoke([HumanMessage(content=prompt)])
    is_backend = "YES" in response.content.upper()

    return {
        "is_backend_issue": is_backend,
        "logs": [f"Categorized: {is_backend}"]
    }
