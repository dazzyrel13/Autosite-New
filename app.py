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
            from threading import Thread
            
            ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if ip and ',' in ip:
                ip = ip.split(',')[0].strip()
            
            ip_hash = hashlib.sha256((ip or 'unknown').encode()).hexdigest()
            path = request.path[:255]
            user_agent = request.user_agent.string[:512] if request.user_agent.string else None
            referrer = request.referrer[:512] if request.referrer else None
            
            # Асинхронное сохранение визита, чтобы не тормозить загрузку страницы (не блокировать БД)
            def save_visit_async(app_context, h_ip, h_path, h_ua, h_ref):
                try:
                    with app_context:
                        from extensions import db
                        from models import Visit
                        visit = Visit(ip_hash=h_ip, path=h_path, user_agent=h_ua, referrer=h_ref)
                        db.session.add(visit)
                        db.session.commit()
                except Exception:
                    # Ignore DB locks or rollback issues in background metrics
                    pass
            
            # Start background thread with app context
            app_ctx = app.app_context()
            Thread(target=save_visit_async, args=(app_ctx, ip_hash, path, user_agent, referrer)).start()
        except Exception:
            pass # Трафик не критичен, не блокируем запрос

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

        # 🚀 Internal Migration: SQLite (site.db) -> Postgres
        def migrate_internal(app_context):
            with app_context:
                try:
                    from models import Vehicle
                    from flask import current_app
                    # Check if Postgres already has data
                    try:
                        first_vehicle = Vehicle.query.first()
                        if first_vehicle:
                            current_app.logger.info("Internal Migration: Data already exists in Postgres. Skipping.")
                            return # Already migrated
                    except Exception as e:
                        current_app.logger.error(f"Internal Migration check failed (maybe DB empty/error): {e}")
                    
                    sqlite_path = os.path.join(current_app.root_path, 'site.db')
                    if not os.path.exists(sqlite_path):
                        current_app.logger.warning(f"Internal Migration: site.db not found at {sqlite_path}")
                        return # No source file to migrate
                    
                    import sqlite3
                    conn = sqlite3.connect(sqlite_path)
                    cursor = conn.cursor()
                    
                    tables = ['vehicle', 'article', 'lead', 'review', 'inspection_report']
                    current_app.logger.info(f"Internal Migration: Starting migration for tables: {tables}")
                    
                    for table_name in tables:
                        try:
                            cursor.execute(f"SELECT * FROM {table_name}")
                            rows = cursor.fetchall()
                            if not rows: continue
                            
                            cols = [description[0] for description in cursor.description]
                            current_app.logger.info(f"Internal Migration: Migrating {len(rows)} rows from {table_name}")
                            
                            for row in rows:
                                data = dict(zip(cols, row))
                                
                                # 🛠️ Fix types for Postgres
                                for k, v in data.items():
                                    # 1. Convert 0/1 to True/False for Boolean fields (PG requirement)
                                    if k in ['is_currency_fixed', 'is_published']:
                                        if v is not None: data[k] = bool(v)
                                    # 2. JSON fields (images, specifications): 
                                    # SQLite provides strings. If we convert them to list/dict, psycopg2 
                                    # tries to insert as text[] (Postgres Array), failing the JSON match.
                                    # We keep them as strings; Postgres/Alchemy will handle the JSON parse.
                                
                                from extensions import db as _db
                                from sqlalchemy import text
                                p_holders = ", ".join([f":{k}" for k in data.keys()])
                                col_names = ", ".join(data.keys())
                                _db.session.execute(text(f"INSERT INTO {table_name} ({col_names}) VALUES ({p_holders}) ON CONFLICT DO NOTHING"), data)
                            _db.session.commit()
                            current_app.logger.info(f"Internal Migration: {table_name} success!")
                        except Exception as table_err:
                            from extensions import db as _db
                            _db.session.rollback() # Clear failed transaction in Postgres
                            current_app.logger.error(f"Internal Migration: {table_name} failed: {table_err}")
                    conn.close()
                    current_app.logger.info("Internal Migration: Migration complete.")
                    from extensions import cache as _cache
                    _cache.clear()
                except Exception as e:
                    try:
                        current_app.logger.critical(f"Internal Migration error: {e}")
                    except:
                        print(f"Migration CRITICAL error (no context): {e}")

        # Start background migration with proper app context
        from threading import Thread
        Thread(target=migrate_internal, args=(app.app_context(),)).start()


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
