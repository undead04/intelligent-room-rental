import requests
import random
import time
from crawler.config.settings import USER_AGENTS, TIMEOUT

def get_random_headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    }

def fetch_with_retry(url, params=None, max_retries=3, backoff_factor=2):
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url, 
                params=params, 
                headers=get_random_headers(), 
                timeout=TIMEOUT
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code in (403, 429):
                print(f"[Cảnh báo] Bị chặn hoặc rate limit. Mã: {response.status_code}")
        except requests.RequestException as e:
            print(f"[Lỗi mạng] {e}")
        
        sleep_time = backoff_factor ** attempt
        print(f"Thử lại sau {sleep_time}s (Lần {attempt + 1}/{max_retries})...")
        time.sleep(sleep_time)
    
    return None
