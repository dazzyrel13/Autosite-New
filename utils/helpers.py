"""
Utility functions for the application.
"""

import re


def slugify(text):
    """
    Транслитерирует кириллицу в латиницу и превращает строку 
    в аккуратный URL-слаг (ASCII-friendly).
    """
    symbols = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ы': 'y', 'э': 'e', 'ю': 'yu', 'я': 'ya', ' ': '_', '-': '_',
        '0': '0', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6',
        '7': '7', '8': '8', '9': '9'
    }
    
    # Приводим к нижнему регистру
    res = text.lower()
    
    # Транслитерация по словарю
    final = ""
    for char in res:
        if char in symbols:
            final += symbols[char]
        elif 'a' <= char <= 'z':
            final += char
        elif char == '_':
            final += char
            
    # Удаляем лишние подчеркивания по краям и дубликаты
    final = re.sub(r'_+', '_', final).strip('_')
    
    # Если на выходе пусто (например, только арабские символы), используем timestamp
    if not final:
        import time
        final = "item_" + str(int(time.time()))
        
    return final


def get_category_path(category):
    """Return the static subfolder path based on category."""
    if category.startswith('cars_new'):
        return 'images/cars/new'
    elif category.startswith('cars_used'):
        return 'images/cars/used'
    elif category.startswith('trucks'):
        # Map trucks to their specific subfolders or generic
        sub = category.replace('trucks_', '')
        if sub in ['tractors', 'dumpers', 'trucks', 'vans', 'km', 'evac']:
            return f'images/trucks_{sub}'
        return 'images/trucks_tractors'
    elif category.startswith('special'):
        return 'images/special'
    return 'images/misc'