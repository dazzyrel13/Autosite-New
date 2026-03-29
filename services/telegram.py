import requests
import os
import logging

logger = logging.getLogger(__name__)

def send_telegram_message(text):
    """
    Отправляет уведомление в Telegram.
    Нужны TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в .env файле.
    """
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID')

    if not token or not chat_id:
        logger.warning("Телеграм не настроен: нет токена или Chat ID")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML'
    }

    # На хостинге прокси обычно не нужен, но локально может пригодиться
    proxy_url = os.getenv('HTTPS_PROXY')
    proxies = {'https': proxy_url, 'http': proxy_url} if proxy_url else None

    try:
        response = requests.post(url, json=payload, proxies=proxies, timeout=15)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в Telegram: {e}")
        return False
