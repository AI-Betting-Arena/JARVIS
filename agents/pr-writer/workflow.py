"""LangGraph workflow definition for the pr-writer agent.

Graph topology (linear — no conditional branches needed for v1):

    START
      ↓
    issue_analyzer   — extract keywords/symbols/file hints from issue text
      ↓
    file_locator     — ripgrep + symbol index → ranked file list
      ↓
    code_reader      — read file contents from disk
      ↓
    patch_generator  — LLM produces unified diff
      ↓
    pr_creator       — apply diff, open GitHub PR
      ↓
    END
"""
import sys
from pathlib import Path

# Add project root so shared.* imports resolve
sys.path.append(str(Path(__file__).parent.parent.parent))
# Add agent directory so nodes can do `from state import PrWriterState`
sys.path.append(str(Path(__file__).parent))

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

from nodes.code_reader import code_reader_node
from nodes.file_locator import file_locator_node
from nodes.issue_analyzer import issue_analyzer_node
from nodes.patch_generator import patch_generator_node
from nodes.pr_creator import pr_creator_node
from shared.llm_factory import create_llm
from state import PrWriterState

load_dotenv()
model = create_llm()

workflow = StateGraph(PrWriterState)

workflow.add_node("issue_analyzer", lambda x: issue_analyzer_node(x, model))
workflow.add_node("file_locator", file_locator_node)
workflow.add_node("code_reader", code_reader_node)
workflow.add_node("patch_generator", lambda x: patch_generator_node(x, model))
workflow.add_node("pr_creator", pr_creator_node)

workflow.add_edge(START, "issue_analyzer")
workflow.add_edge("issue_analyzer", "file_locator")
workflow.add_edge("file_locator", "code_reader")
workflow.add_edge("code_reader", "patch_generator")
workflow.add_edge("patch_generator", "pr_creator")
workflow.add_edge("pr_creator", END)

app = workflow.compile()
