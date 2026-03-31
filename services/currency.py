"""
Currency-related services.
"""

import requests
from decimal import Decimal
import logging
from extensions import scheduler, db
from models import Vehicle

# По умолчанию используем среднее значение, если API недоступен
# Внимание: при запуске это значение будет обновлено через fetch_yuan_rate() в app.py
from extensions import cache

class CachedRateSync(dict):
    """Словарь-прокси, который синхронизирует курс валют через глобальный кэш."""
    def get(self, key, default=None):
        if key == 'CNY':
            cached_val = cache.get('cny_rate')
            if cached_val: return cached_val
        return super().get(key, default)
    
    def __getitem__(self, key):
        if key == 'CNY':
            cached_val = cache.get('cny_rate')
            if cached_val: return cached_val
        return super().__getitem__(key)

current_rate = CachedRateSync({'CNY': 13.1})

logger = logging.getLogger(__name__)

def fetch_yuan_rate():
    """Получает текущий курс юаня к рублю от ЦБ РФ."""
    try:
        response = requests.get("https://www.cbr-xml-daily.ru/daily_json.js", timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Извлекаем курс из структуры JSON ЦБ РФ
        rate = float(data['Valute']['CNY']['Value'])
        nominal = float(data['Valute']['CNY']['Nominal'])
        final_rate = round(rate / nominal, 4)
        
        current_rate['CNY'] = final_rate
        # Сохраняем в кэш на 24 часа для синхронизации между воркерами
        cache.set('cny_rate', final_rate, timeout=86400)
        
        logger.info(f"Курс юаня успешно обновлен: {final_rate} руб.")
        return final_rate
    except Exception as e:
        logger.error(f"Не удалось обновить курс валют (используем {current_rate.get('CNY')}): {str(e)}")
        return current_rate.get('CNY')

@scheduler.task('interval', id='update_prices', hours=6)
def update_all_prices():
    """Фоновая задача для обновления всех цен в рублях на основе курса юаня."""
    with scheduler.app.app_context():
        try:
            rate = Decimal(str(fetch_yuan_rate()))
            
            # Optimize by using a bulk update instead of querying all rows
            updated_count = db.session.query(Vehicle).filter(
                Vehicle.is_currency_fixed.is_(False), 
                Vehicle.price_cny.isnot(None)
            ).update(
                {"price": Vehicle.price_cny * rate}, synchronize_session=False
            )
            
            db.session.commit()
            logger.info(f"Все цены успешно обновлены по курсу. Обновлено {updated_count} позиций.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при обновлении цен по курсу: {e}")