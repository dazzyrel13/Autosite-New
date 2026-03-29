"""
Email notification service using SMTP (Yandex Mail recommended for Russia).
"""
import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


def send_email_notification(subject: str, body_html: str) -> bool:
    """
    Отправляет email-уведомление о новой заявке.
    Настраивается через переменные окружения в .env:
      EMAIL_FROM     - адрес отправителя (ваш Яндекс) 
      EMAIL_TO       - адрес получателя (куда приходят заявки)
      EMAIL_PASSWORD - App-пароль приложения от Яндекс
      EMAIL_SMTP     - SMTP-сервер (по умолчанию smtp.yandex.ru)
      EMAIL_PORT     - порт (по умолчанию 465)
    """
    email_from = os.getenv('EMAIL_FROM')
    email_to = os.getenv('EMAIL_TO', email_from)  # Если не указан — шлём самому себе
    email_password = os.getenv('EMAIL_PASSWORD')
    smtp_host = os.getenv('EMAIL_SMTP', 'smtp.yandex.ru')
    smtp_port = int(os.getenv('EMAIL_PORT', '465'))

    if not email_from or not email_password:
        logger.warning("Email не настроен: нет EMAIL_FROM или EMAIL_PASSWORD в .env")
        return False

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = email_from
    msg['To'] = email_to

    html_part = MIMEText(body_html, 'html', 'utf-8')
    msg.attach(html_part)

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10) as smtp:
            smtp.login(email_from, email_password)
            smtp.sendmail(email_from, email_to, msg.as_string())
        logger.info(f"Email успешно отправлен на {email_to}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки email: {e}")
        return False
