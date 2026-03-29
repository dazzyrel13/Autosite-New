"""
Service for parsing vehicle data from URLs (Drom, Avito, pricerazdel, etc.)
"""
import requests
from bs4 import BeautifulSoup
import re
import logging
from decimal import Decimal
import json
import uuid
import os
from flask import current_app

logger = logging.getLogger(__name__)

class VehicleParser:
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }

    @staticmethod
    def parse_link(url):
        """Парсит данные об автомобиле по ссылке."""
        try:
            if 'pricerazdel' in url:
                return VehicleParser._parse_pricerazdel(url)

            session = requests.Session()
            response = session.get(url, headers=VehicleParser.HEADERS, timeout=12)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'lxml')
            
            if soup.find(class_='car-card'):
                return VehicleParser._parse_pricerazdel(url, soup)

            data = {
                'brand': '', 'model': '', 'year': None, 'price': 0,
                'mileage': None, 'description': '', 'engine_vol': None,
                'power': None, 'url': url
            }

            # 1. JSON-LD
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    ld = json.loads(script.string)
                    items = ld if isinstance(ld, list) else [ld]
                    for item in items:
                        if item.get('@type') in ['Product', 'Car', 'Vehicle']:
                            data['brand'] = (item.get('brand', {}).get('name') or item.get('name', '').split(' ')[0])
                            data['model'] = item.get('name', '').replace(data['brand'], '').strip()
                            if 'offers' in item:
                                data['price'] = Decimal(str(item['offers'].get('price', 0)))
                except Exception: continue

            # Fallback to OG tags and text if brand is empty
            if not data['brand']:
                og_title = soup.find('meta', property='og:title')
                if og_title:
                    t = og_title['content']
                    y_match = re.search(r'(\d{4})', t)
                    if y_match: data['year'] = int(y_match.group(1))
                    clean_t = re.sub(r'\d{4}', '', t).replace(',', '').strip()
                    parts = clean_t.split(' ', 1)
                    data['brand'] = parts[0]
                    data['model'] = parts[1] if len(parts) > 1 else ''

            return data if data['brand'] else None

        except Exception as e:
            logger.error(f"Error: {e}")
            return None

    @staticmethod
    def _parse_pricerazdel(url, soup=None):
        if not soup:
            try:
                response = requests.get(url, headers=VehicleParser.HEADERS, timeout=10)
                soup = BeautifulSoup(response.text, 'lxml')
            except: return None
        
        card = soup.find(class_='car-card')
        return VehicleParser._extract_card_data(card, url) if card else None

    @staticmethod
    def _extract_card_data(card, base_url):
        try:
            name_text = card.find(class_='car-name').text.strip()
            # "Hyundai Elantra (2021)" -> Brand: Hyundai, Model: Elantra (2021)
            parts = name_text.split(' ', 1)
            brand = parts[0]
            model = parts[1] if len(parts) > 1 else ''
            
            price_text = re.sub(r'\D', '', card.find(class_='car-price').text)
            
            specs = {}
            for spec in card.find_all(class_='spec-item'):
                st = spec.text.lower()
                val_tag = spec.find('span')
                if not val_tag: continue
                val = val_tag.text.strip()
                if 'год' in st: 
                    m = re.search(r'\d+', val)
                    if m: specs['year'] = int(m.group())
                if 'двигатель' in st: 
                    v_match = re.search(r'(\d[.,]\d)', val)
                    if v_match: specs['engine_vol'] = float(v_match.group(1).replace(',', '.'))
                if 'пробег' in st: specs['mileage'] = int(re.sub(r'\D', '', val))
                if 'мощность' in st: 
                    m = re.search(r'\d+', val)
                    if m: specs['power'] = int(m.group())

            img_tag = card.find('img', class_='car-image')
            img_url = img_tag['src'] if img_tag else ''
            if img_url and not img_url.startswith('http'):
                from urllib.parse import urljoin
                img_url = urljoin(base_url, img_url)

            return {
                'brand': brand,
                'model': model,
                'year': specs.get('year'),
                'price': Decimal(price_text) if price_text.isdigit() else 0,
                'mileage': specs.get('mileage'),
                'engine_vol': specs.get('engine_vol'),
                'power': specs.get('power'),
                'description': f"Импортировано с {base_url}",
                'external_image': img_url,
                'category': 'cars_used' # Default for this site
            }
        except Exception as e:
            logger.error(f"Card extraction error: {e}")
            return None

    @staticmethod
    def parse_bulk(url):
        try:
            response = requests.get(url, headers=VehicleParser.HEADERS, timeout=15)
            soup = BeautifulSoup(response.text, 'lxml')
            cards = soup.find_all(class_='car-card')
            results = []
            for card in cards:
                data = VehicleParser._extract_card_data(card, url)
                if data: results.append(data)
            return results
        except Exception as e:
            logger.error(f"Bulk parse error: {e}")
            return []
