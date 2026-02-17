from github import Github
import os
from shared.state import AgentState

def github_issue_node(state: AgentState):
    """분석 결과를 바탕으로 GitHub 이슈 생성"""
    if not state.get("is_backend_issue") or not state.get("analysis_report"):
        return state

    print("--- 🐙 CREATING GITHUB ISSUE ---")
    
    # 환경변수에서 정보 로드
    token = os.getenv("GITHUB_TOKEN")
    repo_name = os.getenv("GITHUB_REPO") # e.g. "user/ababe-app"
    
    try:
        g = Github(token)
        repo = g.get_repo(repo_name)
        
        title = f"[🚨 Incident Report] Backend Error - Message ID {state['message_id']}"
        body = f"## 🤖 AI Agent Analysis Report\n\n{state['analysis_report']}"
        
        issue = repo.create_issue(title=title, body=body)
        
        return {
            "github_issue_url": issue.html_url,
            "logs": [f"GitHub issue created: {issue.html_url}"]
        }
    except Exception as e:
        error_msg = f"Failed to create GitHub issue: {str(e)}"
        print(error_msg)
        return {"logs": [error_msg]}