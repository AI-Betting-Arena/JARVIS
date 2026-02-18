import gzip, json, base64, os, urllib.request

def parse_log_status(msg):
    """메시지 내용에 따라 상태, 색상, 이모지를 결정하는 순수 함수"""
    # 1. 실패 우선 판별
    if any(k in msg for k in ['❌', 'Failed', 'Error', 'Exception']):
        return "🔴 배치 작업 실패/오류", 0xFF0000, "🚨", True
    
    # 2. 경고 판별
    if any(k in msg for k in ['⚠️', 'warn', 'Skipping']):
        return "🟡 배치 작업 경고 (Skip)", 0xFFAA00, "⚠️", True
    
    # 3. 성공 판별
    if any(k in msg for k in ['✅', 'successfully', 'finished']):
        return "🟢 배치 작업 성공", 0x00FF00, "✅", True
        
    # 알림이 필요 없는 일반 로그
    return None, None, None, False

def lambda_handler(event, context):
    WEBHOOK_URL = os.environ.get("BATCH_WEBHOOK")
    
    try:
        # CloudWatch 데이터 복호화
        data = event['awslogs']['data']
        payload = json.loads(gzip.decompress(base64.b64decode(data)))
        
        for log in payload.get('logEvents', []):
            msg = log.get('message', '')
            
            title, color, emoji, should_notify = parse_log_status(msg)
            
            if not should_notify:
                continue

            discord_data = {
                "username": "ABABE Batch Monitor",
                "embeds": [{
                    "title": f"{emoji} {title}",
                    "description": f"**로그 내용:**\n```\n{msg[:1800]}\n```", # 2000자 제한 방어
                    "color": color,
                    "footer": {"text": f"ABABE Operations | {payload.get('logGroup')}"}
                }]
            }

            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            req = urllib.request.Request(
                WEBHOOK_URL, 
                data=json.dumps(discord_data).encode('utf-8'),
                headers=headers
            )
            urllib.request.urlopen(req)
            
    except Exception as e:
        print(f"Critical Lambda Error: {e}")
        
    return {"statusCode": 200}