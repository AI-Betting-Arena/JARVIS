from shared.state import AgentState
import discord

async def discord_ui_node(state: AgentState, discord_client):
    alarm_channel = discord_client.get_channel(state['channel_id'])
    original_msg = await alarm_channel.fetch_message(state['message_id'])

    if state['is_backend_issue']:
        await original_msg.add_reaction('✅')
        
        # 2. 백엔드 전용 채널 찾기
        backend_channel = discord.utils.get(discord_client.get_all_channels(), name='💻-backend-discussion') # 채널명 확인
        
        # 3. 백엔드 채널에 메시지 쓰고 거기서 쓰레드 생성
        summary_msg = await backend_channel.send(f"🚨 **새로운 이슈 분석 시작**: Msg ID {state['message_id']}")
        thread = await summary_msg.create_thread(name=f"분석-{state['message_id']}")
        
        await thread.send(f"🤖 **Gemini 분석 결과**\n{state['analysis_report']}")
        return {"thread_id": thread.id}
    else:
        await original_msg.add_reaction('⏭️')
        return {}