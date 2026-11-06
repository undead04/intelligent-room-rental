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
    """Gọi HTTP GET và trả về dữ liệu JSON nếu thành công (200)"""
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
                print(f"[Cảnh báo] Bị chặn hoặc rate limit. Mã: {response.status_code}", flush=True)
        except requests.RequestException as e:
            print(f"[Lỗi mạng] {e}", flush=True)
        
        sleep_time = backoff_factor ** attempt
        print(f"Thử lại sau {sleep_time}s (Lần {attempt + 1}/{max_retries})...", flush=True)
        time.sleep(sleep_time)
    
    return None

def fetch_with_status(url, params=None, max_retries=3, backoff_factor=2):
    """
    Gọi HTTP GET và trả về tuple (status_code, json_data)
    Dùng để phát hiện các mã 404 (tin bị xóa/hết hạn), 200 (còn sống), 403/429 (rate limit).
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(
                url, 
                params=params, 
                headers=get_random_headers(), 
                timeout=TIMEOUT
            )
            if response.status_code == 200:
                try:
                    return 200, response.json()
                except Exception:
                    return 200, None
            elif response.status_code == 404:
                return 404, None
            elif response.status_code in (403, 429):
                print(f"[Cảnh báo] Bị chặn hoặc rate limit. Mã: {response.status_code}", flush=True)
            else:
                return response.status_code, None
        except requests.RequestException as e:
            print(f"[Lỗi mạng] {e}", flush=True)
        
        sleep_time = backoff_factor ** attempt
        time.sleep(sleep_time)
        
    return None, None
