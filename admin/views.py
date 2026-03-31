"""
Admin views and customizations.
"""

from flask_admin import AdminIndexView, expose
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from flask import jsonify, request, url_for, current_app, redirect
from admin.widgets import GalleryField
from wtforms import MultipleFileField, SelectField, TextAreaField
from markupsafe import Markup
import os
import uuid
from services.currency import fetch_yuan_rate
from services.parser import VehicleParser
from utils.helpers import slugify
from extensions import db, limiter
import logging

logger = logging.getLogger(__name__)

class MyAdminIndexView(AdminIndexView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=request.url))

    @expose('/')
    def index(self, **kwargs):
        from models import Vehicle, Article, Lead, Visit
        from extensions import db, cache
        from services.currency import current_rate
        from datetime import datetime, timedelta
        from sqlalchemy import func, cast, Date
        
        # Safely extract rate from dict or use fallback
        if isinstance(current_rate, dict):
            rate = current_rate.get('CNY', 13.0)
        else:
            rate = current_rate if isinstance(current_rate, (int, float)) else 13.0

        # ─── Основная статистика ───
        stats = {
            'total': Vehicle.query.count(),
            'cars': Vehicle.query.filter(Vehicle.category.like('cars%')).count(),
            'trucks': Vehicle.query.filter(Vehicle.category.like('trucks%')).count(),
            'special': Vehicle.query.filter(Vehicle.category.like('special%')).count(),
            'articles': Article.query.count(),
            'avg_price': db.session.query(db.func.avg(Vehicle.price)).scalar() or 0,
            'cny_rate': float(rate),
            'leads_total': Lead.query.count(),
            'leads_new': Lead.query.filter_by(status='new').count(),
            'leads_processed': Lead.query.filter_by(status='processed').count(),
        }
        
        # ─── Заявки по дням (последние 30 дней) ───
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        leads_by_day_raw = db.session.query(
            func.date(Lead.created_at).label('day'),
            func.count(Lead.id).label('cnt')
        ).filter(
            Lead.created_at >= thirty_days_ago
        ).group_by('day').order_by('day').all()

        # Заполняем пропуски (дни без заявок = 0)
        leads_by_day = {}
        for i in range(30, -1, -1):
            day = (datetime.utcnow() - timedelta(days=i)).strftime('%d.%m')
            leads_by_day[day] = 0
        for row in leads_by_day_raw:
            if row.day:
                day_str = row.day if isinstance(row.day, str) else row.day.strftime('%Y-%m-%d')
                try:
                    day_key = datetime.strptime(day_str, '%Y-%m-%d').strftime('%d.%m')
                    if day_key in leads_by_day:
                        leads_by_day[day_key] = row.cnt
                except Exception:
                    pass

        # ─── Популярные бренды (топ-8 по кол-ву в каталоге) ───
        popular_brands = db.session.query(
            Vehicle.brand, func.count(Vehicle.id).label('cnt')
        ).group_by(Vehicle.brand).order_by(func.count(Vehicle.id).desc()).limit(8).all()

        # ─── Самые просматриваемые модели (по заявкам — item field) ───
        popular_items = db.session.query(
            Lead.item, func.count(Lead.id).label('cnt')
        ).filter(
            Lead.item.isnot(None),
            Lead.item != '',
            Lead.item != 'Форма обратной связи'
        ).group_by(Lead.item).order_by(func.count(Lead.id).desc()).limit(6).all()

        # ─── Заявки по статусам ───
        lead_statuses = db.session.query(
            Lead.status, func.count(Lead.id).label('cnt')
        ).group_by(Lead.status).all()

        # ─── Заявки по городам (top 5) ───
        leads_by_city = db.session.query(
            Lead.city, func.count(Lead.id).label('cnt')
        ).filter(
            Lead.city.isnot(None), Lead.city != ''
        ).group_by(Lead.city).order_by(func.count(Lead.id).desc()).limit(5).all()

        # ─── Трафик (Визиты) ───
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        
        visits_today = Visit.query.filter(Visit.created_at >= today_start).count()
        visitors_today = db.session.query(func.count(func.distinct(Visit.ip_hash))).filter(Visit.created_at >= today_start).scalar() or 0
        visits_yesterday = Visit.query.filter(Visit.created_at >= yesterday_start, Visit.created_at < today_start).count()

        # Трафик по дням (последние 30 дней)
        traffic_raw = db.session.query(
            func.date(Visit.created_at).label('day'),
            func.count(Visit.id).label('pv'),
            func.count(func.distinct(Visit.ip_hash)).label('uv')
        ).filter(Visit.created_at >= thirty_days_ago).group_by('day').order_by('day').all()

        traffic_by_day = {day: {'pv': 0, 'uv': 0} for day in leads_by_day.keys()}
        for row in traffic_raw:
            if row.day:
                day_str = row.day if isinstance(row.day, str) else row.day.strftime('%Y-%m-%d')
                try:
                    day_key = datetime.strptime(day_str, '%Y-%m-%d').strftime('%d.%m')
                    if day_key in traffic_by_day:
                        traffic_by_day[day_key] = {'pv': row.pv, 'uv': row.uv}
                except Exception:
                    pass

        # Самые популярные страницы
        top_pages = db.session.query(
            Visit.path, func.count(Visit.id).label('cnt')
        ).group_by(Visit.path).order_by(func.count(Visit.id).desc()).limit(8).all()

        analytics = {
            'leads_by_day_labels': list(leads_by_day.keys()),
            'leads_by_day_data': list(leads_by_day.values()),
            'popular_brands': [{'name': b[0], 'count': b[1]} for b in popular_brands],
            'popular_items': [{'name': i[0][:40], 'count': i[1]} for i in popular_items],
            'lead_statuses': {s[0] or 'new': s[1] for s in lead_statuses},
            'leads_by_city': [{'name': c[0], 'count': c[1]} for c in leads_by_city],
            'traffic_labels': list(traffic_by_day.keys()),
            'traffic_pv_data': [v['pv'] for v in traffic_by_day.values()],
            'traffic_uv_data': [v['uv'] for v in traffic_by_day.values()],
            'top_pages': [{'path': p[0], 'count': p[1]} for p in top_pages],
            'visits_today': visits_today,
            'visitors_today': visitors_today,
            'visits_yesterday': visits_yesterday
        }
        
        recent = Vehicle.query.order_by(Vehicle.id.desc()).limit(10).all()
        return self.render('admin/index_custom.html', stats=stats, recent=recent, analytics=analytics)

    @expose('/update_price', methods=['POST'])
    def update_price(self):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        from models import Vehicle
        from extensions import db
        from services.currency import current_rate
        
        try:
            v_id = request.form.get('id')
            field = request.form.get('field')
            value = request.form.get('value')
            
            vehicle = Vehicle.query.get(v_id)
            if not vehicle:
                return jsonify({'success': False, 'error': 'Vehicle not found'})
            
            if field == 'price_cny':
                vehicle.price_cny = float(value)
                if not vehicle.is_currency_fixed:
                    rate = current_rate.get('CNY', 13.0) if isinstance(current_rate, dict) else current_rate
                    vehicle.price = float(vehicle.price_cny) * rate
            elif field == 'price':
                vehicle.price = float(value)
            elif field == 'is_currency_fixed':
                vehicle.is_currency_fixed = value.lower() == 'true'
                if not vehicle.is_currency_fixed and vehicle.price_cny:
                    rate = current_rate.get('CNY', 13.0) if isinstance(current_rate, dict) else current_rate
                    vehicle.price = float(vehicle.price_cny) * rate
            
            db.session.commit()
            return jsonify({'success': True, 'new_price_rub': float(vehicle.price)})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)})

    @expose('/sync_prices', methods=['POST'])
    def sync_prices(self):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
        from models import Vehicle
        from extensions import db
        from services.currency import fetch_yuan_rate, current_rate
        
        try:
            from decimal import Decimal
            rate_float = fetch_yuan_rate()
            rate = Decimal(str(rate_float))
            
            vehicles = Vehicle.query.filter_by(is_currency_fixed=False).all()
            count = 0
            for v in vehicles:
                if v.price_cny:
                    v.price = v.price_cny * rate
                    count += 1
            db.session.commit()
            return jsonify({'success': True, 'message': f'Обновлено цен: {count}. Текущий курс: {rate_float:.2f} ₽'})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)})

    @expose('/parse_link', methods=['POST'])
    def parse_link_view(self):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
        
        try:
            url = request.form.get('url')
            if not url:
                return jsonify({'success': False, 'error': 'No URL provided'})

            result = VehicleParser.parse_link(url)
            
            if result:
                params = {
                    'category': result.get('category', 'cars_used'),
                    'brand': result.get('brand', ''),
                    'model': result.get('model', ''),
                    'year': result.get('year', ''),
                    'price': result.get('price', ''),
                    'mileage': result.get('mileage', ''),
                    'engine_vol': result.get('engine_vol', ''),
                    'description': result.get('description', '')
                }
                from urllib.parse import urlencode
                # Redirect to the create view of the Vehicle model in Flask-Admin
                # Check for the correct endpoint name, usually it is vehicle.create_view
                redirect_url = url_for('vehicle.create_view') + '?' + urlencode({k: v for k, v in params.items() if v})
                return jsonify({'success': True, 'redirect_url': redirect_url})
            else:
                return jsonify({'success': False, 'error': 'Could not parse link'})
        except Exception as e:
            logger.error(f"Error parsing link: {e}")
            return jsonify({'success': False, 'error': str(e)})

    @expose('/bulk_import', methods=['POST'])
    def bulk_import(self):
        if not current_user.is_authenticated:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 401
            
        from models import Vehicle
        from extensions import db
        from utils.helpers import slugify
        
        try:
            url = request.form.get('url')
            if not url:
                return jsonify({'success': False, 'error': 'No URL provided'})

            results = VehicleParser.parse_bulk(url)
            
            if not results:
                return jsonify({'success': False, 'error': 'No vehicles found on page'})
                
            count = 0
            for item in results:
                # Check if already exists by brand/model/year
                exists = Vehicle.query.filter_by(
                    brand=item['brand'], model=item['model'], year=item['year']
                ).exists()
                
                if db.session.query(exists).scalar():
                    continue

                v = Vehicle(
                    brand=item['brand'],
                    model=item['model'],
                    year=item['year'],
                    price=item['price'],
                    category=item.get('category', 'cars_used'),
                    mileage=item.get('mileage'),
                    engine_vol=item.get('engine_vol'),
                    description=item.get('description', ''),
                    status='active',
                    badge='С пробегом' if 'used' in item.get('category', '') else 'В наличии',
                    specifications=[], # Use empty list instead of None
                    images=[]
                )
                v.slug = slugify(f"{v.brand}-{v.model}-{v.year}-{uuid.uuid4().hex[:4]}")
                
                # Download external image
                ext_img = item.get('external_image')
                if ext_img:
                    import requests
                    from io import BytesIO
                    try:
                        folder_name = v.slug
                        target_dir = os.path.join(current_app.root_path, 'static', 'images', folder_name)
                        os.makedirs(target_dir, exist_ok=True)
                        
                        img_filename = f"main_{uuid.uuid4().hex[:6]}.webp"
                        img_path = os.path.join(target_dir, img_filename)
                        
                        resp = requests.get(ext_img, timeout=10)
                        if resp.status_code == 200:
                            from PIL import Image
                            img = Image.open(BytesIO(resp.content))
                            img.thumbnail((1200, 800), Image.LANCZOS)
                            img.save(img_path, 'WEBP', quality=85)
                            
                            v.main_image = f"images/{folder_name}/{img_filename}"
                            v.images = [v.main_image]
                    except Exception as img_err:
                        logger.error(f"Failed to download image: {img_err}")
                        v.images = [] # Ensure it's a list

                db.session.add(v)
                count += 1
            
            db.session.commit()
            return jsonify({'success': True, 'message': f'Успешно импортировано {count} автомобилей'})
            
        except Exception as e:
            db.session.rollback()
            logger.error(f"Bulk import error: {e}")
            return jsonify({'success': False, 'error': str(e)})

class SafeModelView(ModelView):
    """Base model view that requires authentication."""
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login', next=request.url))

class VehicleAdminView(SafeModelView):
    def _toggle_formatter(view, context, model, name):
        """Рендерит чекбокс, который переключается через AJAX."""
        from flask_wtf.csrf import generate_csrf
        checked = 'checked' if model.is_currency_fixed else ''
        # Генерируем базовый URL в Python, а ID и состояние подставим в JS
        base_url = url_for('vehicle.toggle_fixed_api', id=0, state=0)
        csrf_token = generate_csrf()
        
        return Markup(f'''
            <div class="form-check form-switch">
                <input class="form-check-input" type="checkbox" {checked} 
                       onclick="toggleFixed({model.id}, this.checked)"
                       style="cursor:pointer; width: 40px; height: 20px;">
            </div>
            <script>
            if (typeof toggleFixed === "undefined") {{
                window.toggleFixed = function(id, state) {{
                    const val = state ? 1 : 0;
                    const url = "{base_url}".replace('0/0', id + '/' + val);
                    fetch(url, {{
                        method: 'POST',
                        headers: {{ 
                            'X-CSRFToken': '{csrf_token}',
                            'Content-Type': 'application/json' 
                        }}
                    }}).then(res => res.json())
                       .then(data => {{ if(!data.success) alert('Ошибка сохранения: ' + (data.error || 'неизвестно')); }});
                }}
            }}
            </script>
        ''')

    column_formatters = {
        'is_currency_fixed': _toggle_formatter
    }

    @expose('/toggle_fixed/<int:id>/<int:state>', methods=['POST'])
    def toggle_fixed_api(self, id, state):
        """API endpoint to toggle fixed state from the list view via AJAX."""
        from models import Vehicle
        from extensions import db
        v = Vehicle.query.get_or_404(id)
        v.is_currency_fixed = bool(state)
        db.session.commit()
        return jsonify({'success': True})

    column_list = ('brand', 'model', 'year', 'price', 'price_cny', 'is_currency_fixed', 'category', 'status', 'created_at')
    column_filters = ('brand', 'category', 'status', 'year', 'is_currency_fixed')
    column_searchable_list = ('brand', 'model')
    column_editable_list = ('status', 'price', 'price_cny') # removed is_currency_fixed from here to use formatter
    
    column_labels = {
        'brand': 'Марка', 'model': 'Модель', 'year': 'Год',
        'price': 'Цена (₽)', 'price_cny': 'Цена (¥)',
        'is_currency_fixed': 'ФИКС',
        'category': 'Категория',
        'status': 'Статус', 'created_at': 'Добавлено',
        'mileage': 'Пробег (км)',
        'engine_vol': 'Объем (л)', 'description': 'Описание'
    }

    form_extra_fields = {
        'upload_images': MultipleFileField('🖼️ Загрузить фото (WebP)'),
        'images_gallery': GalleryField('📸 Галерея (удаление)'),
    }

    form_columns = [
        'category', 'brand', 'model', 'year', 'price', 'price_cny', 'is_currency_fixed', 'status',
        'mileage', 'engine_vol', 'power', 'badge', 'description', 'upload_images', 'images_gallery'
    ]

    def on_model_change(self, form, model, is_created):
        """Handle image uploads, slug generation and price auto-calc."""
        from extensions import cache
        cache.clear() # Clear cache on any manual change

        if not model.slug:
            model.slug = slugify(f"{model.brand}-{model.model}-{model.year}-{uuid.uuid4().hex[:6]}")

        # Auto-calculate price in RUB if CNY is provided and NOT fixed
        if model.price_cny and not model.is_currency_fixed:
            from services.currency import current_rate
            rate = current_rate.get('CNY', 13.0) if isinstance(current_rate, dict) else current_rate
            model.price = round(float(model.price_cny) * float(rate))

        # Update main_image if not set
        existing_images = list(model.images) if model.images else []
        
        uploaded_files = request.files.getlist('upload_images')
        new_images = []

        if uploaded_files and uploaded_files[0].filename:
            folder_name = model.slug
            target_dir = os.path.join(current_app.root_path, 'static', 'images', folder_name)
            os.makedirs(target_dir, exist_ok=True)

            for idx, file in enumerate(uploaded_files):
                if not file: continue
                filename = f"{idx}_{uuid.uuid4().hex[:6]}.webp"
                file_path = os.path.join(target_dir, filename)
                
                try:
                    from PIL import Image
                    img = Image.open(file)
                    img.thumbnail((1200, 800), Image.LANCZOS)
                    img.save(file_path, 'WEBP', quality=85)
                    new_images.append(f"images/{folder_name}/{filename}")
                except Exception as e:
                    logger.error(f"Error processing image {file.filename}: {e}")

        combined_images = existing_images + new_images
        model.images = combined_images
        
        if combined_images:
            model.main_image = combined_images[0]
        else:
            model.main_image = ""

    def on_model_delete(self, model):
        """Полная очистка кэша и диска при удалении автомобиля."""
        from extensions import cache
        import shutil
        cache.clear()

        # Путь к папке с изображениями авто: static/images/<slug>
        if model.slug:
            try:
                target_dir = os.path.join(current_app.root_path, 'static', 'images', model.slug)
                if os.path.exists(target_dir):
                    shutil.rmtree(target_dir)
                    logger.info(f"Папка с фото авто {model.slug} успешно удалена.")
            except Exception as e:
                logger.error(f"Ошибка удаления папки авто {model.slug}: {e}")

class LeadAdminView(SafeModelView):
    can_create = False
    can_edit = True
    can_delete = True
    
    column_list = ('id', 'created_at', 'status', 'name', 'phone', 'item', 'city')
    column_default_sort = ('created_at', True)
    column_filters = ('status', 'city')
    column_searchable_list = ('name', 'phone', 'message', 'item')
    
    column_labels = {
        'id': 'ID', 'created_at': 'Дата', 'status': 'Статус',
        'name': 'Имя', 'phone': 'Телефон', 'city': 'Город',
        'item': 'Техника', 'message': 'Сообщение', 'email': 'Email'
    }
    
    form_choices = {'status': [('new', 'Новая'), ('processed', 'В работе'), ('archived', 'Архив')]}
    form_overrides = {'status': SelectField, 'message': TextAreaField}
    form_args = {'status': {'choices': [('new', 'Новая'), ('processed', 'В работе'), ('archived', 'Архив')], 'label': 'Статус'}}

class ArticleAdminView(SafeModelView):
    form_extra_fields = {
        'upload_image': MultipleFileField('🖼️ Главное фото статьи (WebP)'),
        'content': TextAreaField('Содержание (HTML приветствуется)'),
    }
    
    column_list = ('title', 'created_at')
    column_labels = {'title': 'Заголовок', 'created_at': 'Дата публикации', 'content': 'Текст статьи', 'summary': 'Краткое описание'}
    
    def on_model_change(self, form, model, is_created):
        if not model.slug:
            model.slug = slugify(model.title)
        
        uploaded = request.files.getlist('upload_image')
        if uploaded and uploaded[0].filename:
            file = uploaded[0]
            folder_name = 'articles'
            target_dir = os.path.join(current_app.root_path, 'static', 'images', folder_name)
            os.makedirs(target_dir, exist_ok=True)
            
            filename = f"{model.slug}.webp"
            file_path = os.path.join(target_dir, filename)
            
            from PIL import Image
            img = Image.open(file)
            img.thumbnail((1200, 800), Image.LANCZOS)
            img.save(file_path, 'WEBP', quality=85)
            model.main_image = f"images/{folder_name}/{filename}"

    def on_model_delete(self, model):
        """Удаляем фото статьи при её удалении."""
        from extensions import cache
        cache.clear()
        if model.main_image:
            try:
                full_path = os.path.join(current_app.root_path, 'static', model.main_image)
                if os.path.exists(full_path):
                    os.remove(full_path)
                    logger.info(f"Фото статьи {model.title} удалено.")
            except Exception as e:
                logger.error(f"Ошибка удаления фото статьи: {e}")

class ReviewAdminView(SafeModelView):
    can_edit = True
    can_delete = True
    can_view_details = True

    column_list = ('author_name', 'rating', 'source', 'vehicle_model', 'is_published', 'created_at')
    column_searchable_list = ['author_name', 'text', 'vehicle_model']
    column_filters = ['rating', 'source', 'is_published']
    column_editable_list = ['is_published', 'rating']

    column_labels = {
        'author_name': 'Имя клиента', 'rating': 'Оценка (1-5 звёзд)', 'text': 'Текст отзыва',
        'source': 'Источник (напр., 2ГИС)', 'vehicle_model': 'За какую машину (опционально)',
        'is_published': 'Отображать на Главной', 'created_at': 'Дата'
    }
    
    form_columns = ['author_name', 'rating', 'source', 'vehicle_model', 'text', 'is_published']

class InspectionReportAdminView(SafeModelView):
    column_list = ['report_uid', 'model_name', 'year', 'price_cny', 'created_at']
    column_searchable_list = ['model_name', 'report_uid']
    column_filters = ['created_at']
    can_create = False
    
    def on_model_delete(self, model):
        import traceback, logging, os, shutil
        from flask import current_app
        try:
            target_dir = os.path.join(current_app.root_path, 'static', 'reports', model.report_uid)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
        except Exception as e:
            logging.error(f'Ошибка удаления папки отчета {model.report_uid}: {e}')
            traceback.print_exc()

    
    from flask_admin.actions import action
    from flask import current_app, flash, redirect, url_for
    import os, shutil, uuid

    @action('publish_to_catalog', 'Скопировать в Каталог (Быстро)', 'Превратить выбранные отчеты в машины на сайте?')
    def action_publish(self, ids):
        from models import InspectionReport, Vehicle
        from extensions import db
        from services.currency import current_rate
        from utils.helpers import slugify
        
        count = 0
        rate = current_rate.get('CNY', 13.0) if isinstance(current_rate, dict) else current_rate
        rate = float(rate)
        
        for r_id in ids:
            report = InspectionReport.query.get(r_id)
            if not report: continue
            
            parts = report.model_name.strip().split(' ', 1)
            brand = parts[0]
            model_name = parts[1] if len(parts)>1 else ''
            slug = slugify(f'{brand}-{model_name}-{report.year}-{uuid.uuid4().hex[:6]}')
            
            copied_images = []
            if report.images:
                target_dir = os.path.join(current_app.root_path, 'static', 'images', slug)
                os.makedirs(target_dir, exist_ok=True)
                for rel_img_path in report.images:
                    src_full = os.path.join(current_app.root_path, 'static', rel_img_path)
                    if os.path.exists(src_full):
                        filename = os.path.basename(rel_img_path)
                        dst_full = os.path.join(target_dir, filename)
                        shutil.copy2(src_full, dst_full)
                        copied_images.append(f'images/{slug}/{filename}')
            
            v = Vehicle(
                brand=brand, model=model_name, year=report.year,
                horsepower=report.horsepower, mileage=report.mileage,
                price_cny=report.price_cny, price=round(float(report.price_cny or 0) * rate),
                description='Авто по результатам осмотра ' + report.report_uid + '.\n' + (report.description or ''),
                slug=slug, category='cars_used', images=copied_images,
                main_image=copied_images[0] if copied_images else ''
            )
            db.session.add(v)
            count += 1
        db.session.commit()
        from extensions import cache
        cache.clear()
        flash(f'Успешно перенесено {count} авто в каталог!', 'success')

    @action('publish_and_edit', 'Перенести и РЕДАКТИРОВАТЬ', 'Данные будут скопированы, и вы сразу перейдете к редактированию карточки товара.')
    def action_publish_and_edit(self, ids):
        from models import InspectionReport, Vehicle
        from extensions import db
        from services.currency import current_rate
        from utils.helpers import slugify
        
        if len(ids) > 1:
            flash('Для редактирования выберите только ОДИН отчет.', 'warning')
            return redirect(url_for('.index_view'))

        report = InspectionReport.query.get(ids[0])
        if not report: return

        rate = current_rate.get('CNY', 13.0) if isinstance(current_rate, dict) else current_rate
        rate = float(rate)
        
        parts = report.model_name.strip().split(' ', 1)
        brand = parts[0]
        model_name = parts[1] if len(parts)>1 else ''
        slug = slugify(f'{brand}-{model_name}-{report.year}-{uuid.uuid4().hex[:6]}')
        
        copied_images = []
        if report.images:
            target_dir = os.path.join(current_app.root_path, 'static', 'images', slug)
            os.makedirs(target_dir, exist_ok=True)
            for rel_img_path in report.images:
                src_full = os.path.join(current_app.root_path, 'static', rel_img_path)
                if os.path.exists(src_full):
                    filename = os.path.basename(rel_img_path)
                    dst_full = os.path.join(target_dir, filename)
                    shutil.copy2(src_full, dst_full)
                    copied_images.append(f'images/{slug}/{filename}')
        
        v = Vehicle(
            brand=brand, model=model_name, year=report.year,
            horsepower=report.horsepower, mileage=report.mileage,
            price_cny=report.price_cny, price=round(float(report.price_cny or 0) * rate),
            description=(report.description or ''),
            slug=slug, category='cars_used', images=copied_images,
            main_image=copied_images[0] if copied_images else ''
        )
        db.session.add(v)
        db.session.commit()
        from extensions import cache
        cache.clear()
        
        flash('Данные скопированы. Теперь проверьте и отредактируйте их перед публикацией.', 'info')
        return redirect(url_for('vehicle.edit_view', id=v.id))
