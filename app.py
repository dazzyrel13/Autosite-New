"""
Main Flask application factory.
"""

from flask import Flask, render_template, request
import os
import logging
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from extensions import db, babel, login_manager, limiter, scheduler, compress, csrf, cache
from config import Config, CAT_TITLES
from models import User

# Глобальный кэш для времен изменения файлов
_MTIME_CACHE = {}

def create_app(config_class=Config):
    app = Flask(__name__)

    app.config['APPLICATION_ROOT'] = '/'
    app.config['SESSION_COOKIE_PATH'] = '/'

    app.config.from_object(config_class)

    # 🛡️ Sentry Monitoring
    if app.config.get('SENTRY_DSN'):
        sentry_sdk.init(
            dsn=app.config['SENTRY_DSN'],
            integrations=[FlaskIntegration()],
            traces_sample_rate=0.1, # Reduced for production efficiency
            profiles_sample_rate=0.1,
        )
        app.logger.info("Sentry monitoring initialized.")
    app.config['COMPRESS_ALGORITHM'] = 'gzip'
    app.config['COMPRESS_MIN_SIZE'] = 500
    app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000 # 1 year cache

    # Инициализация расширений
    db.init_app(app)
    babel.init_app(app, default_locale='ru')
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    try:
        scheduler.init_app(app)
    except Exception:
        pass
    compress.init_app(app)
    csrf.init_app(app)

    # 🗄️ Кэширование (Авто-переключение: Redis для продакшена, SimpleCache для локалки)
    redis_url = os.environ.get("REDIS_URL")
    if redis_url and redis_url != "memory://":
        app.config['CACHE_TYPE'] = 'RedisCache'
        app.config['CACHE_REDIS_URL'] = redis_url
    else:
        app.config['CACHE_TYPE'] = 'SimpleCache'
        
    app.config['CACHE_DEFAULT_TIMEOUT'] = 300
    cache.init_app(app)

    # 🛡️ Защита от подмены IP за Proxy (Nginx, Cloudflare)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # 🚦 Реальная настройка ограничений (Rate Limiting)
    app.config['RATELIMIT_DEFAULT'] = "2000 per day; 200 per hour"
    app.config['RATELIMIT_STORAGE_URI'] = os.environ.get("REDIS_URL", "memory://")
    limiter.init_app(app)

    # 🔒 Строгие заголовки безопасности (Security Headers)
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        # Modern CSP: Allows self scripts/styles + trustworthy CDNs
        response.headers['Content-Security-Policy'] = "default-src 'self'; worker-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://unpkg.com https://cdnjs.cloudflare.com; font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; img-src 'self' data: https://ingest.de.sentry.io; connect-src 'self' https://ingest.de.sentry.io https://cdn.jsdelivr.net https://unpkg.com https://fonts.googleapis.com https://fonts.gstatic.com;"
        return response

    # 🧵 Пул потоков для легких фоновых задач (чтобы не плодить тысячи тредов)
    from concurrent.futures import ThreadPoolExecutor
    executor = ThreadPoolExecutor(max_workers=4)

    # 📊 Регистрация посещений (Трафик)
    @app.before_request
    def record_visit():
        # Исключаем статику, админку, поиск и favicon
        admin_endpoint = app.config.get('ADMIN_ENDPOINT', 'admin')
        if request.path.startswith('/static') or \
           request.path.startswith(f'/{admin_endpoint}') or \
           request.path.startswith('/search_ajax') or \
           'favicon.ico' in request.path:
            return

        ua_string = (request.user_agent.string or "").lower()
        # Исключаем ботов и поисковики
        bots = ['bot', 'crawler', 'spider', 'slurp', 'google', 'yandex', 'bing', 'ahrefs', 'lighthouse', 'monitoring']
        if any(bot in ua_string for bot in bots):
            return

        try:
            import hashlib
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()
            
            ip_hash = hashlib.sha256((ip or 'unknown').encode()).hexdigest()
            path = request.path[:255]
            user_agent = request.user_agent.string[:512] if request.user_agent.string else None
            referrer = request.referrer[:512] if request.referrer else None
            
            # Асинхронное сохранение визита через executor
            def save_visit_async(app_context, h_ip, h_path, h_ua, h_ref):
                try:
                    with app_context:
                        from extensions import db
                        from models import Visit
                        visit = Visit(ip_hash=h_ip, path=h_path, user_agent=h_ua, referrer=h_ref)
                        db.session.add(visit)
                        db.session.commit()
                except Exception:
                    pass # Трафик не критичен
            
            executor.submit(save_visit_async, app.app_context(), ip_hash, path, user_agent, referrer)
        except Exception:
            pass

    # Precompute labels once globally
    SHORT_LABELS = {k: v.replace('Все ', '').replace('автомобили', '').strip() for k, v in CAT_TITLES.items()}

    # Кэширование времени изменения файлов для производительности
    def cached_mtime(file_path):
        if app.debug: # В режиме отладки всегда проверяем диск
            return int(os.path.getmtime(file_path)) if os.path.exists(file_path) else None
        
        if file_path not in _MTIME_CACHE:
            if os.path.exists(file_path):
                _MTIME_CACHE[file_path] = int(os.path.getmtime(file_path))
            else:
                _MTIME_CACHE[file_path] = None
        return _MTIME_CACHE[file_path]

    # Контекстный процессор для глобальных переменных
    @app.context_processor
    def inject_global_vars():
        from flask import url_for
        import os

        def static_versioned(filename):
            """Returns url for static file with modification time appended for cache busting."""
            file_path = os.path.join(app.root_path, 'static', filename)
            mtime = cached_mtime(file_path)
            
            if mtime:
                return f"{url_for('static', filename=filename)}?v={mtime}"
            return url_for('static', filename=filename)

        return {
            'cat_labels': SHORT_LABELS,
            'active_page': request.endpoint or "",
            'static_versioned': static_versioned
        }

    # Регистрация маршрутов
    with app.app_context():
        # Auto-create the database file and schema
        os.makedirs(app.instance_path, exist_ok=True)
        db.create_all()

        # 🚀 Умная миграция: SQLite (site.db) -> Postgres (Только при первом запуске)
        def migrate_internal(app_context):
            with app_context:
                try:
                    from models import Vehicle
                    from flask import current_app
                    from extensions import db as _db
                    from sqlalchemy import text
                    
                    # 🛠️ Шаг 1: Синхронизируем сиквенсы (лечит ошибки Duplicate Key)
                    tables = ['vehicle', 'article', 'lead', 'review', 'inspection_report']
                    for table in tables:
                        try:
                            # Postgres Only: Sync setval for ID counter
                            _db.session.execute(text(f"SELECT setval('{table}_id_seq', COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"))
                            _db.session.commit()
                        except Exception:
                            _db.session.rollback()

                    # Проверяем, пуста ли база
                    try:
                        if Vehicle.query.first():
                            return # Данные уже есть, ничего не делаем
                    except Exception:
                        pass
                    
                    sqlite_path = os.path.join(current_app.root_path, 'site.db')
                    if not os.path.exists(sqlite_path):
                        return
                    
                    import sqlite3
                    conn = sqlite3.connect(sqlite_path)
                    cursor = conn.cursor()
                    
                    for table_name in tables:
                        try:
                            cursor.execute(f"SELECT * FROM {table_name}")
                            rows = cursor.fetchall()
                            if not rows: continue
                            
                            cols = [description[0] for description in cursor.description]
                            for row in rows:
                                data = dict(zip(cols, row))
                                # Исправляем типы для PG
                                for k, v in data.items():
                                    if k in ['is_currency_fixed', 'is_published']:
                                        if v is not None: data[k] = bool(v)
                                
                                p_holders = ", ".join([f":{k}" for k in data.keys()])
                                col_names = ", ".join(data.keys())
                                # Используем ON CONFLICT, чтобы не падать при повторном деплое
                                _db.session.execute(text(f"INSERT INTO {table_name} ({col_names}) VALUES ({p_holders}) ON CONFLICT (id) DO NOTHING"), data)
                            _db.session.commit()
                        except Exception as table_err:
                            _db.session.rollback()
                            current_app.logger.warning(f"Миграция таблицы {table_name} пропущена: {table_err}")
                    conn.close()
                    
                    # Финальная синхронизация счетчиков
                    for table in tables:
                        try:
                            _db.session.execute(text(f"SELECT setval('{table}_id_seq', (SELECT MAX(id) FROM {table}))"))
                            _db.session.commit()
                        except:
                            _db.session.rollback()
                            
                    current_app.logger.info("Внутренняя миграция завершена.")
                except Exception as e:
                    current_app.logger.error(f"Ошибка миграции: {e}")

        # Запускаем миграцию один раз через executor
        executor.submit(migrate_internal, app.app_context())


        from routes.main import register_routes
        from routes.auth import register_auth_routes
        register_routes(app)
        register_auth_routes(app)

        # Настройка админки
        from admin.views import MyAdminIndexView, VehicleAdminView, LeadAdminView, ArticleAdminView, ReviewAdminView, InspectionReportAdminView
        from models import Vehicle, Lead, Article, Review, InspectionReport
        from flask_admin import Admin

        admin_url = '/' + app.config['ADMIN_ENDPOINT']
        admin = Admin(app, name='Турбо-ДВ Админ', 
                      index_view=MyAdminIndexView(name='Главная', url=admin_url), 
                      url=admin_url)

        admin.add_view(VehicleAdminView(Vehicle, db.session, name='Каталог техники'))
        admin.add_view(ArticleAdminView(Article, db.session, name='Статьи и Блог'))
        admin.add_view(ReviewAdminView(Review, db.session, name='Отзывы 2ГИС'))
        admin.add_view(LeadAdminView(Lead, db.session, name='Архив заявок'))
        admin.add_view(InspectionReportAdminView(InspectionReport, db.session, name='Отчеты дилеров (Китай)'))

        # ⏰ Надежный запуск планировщика для хостинга
        from services.currency import fetch_yuan_rate
        from services.maintenance import cleanup_old_visits
        fetch_yuan_rate() # Первичный запуск курса при старте
        
        if not scheduler.running:
            # Prevent apscheduler from spinning up multi instances if multiple workers are deployed
            if os.environ.get('WERKZEUG_RUN_MAIN') == 'true' or not app.debug:
                try:
                    scheduler.start()
                except Exception as e:
                    app.logger.warning(f"Scheduler failed to start or already running: {e}")

    # Настройка логирования
    logging.basicConfig(level=logging.INFO)

    @login_manager.user_loader
    def load_user(user_id):
        if user_id == app.config['ADMIN_USER']:
            return User(app.config['ADMIN_USER'])
        return None

    # Обработчики ошибок
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_server_error(e):
        db.session.rollback()
        return render_template('500.html'), 500

    return app

if __name__ == '__main__':
    app = create_app()
    # Debug is False by default for safety. Enable only via environment or manual change.
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0')
