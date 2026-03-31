"""
Maintenance services for cleaning up old data and system optimization.
"""

import logging
from datetime import datetime, timedelta
from extensions import scheduler, db
from models import Visit

logger = logging.getLogger(__name__)

@scheduler.task('interval', id='cleanup_old_visits', hours=24)
def cleanup_old_visits():
    """Ежедневная задача по удалению старых записей о визитах (старше 30 дней)."""
    with scheduler.app.app_context():
        try:
            thirty_days_ago = datetime.utcnow() - timedelta(days=30)
            
            # Удаляем старые записи
            deleted_count = db.session.query(Visit).filter(
                Visit.created_at < thirty_days_ago
            ).delete()
            
            db.session.commit()
            if deleted_count > 0:
                logger.info(f"Обслуживание: Удалено {deleted_count} старых записей о визитах.")
        except Exception as e:
            db.session.rollback()
            logger.error(f"Ошибка при очистке старых визитов: {e}")
