import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        raise RuntimeError("CRITICAL ERROR: SECRET_KEY NOT SET IN .ENV! Application cannot start without it.")
    # Используем Postgres на Railway/хостинге, если он доступен, иначе site.db (SQLite)
    _db_url = os.getenv('DATABASE_URL')
    if _db_url and _db_url.startswith('postgres://'):
        # SQLAlchemy 1.4+ жестко требует 'postgresql://'
        _db_url = _db_url.replace('postgres://', 'postgresql://', 1)
    
    SQLALCHEMY_DATABASE_URI = _db_url or ('sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'site.db'))
    SQLALCHEMY_TRACK_MODIFICATIONS = False


    
    # 💥 DOS Defense (16 MB limit max per request)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    # 🔑 Секретный ключ для дилеров (Option B)
    DEALER_TOKEN = os.getenv("DEALER_TOKEN", "TDV-CN-2026-SECRET")

    # 🍪 Cookie Security & CSRF Defense 
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_HTTPONLY = True
    # Автоматически включаем Secure, если работаем через HTTPS (на хостинге)
    SESSION_COOKIE_SECURE = os.getenv('SESSION_COOKIE_SECURE', 'False').lower() == 'true'

    # 🚦 Database lock timeout configuration (защита базы данных)
    # Параметр 'timeout' работает только в SQLite — для PostgreSQL он не нужен
    _db_uri = SQLALCHEMY_DATABASE_URI
    if _db_uri.startswith('sqlite'):
        SQLALCHEMY_ENGINE_OPTIONS = {
            'connect_args': {
                'timeout': 15
            }
        }
    else:
        SQLALCHEMY_ENGINE_OPTIONS = {}

    ADMIN_USER = os.getenv('ADMIN_USER')
    ADMIN_PASS = os.getenv('ADMIN_PASS')
    ADMIN_ENDPOINT = os.getenv('ADMIN_ENDPOINT', 'admin_portal_hidden')
    SENTRY_DSN = os.getenv('SENTRY_DSN')

    # ⏰ Scheduler Settings (для стабильного авто-обновления цен)
    SCHEDULER_API_ENABLED = True
    SCHEDULER_TIMEZONE = "Asia/Vladivostok" # Рекомендую для Благовещенска

CAT_TITLES = {
    'cars': 'Легковые автомобили',
    'cars_new': 'Новые легковые автомобили',
    'cars_used': 'Легковые с пробегом',
    'trucks': 'Коммерческий транспорт',
    'trucks_tractors': 'Тягачи',
    'trucks_dumpers': 'Самосвалы',
    'trucks_trucks': 'Грузовики',
    'trucks_vans': 'Фургоны',
    'trucks_km': 'Бортовые с КМУ',
    'trucks_evac': 'Эвакуаторы',
    'special': 'Вся спецтехника',
    'special_lifts': 'Автовышки',
    'special_frontal': 'Фронтальные погрузчики',
    'special_forklift': 'Вилочные погрузчики',
    'special_excavators': 'Экскаваторы-погрузчики'
}
