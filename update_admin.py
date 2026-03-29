
import codecs
import re
import os

target_file = 'admin/views.py'
with codecs.open(target_file, 'r', 'utf-8') as f:
    code = f.read()

# Define the new content for the actions
new_actions = """
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
                description='Авто по результатам осмотра ' + report.report_uid + '.\\n' + (report.description or ''),
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
"""

# Find where class InspectionReportAdminView(AuthModelView): ends or the old action starts
# I'll just look for the class start and append within it.
class_start_pattern = r"class InspectionReportAdminView\(AuthModelView\):"
old_action_marker = r"from flask_admin.actions import action"

if re.search(old_action_marker, code):
    # If the old action block exists, replace everything from it to the end of the file
    code = re.split(old_action_marker, code)[0] + new_actions
else:
    # Otherwise append it to the end of the class
    class_match = re.search(class_start_pattern, code)
    if class_match:
        # Append after the end of the class (simplest way is to append to file if it was the last class)
        code += new_actions

with codecs.open(target_file, 'w', 'utf-8') as f:
    f.write(code)
