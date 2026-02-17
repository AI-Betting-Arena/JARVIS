import discord
from discord.ext import commands
import os
import asyncio
from main import app  # 네가 만든 LangGraph 컴파일본

# 환경 변수 로드
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
TARGET_CHANNEL_NAME = "🚨-incident-alarm"

class AgentBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def on_ready(self):
        print(f"🤖 Backend Expert Agent 기동 완료: {self.user.name}")
        await self.process_missed_alarms()

    async def process_missed_alarms(self):
        """봇이 꺼져있을 때 올라온 미처리 알림 소급 처리"""
        channel = discord.utils.get(self.get_all_channels(), name=TARGET_CHANNEL_NAME)
        if not channel: return

        print("🔍 미처리 알림 스캔 중...")
        async for message in channel.history(limit=50):
            # TODO: AND가 이게 맞나?
            if message.author.bot and not any(r.emoji == '✅' for r in message.reactions):
                # ⏭️(스킵) 표시도 없는 경우에만 처리
                if not any(r.emoji == '⏭️' for r in message.reactions):
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
        inputs = {
            "message_id": message.id,
            "channel_id": message.channel.id,
            "raw_log": message.content,
            "logs": []
        }

        # 2. LangGraph 실행 (비동기로 실행하기 위해 run_in_executor 사용 가능하지만 여기선 단순 호출)
        # LangChain의 invoke는 동기 함수이므로 루프를 유지하기 위해 래핑
        loop = asyncio.get_event_loop()
        final_state = await loop.run_in_executor(None, lambda: app.invoke(inputs))

        from nodes.discord_ui import discord_ui_node
        await discord_ui_node(final_state, self)

if __name__ == "__main__":
    bot = AgentBot()
    bot.run(DISCORD_TOKEN)