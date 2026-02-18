from state import IssueCreatorState
import discord
import os


async def discord_ui_node(state: IssueCreatorState, discord_client):
    alarm_channel = discord_client.get_channel(state['channel_id'])
    original_msg = await alarm_channel.fetch_message(state['message_id'])

    if state['is_backend_issue']:
        await original_msg.add_reaction('✅')

        # 2. 백엔드 전용 채널 찾기
        backend_channel = discord_client.get_channel(int(os.getenv("BACKEND_EXPERT_CHANNEL_ID")))

        if backend_channel is None:
            print(f"❌ Error: Channel ID {os.getenv('BACKEND_EXPERT_CHANNEL_ID')}를 찾을 수 없습니다. 권한이나 ID를 확인하세요.")
            # 필요하다면 시스템 로그에 남기거나 에러 상태로 전이
            return {"error": "Channel not found"}

        try:
            summary_msg = await backend_channel.send(f"🚨 **새로운 이슈 분석 시작**: Msg ID {state['message_id']}")
            thread = await summary_msg.create_thread(name=f"분석-{state['message_id']}")

            report = state.get('analysis_report', '')
            full_message = f"🤖 **Gemini 분석 결과**\n{report}"

            # 디스코드 메시지 제한(2000자)에 맞춰 분할 전송
            MAX_LENGTH = 1900

            if len(full_message) <= MAX_LENGTH:
                await thread.send(full_message)
            else:
                # 메시지를 chunk 단위로 쪼갬
                chunks = [full_message[i:i + MAX_LENGTH] for i in range(0, len(full_message), MAX_LENGTH)]
                for i, chunk in enumerate(chunks):
                    await thread.send(f"(Part {i+1}/{len(chunks)})\n{chunk}")
            return {"thread_id": thread.id}
        except Exception as e:
            print(f"❌ Discord 메시지 전송 또는 쓰레드 생성 실패: {str(e)}")
    else:
        await original_msg.add_reaction('⏭️')
        return {}
