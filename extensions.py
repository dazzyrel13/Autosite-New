from flask_sqlalchemy import SQLAlchemy
from flask_babel import Babel
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_apscheduler import APScheduler
from flask_compress import Compress
from flask_wtf.csrf import CSRFProtect
try:
    from flask_caching import Cache
except ImportError:
    # Заглушка, если библиотека не установлена
    class Cache:
        def __init__(self, **kwargs): pass
        def init_app(self, app, **kwargs): pass
        def cached(self, **kwargs):
            return lambda f: f

db = SQLAlchemy()
babel = Babel()
login_manager = LoginManager()
limiter = Limiter(key_func=get_remote_address)
scheduler = APScheduler()
compress = Compress()
csrf = CSRFProtect()
cache = Cache()
