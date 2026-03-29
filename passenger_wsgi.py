import sys
import os

# Добавляем путь к проекту в sys.path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

# Passenger ищет переменную 'application'
application = create_app()
