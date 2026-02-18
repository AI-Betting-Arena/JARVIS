import sys
from pathlib import Path

# Add project root so shared.* imports resolve
sys.path.append(str(Path(__file__).parent.parent.parent))
# Add agent directory so nodes can do `from state import IssueCreatorState`
sys.path.append(str(Path(__file__).parent))

from state import IssueCreatorState
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from shared.llm_factory import create_llm
from nodes.categorize import categorize_node
from nodes.analyze import analyze_node
from nodes.github_issue import github_issue_node
from nodes.notify import discord_ui_node

load_dotenv()
model = create_llm()

workflow = StateGraph(IssueCreatorState)

workflow.add_node("categorize", lambda x: categorize_node(x, model))
workflow.add_node("analyze", lambda x: analyze_node(x, model))
workflow.add_node("github_issue", github_issue_node)

# WARNING: set_entry_point() is a legacy API. Current LangGraph docs recommend
# using add_edge(START, "categorize") instead. Do not fix in this PR.
workflow.set_entry_point("categorize")

workflow.add_conditional_edges(
    "categorize",
    lambda x: "continue" if x["is_backend_issue"] else "exit",
    {
        "continue": "analyze",
        "exit": END
    }
)
workflow.add_edge("analyze", "github_issue")
workflow.add_edge("github_issue", END)

#workflow.add_node("discord_ui", lambda x: discord_ui_node(x, bot))

app = workflow.compile()
