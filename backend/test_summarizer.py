import os
import sys
from pathlib import Path

# Parse .env manually to avoid system env var pollution
project_root = Path(__file__).resolve().parent.parent
env_file = project_root / ".env"
env_vars = {}
if env_file.exists():
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip()

# Override system env vars with .env values
for key, value in env_vars.items():
    os.environ[key] = value

sys.path.insert(0, '.')

import asyncio
import json
import httpx

async def test():
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    model = os.environ.get("OPENAI_CHAT_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")
    
    print(f"API Key present: {bool(api_key)}")
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    
    system_prompt = "You are a news analyst. Output structured JSON."
    user_prompt = """以下是一组新闻报道，请分析并输出 JSON：
- 赣锋锂业一季度净利润大增143%
  公司实现营业收入91.96亿元...

要求：title, summary, category, sentiment, entities
请严格输出 JSON 格式。"""
    
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 400,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://localhost",
        "X-Title": "Agent Hot News",
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        print(f"Status: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        print(f"Body length: {len(resp.text)}")
        print(f"Body: {resp.text[:2000]}")
        
        if resp.text.strip():
            try:
                data = resp.json()
                print(f"JSON keys: {data.keys()}")
                if data.get("choices"):
                    content = data['choices'][0]['message']['content']
                    print(f"Content: {content[:500]}")
                    # Try parse JSON
                    if "```json" in content:
                        content = content.split("```json")[1].split("```")[0].strip()
                    elif "```" in content:
                        content = content.split("```")[1].split("```")[0].strip()
                    result = json.loads(content)
                    print(f"Parsed: {result}")
            except Exception as e:
                print(f"Parse error: {e}")

if __name__ == "__main__":
    asyncio.run(test())
