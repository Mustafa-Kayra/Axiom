#!/usr/bin/env python3
"""
Test Axiom API ile iletişim
"""
import httpx
import json
import time

def test_api():
    """API'ye istek gönder ve cevabı poll et"""
    
    # API endpoint ve headers
    api_url = "https://api.ayechat.ai/invoke_cli"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer aye_demo_abc123xyz"
    }
    
    # Request payload
    payload = {
        "chat_id": -1,
        "message": "merhaba dünya, sen kimsin?",
        "source_files": {},
        "model": "google/gemini-3-flash-preview",
        "system_prompt": "Sen bir yazılım geliştirme asistanısın.",
        "max_output_tokens": 4096,
        "streaming": True
    }
    
    print("=" * 60)
    print("🚀 AXIOM API TEST")
    print("=" * 60)
    print(f"\n📤 Request URL: {api_url}")
    print(f"📄 Payload:\n{json.dumps(payload, indent=2)}")
    print("\n[*] API'ye istek gönderiliyor...\n")
    
    try:
        # API'ye istek gönder
        resp = httpx.post(api_url, json=payload, headers=headers, timeout=30)
        print(f"✅ Response Status: {resp.status_code}")
        
        response_data = resp.json()
        print(f"📥 Response JSON:\n{json.dumps(response_data, indent=2)}")
        
        # S3 polling URL'ini al
        response_url = response_data.get("response_url")
        status = response_data.get("status")
        
        print(f"\n📍 Status: {status}")
        print(f"🔗 Polling URL:\n{response_url}")
        
        # Eğer enqueued ise, poll et
        if status == "enqueued" and response_url:
            print("\n[*] Cevap hazırlanıyor, polling başlanıyor...\n")
            
            for attempt in range(1, 6):
                time.sleep(2)
                print(f"⏳ Poll attempt {attempt}/5...")
                
                try:
                    poll_resp = httpx.get(response_url, timeout=30)
                    print(f"   Status: {poll_resp.status_code}")
                    
                    if poll_resp.status_code == 200:
                        result = poll_resp.json()
                        print(f"\n✅ SONUÇ HAZIR:\n{json.dumps(result, indent=2)}")
                        return result
                    else:
                        print(f"   Response: {poll_resp.text[:100]}...")
                        
                except Exception as e:
                    print(f"   Error: {e}")
        
        return response_data
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

if __name__ == "__main__":
    test_api()
