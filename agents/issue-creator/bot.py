import sys
from pathlib import Path

# Add project root so shared.* imports resolve
sys.path.append(str(Path(__file__).parent.parent.parent))
# Add agent directory so nodes can do `from state import IssueCreatorState`
sys.path.append(str(Path(__file__).parent))

import discord
from discord.ext import commands
import os
import asyncio
from workflow import app  # LangGraph 컴파일본

# 환경 변수 로드
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_NAME = "🚨-incident-alarm"


class AgentBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        print(f"🤖 Issue Creator Agent 기동 완료: {self.user.name}")
        await self.process_missed_alarms()

    def _extract_log_from_embed(self, message):
        """Embed의 'Message' 필드에서 로그 텍스트 추출, 없으면 message.content로 폴백"""
        if message.embeds:
            embed = message.embeds[0]
            for field in embed.fields:
                if field.name == "Message":
                    return field.value
        return message.content

    async def _bot_already_reacted(self, message):
        """이 봇이 ✅ 또는 ⏭️ 반응을 이미 달았는지 확인"""
        for reaction in message.reactions:
            if reaction.emoji in ('✅', '⏭️'):
                async for user in reaction.users():
                    if user == self.user:
                        return True
        return False

    async def process_missed_alarms(self):
        """봇이 꺼져있을 때 올라온 미처리 알림 소급 처리"""
        channel = discord.utils.get(self.get_all_channels(), name=TARGET_CHANNEL_NAME)
        if not channel:
            return

        print("🔍 미처리 알림 스캔 중...")
        async for message in channel.history(limit=50):
            if message.author.bot and not await self._bot_already_reacted(message):
                await self.run_agent_workflow(message)

    async def on_message(self, message):
        # 본인이 쏜 메시지에는 반응하지 않음 (무한 루프 방지)
        if message.author == self.user:
            return

        # 🚨-incident-alarm 채널에 다른 봇(Lambda)이 쏜 메시지 감시
        if message.channel.name == TARGET_CHANNEL_NAME and message.author.bot:
            await self.run_agent_workflow(message)

    async def run_agent_workflow(self, message):
        """LangGraph 실행 및 결과 반영"""
        print(f"🚀 워크플로우 실행 시작 (Msg ID: {message.id})")

        # 1. 초기 상태 설정
        raw_log = self._extract_log_from_embed(message)
        if not raw_log:
            print(f"⚠️ 로그 텍스트 없음, 스킵 (Msg ID: {message.id})")
            return

        inputs = {
            "message_id": message.id,
            "channel_id": message.channel.id,
            "raw_log": raw_log,
            "logs": []
        }

        # 2. LangGraph 실행 (비동기로 실행하기 위해 run_in_executor 사용 가능하지만 여기선 단순 호출)
        # LangChain의 invoke는 동기 함수이므로 루프를 유지하기 위해 래핑
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(None, lambda: app.invoke(inputs))

        from nodes.notify import discord_ui_node
        await discord_ui_node(final_state, self)


if __name__ == "__main__":
    bot = AgentBot()
    bot.run(DISCORD_TOKEN)
