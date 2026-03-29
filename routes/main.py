"""
Main application routes.
"""

from flask import render_template, abort, request, jsonify, url_for
from models import Vehicle, Article
from config import CAT_TITLES
from extensions import limiter, db, cache
from sqlalchemy.orm import load_only
import logging
import threading
from markupsafe import escape

logger = logging.getLogger(__name__)

def register_routes(app):

    @app.route('/sw.js')
    def service_worker():
        from flask import send_from_directory
        import os
        return send_from_directory(os.path.join(app.root_path, 'static'), 'sw.js', mimetype='application/javascript')

    @app.route('/manifest.json')
    def pwa_manifest():
        from flask import send_from_directory
        import os
        return send_from_directory(os.path.join(app.root_path, 'static'), 'manifest.json', mimetype='application/json')


    # ─── Конфигурация каталога (одно место для всех категорий) ───
    CATALOG_ROUTES = {
        # endpoint:    (url,                  filter_type,   filter_value,       title)
        'cars':              ('/cars',              'like',   'cars%',             'Все легковые автомобили'),
        'cars_new':          ('/cars/new',          'exact',  'cars_new',          'Новые легковые автомобили'),
        'cars_used':         ('/cars/used',         'exact',  'cars_used',         'Легковые с пробегом'),
        'trucks':            ('/trucks',            'like',   'trucks%',           'Грузовые автомобили'),
        'trucks_tractors':   ('/trucks/tractors',   'exact',  'trucks_tractors',   'Тягачи'),
        'trucks_dumpers':    ('/trucks/dumpers',    'exact',  'trucks_dumpers',    'Самосвалы'),
        'trucks_trucks':     ('/trucks/trucks',     'exact',  'trucks_trucks',     'Грузовики'),
        'trucks_vans':       ('/trucks/vans',       'exact',  'trucks_vans',       'Фургоны'),
        'trucks_km':         ('/trucks/km',         'exact',  'trucks_km',         'Бортовые с КМУ'),
        'trucks_evac':       ('/trucks/evac',       'exact',  'trucks_evac',       'Эвакуаторы'),
        'special':           ('/special',           'like',   'special%',          'Вся спецтехника'),
        'special_lifts':     ('/special/lifts',     'exact',  'special_lifts',     'Автовышки'),
        'special_frontal':   ('/special/frontal',   'exact',  'special_frontal',   'Фронтальные погрузчики'),
        'special_forklift':  ('/special/forklift',  'exact',  'special_forklift',  'Вилочные погрузчики'),
        'special_excavators':('/special/excavators', 'exact', 'special_excavators', 'Экскаваторы-погрузчики'),
    }

    # Общая оптимизация — колонки для списков
    CATALOG_COLUMNS = load_only(
        Vehicle.id, Vehicle.brand, Vehicle.model, Vehicle.price,
        Vehicle.year, Vehicle.main_image, Vehicle.slug, Vehicle.badge,
        Vehicle.category, Vehicle.mileage, Vehicle.status
    )

    # ─── Допустимые значения сортировки ───
    SORT_OPTIONS = {
        'newest': ('По новизне', Vehicle.id.desc()),
        'price_asc': ('Цена ↑', Vehicle.price.asc()),
        'price_desc': ('Цена ↓', Vehicle.price.desc()),
        'year_desc': ('Год ↓', Vehicle.year.desc()),
        'year_asc': ('Год ↑', Vehicle.year.asc()),
        'mileage_asc': ('Пробег ↑', Vehicle.mileage.asc()),
    }

    def _catalog_view(filter_type, filter_value, title):
        """Универсальный обработчик каталожных страниц с фильтрами."""
        page = request.args.get('page', 1, type=int)

        # --- Базовая фильтрация по категории ---
        base_query = Vehicle.query.options(CATALOG_COLUMNS)
        if filter_type == 'like':
            base_query = base_query.filter(Vehicle.category.like(filter_value))
        else:
            base_query = base_query.filter_by(category=filter_value)

        # --- Получаем список брендов ДО применения фильтров ---
        available_brands = sorted([
            b[0] for b in base_query.with_entities(Vehicle.brand).distinct().all()
        ])

        # --- Применение расширенных фильтров из query string ---
        query = base_query

        f_brand = request.args.get('brand', '').strip()
        if f_brand:
            query = query.filter(Vehicle.brand == f_brand)

        f_price_from = request.args.get('price_from', type=float)
        if f_price_from:
            query = query.filter(Vehicle.price >= f_price_from)

        f_price_to = request.args.get('price_to', type=float)
        if f_price_to:
            query = query.filter(Vehicle.price <= f_price_to)

        f_year_from = request.args.get('year_from', type=int)
        if f_year_from:
            query = query.filter(Vehicle.year >= f_year_from)

        f_year_to = request.args.get('year_to', type=int)
        if f_year_to:
            query = query.filter(Vehicle.year <= f_year_to)

        f_mileage_to = request.args.get('mileage_to', type=int)
        if f_mileage_to:
            query = query.filter(Vehicle.mileage <= f_mileage_to)

        # --- Сортировка ---
        sort_key = request.args.get('sort', 'newest')
        if sort_key in SORT_OPTIONS:
            _, order_clause = SORT_OPTIONS[sort_key]
            query = query.order_by(order_clause)
        else:
            query = query.order_by(Vehicle.id.desc())

        # --- Общее количество для отображения ---
        total_count = query.count()

        pagination = query.paginate(page=page, per_page=12, error_out=False)

        # Данные фильтров для сохранения состояния формы
        filter_data = {
            'brand': f_brand,
            'price_from': f_price_from or '',
            'price_to': f_price_to or '',
            'year_from': f_year_from or '',
            'year_to': f_year_to or '',
            'mileage_to': f_mileage_to or '',
            'sort': sort_key,
        }

        return render_template(
            'catalog.html',
            vehicles=pagination.items,
            pagination=pagination,
            title=title,
            available_brands=available_brands,
            filter_data=filter_data,
            total_count=total_count,
            sort_options=SORT_OPTIONS,
        )

    # ─── Регистрация всех каталожных маршрутов ───
    for endpoint, (url, filter_type, filter_value, title) in CATALOG_ROUTES.items():
        # Замыкание для захвата переменных
        def make_view(ft, fv, t):
            @cache.cached(timeout=300, query_string=True)
            def view():
                return _catalog_view(ft, fv, t)
            return view

        view_func = make_view(filter_type, filter_value, title)
        view_func.__name__ = endpoint
        app.add_url_rule(url, endpoint=endpoint, view_func=view_func)

    # Дополнительный алиас: /trucks_tractors → тот же вид
    @cache.cached(timeout=300, query_string=True)
    def _trucks_tractors_alias():
        return _catalog_view('exact', 'trucks_tractors', 'Тягачи')
    app.add_url_rule('/trucks_tractors', endpoint='trucks_tractors_alias',
                     view_func=_trucks_tractors_alias)

    # ─── Главная (кэш 5 минут) ───
    @app.route('/')
    @cache.cached(timeout=300)
    def index():
        from models import Review
        featured = Vehicle.query.options(CATALOG_COLUMNS).order_by(Vehicle.id.desc()).limit(6).all()
        reviews = Review.query.filter_by(is_published=True).order_by(Review.id.desc()).limit(10).all()
        brands = [b[0] for b in db.session.query(Vehicle.brand).distinct().all()]
        return render_template('index.html', featured=featured, reviews=reviews, brands=brands)

    # ─── Поиск ───
    @app.route('/search')
    @cache.cached(timeout=300, query_string=True)
    def search():
        page = request.args.get('page', 1, type=int)
        query = Vehicle.query.options(CATALOG_COLUMNS).filter(Vehicle.status == 'active')

        brand = request.args.get('brand')
        if brand: query = query.filter(Vehicle.brand == brand)

        model = request.args.get('model')
        if model:
            model_escaped = model.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            query = query.filter(Vehicle.model.ilike(f'%{model_escaped}%', escape='\\'))

        year_from = request.args.get('year_from', type=int)
        if year_from: query = query.filter(Vehicle.year >= year_from)

        year_to = request.args.get('year_to', type=int)
        if year_to: query = query.filter(Vehicle.year <= year_to)

        price_from = request.args.get('price_from', type=float)
        if price_from: query = query.filter(Vehicle.price >= price_from)

        price_to = request.args.get('price_to', type=float)
        if price_to: query = query.filter(Vehicle.price <= price_to)

        mileage_to = request.args.get('mileage_to', type=int)
        if mileage_to: query = query.filter(Vehicle.mileage <= mileage_to)

        is_new = request.args.get('is_new')
        if is_new:
            query = query.filter(
                (Vehicle.mileage == 0) | 
                (Vehicle.badge == 'Новый') | 
                (Vehicle.category == 'cars_new')
            )

        engine_from = request.args.get('engine_from', type=float)
        if engine_from: query = query.filter(Vehicle.engine_vol >= engine_from)

        body_type = request.args.get('body_type')
        if body_type: query = query.filter(Vehicle.body_type == body_type)

        # Сортировка
        sort_key = request.args.get('sort', 'newest')
        if sort_key in SORT_OPTIONS:
            _, order_clause = SORT_OPTIONS[sort_key]
            query = query.order_by(order_clause)
        else:
            query = query.order_by(Vehicle.id.desc())

        total_count = query.count()
        pagination = query.paginate(page=page, per_page=12, error_out=False)

        # Доступные бренды для dropdown
        available_brands = sorted([
            b[0] for b in db.session.query(Vehicle.brand).distinct().all()
        ])

        filter_data = {
            'brand': brand or '',
            'price_from': price_from or '',
            'price_to': price_to or '',
            'year_from': year_from or '',
            'year_to': year_to or '',
            'mileage_to': mileage_to or '',
            'engine_from': engine_from or '',
            'body_type': body_type or '',
            'sort': sort_key,
        }

        return render_template(
            'catalog.html',
            vehicles=pagination.items,
            pagination=pagination,
            title='Результаты поиска',
            available_brands=available_brands,
            filter_data=filter_data,
            total_count=total_count,
            sort_options=SORT_OPTIONS,
        )

    # Универсальный маршрут для каталога (legacy)
    @app.route('/category/<cat_slug>')
    @cache.cached(timeout=300, query_string=True)
    def catalog(cat_slug):
        page = request.args.get('page', 1, type=int)
        if cat_slug not in CAT_TITLES:
            abort(404)

        base_query = Vehicle.query.options(CATALOG_COLUMNS)

        if cat_slug == 'cars':
            base_query = base_query.filter(Vehicle.category.like('cars%'))
        elif cat_slug == 'trucks':
            base_query = base_query.filter(Vehicle.category.like('trucks%'))
        elif cat_slug == 'special':
            base_query = base_query.filter(Vehicle.category.like('special%'))
        else:
            base_query = base_query.filter_by(category=cat_slug)

        available_brands = sorted([
            b[0] for b in base_query.with_entities(Vehicle.brand).distinct().all()
        ])

        total_count = base_query.count()
        pagination = base_query.order_by(Vehicle.id.desc()).paginate(page=page, per_page=12, error_out=False)

        filter_data = {
            'brand': '', 'price_from': '', 'price_to': '',
            'year_from': '', 'year_to': '', 'mileage_to': '', 'sort': 'newest',
        }

        return render_template(
            'catalog.html',
            vehicles=pagination.items,
            pagination=pagination,
            title=CAT_TITLES[cat_slug],
            available_brands=available_brands,
            filter_data=filter_data,
            total_count=total_count,
            sort_options=SORT_OPTIONS,
        )


    # Подробная страница
    @app.route('/item/<slug>')
    def vehicle_detail(slug):
        vehicle = Vehicle.query.filter_by(slug=slug).first_or_404()
        return render_template('vehicle_detail.html', vehicle=vehicle)

    # Информационные страницы
    @app.route('/about')
    def about(): return render_template('info_about.html')

    @app.route('/privacy-policy')
    def privacy_policy(): return render_template('privacy_policy.html')

    @app.route('/how-to-buy')
    def how_to_buy(): return render_template('info_how_to_buy.html')

    @app.route('/delivery')
    def delivery(): return render_template('info_delivery.html')

    @app.route('/customs')
    def customs(): return render_template('info_customs.html')

    @app.route('/leasing')
    def leasing(): return render_template('info_leasing.html')

    # Блог и Статьи
    @app.route('/articles')
    def articles():
        page = request.args.get('page', 1, type=int)
        pagination = Article.query.order_by(Article.created_at.desc()).paginate(page=page, per_page=9, error_out=False)
        return render_template('articles.html', articles=pagination.items, pagination=pagination)

    @app.route('/article/<slug>')
    def article_detail(slug):
        article = Article.query.filter_by(slug=slug).first_or_404()
        return render_template('article_detail.html', article=article)


    @app.route('/search_ajax')
    @limiter.limit("30 per minute")
    @cache.cached(timeout=60, query_string=True)
    def search_ajax():
        q = request.args.get('q', '').strip()
        # Restrict length further to prevent heavy '%LIKE%' DB query DoS attacks
        if not q or len(q) < 2 or len(q) > 30:
            return jsonify([])

        # 🗄️ Уязвимость SQL-инъекции (экранируем спецсимволы LIKE)
        q_escaped = q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')

        # Use load_only or specific columns to save memory and DB transfer bandwidth
        results = Vehicle.query.options(
            load_only(Vehicle.brand, Vehicle.model, Vehicle.price, Vehicle.main_image, Vehicle.slug, Vehicle.category)
        ).filter(
            (Vehicle.brand.ilike(f'%{q_escaped}%', escape='\\')) | 
            (Vehicle.model.ilike(f'%{q_escaped}%', escape='\\'))
        ).limit(5).all()

        data = []
        for v in results:
            data.append({
                'brand': v.brand,
                'model': v.model,
                'price': float(v.price),
                'image': url_for('static', filename=v.main_image or 'images/no_photo.webp'),
                'url': url_for('vehicle_detail', slug=v.slug),
                'category': v.category
            })
        return jsonify(data)


    @app.route('/submit_lead', methods=['POST'])
    @limiter.limit("3 per minute")
    def submit_lead():
        name = request.form.get('name', 'Без имени').strip()
        phone = request.form.get('phone', 'Без телефона').strip()
        city = request.form.get('city', '').strip()
        item = request.form.get('item', 'Форма обратной связи').strip()
        email = request.form.get('email', '').strip()
        message = request.form.get('message', '').strip()
        
        from models import Lead
        from extensions import db as db_session
        
        # 📂 Сохраняем в базу данных (Архив) - Делаем в основном потоке для надежности
        new_lead_id = '?'
        try:
            new_lead = Lead(
                name=name,
                phone=phone,
                city=city,
                item=item,
                email=email,
                message=message
            )
            db_session.session.add(new_lead)
            db_session.session.commit()
            new_lead_id = new_lead.id
            logger.info(f"Заявка от {name} успешно сохранена в базу. ID: {new_lead_id}")
        except Exception as e:
            db_session.session.rollback()
            logger.error(f"Ошибка сохранения заявки в базу: {e}")

        # 📨 Отправка уведомлений в фоновом потоке
        def notify_async(lead_id, name, phone, city, item, email, message):
            with app.app_context():
                # Экранируем данные для безопасности
                safe_name = str(escape(name))
                safe_phone = str(escape(phone))
                safe_city = str(escape(city)) if city else ""
                safe_item = str(escape(item))
                safe_email = str(escape(email)) if email else ""
                safe_message = str(escape(message)) if message else ""

                # 1. Telegram
                tel_text = f"🔥 <b>Новая заявка с сайта!</b> (ID: {lead_id})\n\n" \
                           f"👤 <b>Имя:</b> {safe_name}\n" \
                           f"📞 <b>Телефон:</b> {safe_phone}\n"
                if safe_city: tel_text += f"📍 <b>Город:</b> {safe_city}\n"
                tel_text += f"🚘 <b>Интересует:</b> {safe_item}"
                if safe_email: tel_text += f"\n📧 <b>Email:</b> {safe_email}"
                if safe_message: tel_text += f"\n💬 <b>Сообщение:</b> {safe_message}"

                from services.telegram import send_telegram_message
                send_telegram_message(tel_text)

                # 2. Email
                from services.email_notify import send_email_notification
                email_subject = f"🔥 Новая заявка с сайта Турбо-ДВ: {safe_name} — {safe_item}"
                email_body = f"""
                <html><body style="font-family: Arial, sans-serif; background: #111; color: #eee; padding: 30px;">
                    <div style="max-width: 500px; margin: 0 auto; background: #1a1a1a; border-radius: 12px; padding: 30px; border: 1px solid #333;">
                        <h2 style="color: #e63946; margin-top: 0;">🔥 Новая заявка с сайта Турбо-ДВ</h2>
                        <table style="width: 100%; border-collapse: collapse;">
                            <tr><td style="padding: 8px 0; color: #999;">👤 Имя</td><td style="padding: 8px 0; font-weight: bold;">{safe_name}</td></tr>
                            <tr><td style="padding: 8px 0; color: #999;">📞 Телефон</td><td style="padding: 8px 0; font-weight: bold;">{safe_phone}</td></tr>
                            {"<tr><td style='padding: 8px 0; color: #999;'>📍 Город</td><td style='padding: 8px 0; font-weight: bold;'>" + safe_city + "</td></tr>" if safe_city else ""}
                            <tr><td style="padding: 8px 0; color: #999;">🚘 Интересует</td><td style="padding: 8px 0; font-weight: bold;">{safe_item}</td></tr>
                            {"<tr><td style='padding: 8px 0; color: #999;'>📧 Email</td><td style='padding: 8px 0;'>" + safe_email + "</td></tr>" if safe_email else ""}
                            {"<tr><td style='padding: 8px 0; color: #999; vertical-align: top;'>💬 Сообщение</td><td style='padding: 8px 0;'>" + safe_message + "</td></tr>" if safe_message else ""}
                        </table>
                    </div>
                </body></html>
                """
                send_email_notification(email_subject, email_body)

        from extensions import scheduler
        try:
            scheduler.add_job(
                id=f'notify_lead_{new_lead_id}',
                func=notify_async,
                args=(new_lead_id, name, phone, city, item, email, message),
                misfire_grace_time=3600
            )
        except Exception as e:
            logger.error(f"Ошибка планирования фоновой задачи: {e}")
            # Обычный тред как фоллбэк
            threading.Thread(target=notify_async, args=(
                new_lead_id, name, phone, city, item, email, message
            )).start()

        return jsonify(success=True)

    # Контакты
    @app.route('/contact')
    def contact():
        return render_template('contact.html')


    @app.route('/robots.txt')
    def robots():
        rules = (
            "User-agent: *\n"
            "Disallow: /admin/\n"
            "Disallow: /search_ajax\n"
            "Disallow: /*?search=\n"
            "Allow: /\n"
            "Sitemap: " + url_for('sitemap', _external=True)
        )
        return rules, 200, {'Content-Type': 'text/plain'}

    @app.route('/sitemap.xml')
    @cache.cached(timeout=3600)
    def sitemap():
        pages_set = set()
        # Static pages
        for rule in app.url_map.iter_rules():
            if "GET" in rule.methods and len(rule.arguments) == 0:
                endpoint = rule.endpoint
                if not any(x in endpoint for x in ['admin.', 'login', 'logout', 'robots', 'sitemap', 'static', 'search_ajax']):
                    pages_set.add(url_for(endpoint, _external=True))
        
        # Category pages
        for cat_slug in CAT_TITLES.keys():
            pages_set.add(url_for('catalog', cat_slug=cat_slug, _external=True))
            
        pages = list(pages_set)
        
        # Vehicle pages (Only slugs, to keep sitemap light)
        vehicles = Vehicle.query.options(load_only(Vehicle.slug)).all()
        for v in vehicles:
            pages.append(url_for('vehicle_detail', slug=v.slug, _external=True))
        
        # Article pages
        articles = Article.query.options(load_only(Article.slug)).all()
        for a in articles:
            pages.append(url_for('article_detail', slug=a.slug, _external=True))
            
        sitemap_xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        for page in pages:
            sitemap_xml += f'  <url><loc>{page}</loc><changefreq>daily</changefreq></url>\n'
        sitemap_xml += '</urlset>'
        
        return sitemap_xml, 200, {'Content-Type': 'application/xml'}
    # ─── ОТЧЕТЫ ДИЛЕРА (Внутренняя генерация осмотров) ───
    from extensions import csrf
    @app.route('/dealer/report/create', methods=['GET', 'POST'])
    @csrf.exempt
    def dealer_report_create():
        from flask_login import current_user
        # Проверка токена (Вариант Б) или логина (для админа)
        token = request.args.get('token') or request.form.get('token')
        valid_token = app.config.get('DEALER_TOKEN', 'TDV-CN-2026-SECRET')
        
        if not current_user.is_authenticated and token != valid_token:
            return "⛔ Ошибка доступа. Неверный ключ или не выполнен вход.", 403
            
        if request.method == 'POST':
            import os, uuid
            from werkzeug.utils import secure_filename
            from models import InspectionReport
            
            model_name = request.form.get('model')
            year = request.form.get('year')
            horsepower = request.form.get('horsepower')
            mileage = request.form.get('mileage')
            price = request.form.get('price')
            desc = request.form.get('desc')
            
            report_uid = f'TDV-{uuid.uuid4().hex[:6].upper()}'
            target_dir = os.path.join(app.root_path, 'static', 'reports', report_uid)
            os.makedirs(target_dir, exist_ok=True)
            
            saved_images = []
            files = request.files.getlist('photos')
            from PIL import Image, ImageOps
            for idx, file in enumerate(files):
                if file and file.filename:
                    filename = f'{idx}.webp'
                    path = os.path.join(target_dir, filename)
                    try:
                        img = Image.open(file)
                        img = ImageOps.exif_transpose(img)
                        img = img.convert('RGB')
                        img.save(path, 'WEBP', quality=95)
                        saved_images.append(f'reports/{report_uid}/{filename}')
                    except Exception as e:
                        logger.error(f'Error saving image: {e}')
            
            report = InspectionReport(
                report_uid=report_uid,
                model_name=model_name,
                year=int(year) if year else None,
                horsepower=int(horsepower) if horsepower else None,
                mileage=int(mileage) if mileage else None,
                price_cny=int(price) if price else None,
                description=desc,
                images=saved_images
            )
            db.session.add(report)
            db.session.commit()
            
            return jsonify({'success': True, 'url': url_for('view_report', uid=report_uid)})
            
        return render_template('dealer_report.html', token=token)

    @app.route('/report/<uid>')
    @csrf.exempt
    def view_report(uid):
        from models import InspectionReport
        report = InspectionReport.query.filter_by(report_uid=uid).first_or_404()
        return render_template('report_view.html', report=report)

    @app.route('/report/<uid>/download_photos')
    def report_download_photos(uid):
        from models import InspectionReport
        import zipfile
        import io
        from flask import send_file
        
        report = InspectionReport.query.filter_by(report_uid=uid).first_or_404()
        if not report.images:
            return 'No photos', 404
            
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w') as zf:
            for img_path in report.images:
                full_path = os.path.join(app.root_path, 'static', img_path)
                if os.path.exists(full_path):
                    zf.write(full_path, os.path.basename(img_path))
        
        memory_file.seek(0)
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'photos_{uid}.zip'
        )
