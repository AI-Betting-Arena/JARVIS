from state import IssueCreatorState
from langchain_core.messages import HumanMessage


def analyze_node(state: IssueCreatorState, model):
    if not state.get("is_backend_issue"):
        return state
    # TODO: 분석할 때 프롬프트 더 자세하게
    print("--- ANALYZING ERROR ---")
    prompt = f"""
    You are a backend expert. Analyze the following log and provide a detailed report including error summary, technical cause, and suggested fix (including code changes if applicable).

    log: {state['raw_log']}

    [Report should be in the following format]
    1. Error Summary:
    2. Technical Cause:
    3. Suggested Fix: (include code changes if applicable)
    """

    response = model.invoke([HumanMessage(content=prompt)])

    return {
        "analysis_report": response.content,
        "logs": ["Analysis completed by Gemini"]
    }
