"""Discord bot entry point for the pr-writer agent.

Listens for GitHub issue URLs posted in the configured Discord channel.
When a message matching the pattern is detected, the bot:
  1. Fetches the issue details from the GitHub API.
  2. Runs the pr-writer LangGraph workflow.
  3. Posts the resulting PR URL back to Discord.

Expected message format (from a human or another bot):
    Any message containing a GitHub issue URL, e.g.:
    https://github.com/owner/repo/issues/42

Environment variables required:
    DISCORD_BOT_TOKEN          Discord bot token
    GITHUB_TOKEN               GitHub token with repo scope
    GITHUB_REPO                "owner/repo" target repository
    PR_WRITER_CHANNEL_NAME     Discord channel name to monitor
                               (default: "🤖-pr-writer")
"""
import sys
from pathlib import Path

# Add project root so shared.* imports resolve
sys.path.append(str(Path(__file__).parent.parent.parent))
# Add agent directory so nodes can do `from state import PrWriterState`
sys.path.append(str(Path(__file__).parent))

import asyncio
import os
import re

import discord
from discord.ext import commands
from dotenv import load_dotenv
from github import Github

from workflow import app  # compiled LangGraph app

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
TARGET_CHANNEL_NAME = os.getenv("PR_WRITER_CHANNEL_NAME", "🛠️-active-fix")

# Matches GitHub issue URLs: https://github.com/<owner>/<repo>/issues/<number>
_ISSUE_URL_RE = re.compile(
    r"https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)"
)


def _fetch_issue(issue_url_match: re.Match) -> dict:
    """Fetch issue metadata from GitHub API.

    Args:
        issue_url_match: Regex match object from _ISSUE_URL_RE.

    Returns:
        Dict with keys: issue_number, issue_title, issue_body.

    Raises:
        Exception: propagated from PyGithub on API errors.
    """
    owner = issue_url_match.group("owner")
    repo_name = issue_url_match.group("repo")
    number = int(issue_url_match.group("number"))

    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(f"{owner}/{repo_name}")
    issue = repo.get_issue(number)

    return {
        "issue_number": number,
        "issue_title": issue.title,
        "issue_body": issue.body or "",
    }


class PrWriterBot(commands.Bot):
    """Discord bot that triggers the pr-writer LangGraph workflow."""

    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        print(f"🤖 PR Writer Agent ready: {self.user.name}")
        print(f"   Monitoring channel: {TARGET_CHANNEL_NAME}")

    async def on_message(self, message: discord.Message):
        # Ignore own messages to prevent loops
        if message.author == self.user:
            return

        if message.channel.name != TARGET_CHANNEL_NAME:
            return

        match = _ISSUE_URL_RE.search(message.content)
        if not match:
            return

        await self._run_workflow(message, match)

    async def _run_workflow(self, message: discord.Message, match: re.Match):
        """Fetch the issue, invoke the LangGraph pipeline, and report the result."""
        issue_url = match.group(0)
        print(f"🚀 PR Writer workflow triggered for: {issue_url}")

        # Acknowledge receipt so the user knows processing has started
        status_msg = await message.channel.send(
            f"⏳ Processing issue: {issue_url}\nLocating relevant files and generating patch..."
        )

        try:
            issue_data = _fetch_issue(match)
        except Exception as exc:
            await status_msg.edit(content=f"❌ Failed to fetch issue: {exc}")
            return

        inputs = {
            "message_id": message.id,
            "channel_id": message.channel.id,
            "raw_log": issue_data["issue_body"],
            "logs": [],
            **issue_data,
        }

        # LangGraph invoke is synchronous — run in thread pool to avoid
        # blocking the Discord event loop (same pattern as issue-creator bot)
        loop = asyncio.get_event_loop()
        try:
            final_state = await loop.run_in_executor(
                None, lambda: app.invoke(inputs)
            )
        except Exception as exc:
            await status_msg.edit(content=f"❌ Workflow error: {exc}")
            return

        pr_url = final_state.get("pr_url", "")
        agent_logs = final_state.get("logs", [])

        if pr_url:
            await status_msg.edit(
                content=(
                    f"✅ Pull Request created!\n"
                    f"**Issue:** {issue_url}\n"
                    f"**PR:** {pr_url}"
                )
            )
        else:
            # Surface the last log line for debugging
            last_log = agent_logs[-1] if agent_logs else "No details available"
            await status_msg.edit(
                content=(
                    f"⚠️ Workflow completed but no PR was created.\n"
                    f"Last status: {last_log}"
                )
            )


if __name__ == "__main__":
    bot = PrWriterBot()
    bot.run(DISCORD_TOKEN)
