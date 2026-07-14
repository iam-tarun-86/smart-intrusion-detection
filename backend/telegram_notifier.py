"""
telegram_notifier.py — Send alerts with photos to Telegram (non-blocking)
"""

import requests
import threading
from pathlib import Path
from typing import Optional


class TelegramNotifier:
    def __init__(self, bot_token: Optional[str], chat_id: Optional[str]):
        self.bot_token = bot_token or ""
        self.chat_id = chat_id or ""
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}" if self.bot_token else ""
        self._recent_alerts = set()  # Prevent spam
    
    def _send_async(self, message: str, photo_path: Optional[str] = None):
        """Send in background thread so camera doesn't freeze."""
        try:
            if photo_path and Path(photo_path).exists():
                with open(photo_path, "rb") as photo:
                    url = f"{self.base_url}/sendPhoto"
                    files = {"photo": photo}
                    data = {
                        "chat_id": self.chat_id,
                        "caption": message,
                        "parse_mode": "HTML"
                    }
                    response = requests.post(url, files=files, data=data, timeout=10)
            else:
                url = f"{self.base_url}/sendMessage"
                data = {
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML"
                }
                response = requests.post(url, data=data, timeout=10)
            
            if response.status_code == 200:
                print(f"[Telegram] Alert sent")
            else:
                print(f"[Telegram] Failed: {response.text}")
                
        except Exception as e:
            print(f"[Telegram] Error: {e}")

    def send_alert(self, message: str, photo_path: Optional[str] = None, dedup_key: Optional[str] = None) -> bool:
        """Queue alert to send in background — doesn't block camera."""
        if not self.bot_token:
            print("[Telegram] Notifier disabled (missing bot token)")
            return False
            
        # Deduplication key: fall back to first 50 chars of message if no dedup_key is provided
        key = dedup_key or message[:50]
        if key in self._recent_alerts:
            return False
        
        self._recent_alerts.add(key)
        # Clear after 60 seconds so same person can alert again later
        threading.Timer(60.0, lambda: self._recent_alerts.discard(key)).start()
        
        # Send in background thread
        thread = threading.Thread(
            target=self._send_async,
            args=(message, photo_path),
            daemon=True
        )
        thread.start()
        return True