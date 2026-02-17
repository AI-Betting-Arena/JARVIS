import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from shared.state import AgentState
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from nodes.categorize import categorize_node
from nodes.analyze import analyze_node
from nodes.github import github_issue_node
from nodes.discord_ui import discord_ui_node

load_dotenv()
model = ChatGoogleGenerativeAI(model="models/gemini-2.0-flash")

workflow = StateGraph(AgentState)

workflow.add_node("categorize", lambda x: categorize_node(x, model))
workflow.add_node("analyze", lambda x: analyze_node(x, model))
workflow.add_node("github_issue", github_issue_node)

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
