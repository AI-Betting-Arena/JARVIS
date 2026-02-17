import os
import base64
import gzip
import json
import urllib.request

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

def lambda_handler(event, context):
    try:
        cw_data = event['awslogs']['data']
        compressed_payload = base64.b64decode(cw_data)
        uncompressed_payload = gzip.decompress(compressed_payload)
        payload = json.loads(uncompressed_payload)

        log_group = payload.get('logGroups', 'N/A')
        log_stream = payload.get('logStreams', 'N/A')

        for log_event in payload.get('logEvents', []):
            message = log_event.get('message', '')
            
            # 3. 디스코드 전송 데이터 구성
            discord_data = {
                "username": "AWS Monitor Agent",
                "embeds": [{
                    "title": "🚨 Backend Error Detected",
                    "color": 0xFF0000,
                    "fields": [
                        {"name": "Log Group", "value": f"`{log_group}`", "inline": True},
                        {"name": "Log Stream", "value": f"`{log_stream}`", "inline": True},
                        {"name": "Message", "value": f"```\n{message[:1000]}\n```"}
                    ],
                    "footer": {"text": "Analyzing with Gemini Agent soon..."}
                }]
            }

            # 4. HTTP POST 요청
            send_request(discord_data)

    except Exception as e:
        print(f"Error: {str(e)}")
        return {"statusCode": 500}

    return {"statusCode": 200}

def send_request(data):
    req = urllib.request.Request(
        DISCORD_WEBHOOK_URL,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as response:
        pass