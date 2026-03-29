const CACHE_NAME = 'turbo-dv-v3'; // Инкремент версии для обновления кэша
const STATIC_CACHE = 'turbo-dv-static-v3';
const DYNAMIC_CACHE = 'turbo-dv-dynamic-v2';

const INITIAL_ASSETS = [
  '/',
  '/static/main.css',
  '/static/logo_emblem.webp',
  '/static/hero_car_bg.webp',
  '/static/images/fon.webp',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css',
  'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css'
];

// Установка: Кэшируем основные ресурсы
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      console.log('[SW] Pre-caching static assets');
      return cache.addAll(INITIAL_ASSETS);
    })
  );
  self.skipWaiting();
});

// Активация: Очищаем старые кэши
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys => {
      return Promise.all(
        keys.filter(key => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
            .map(key => caches.delete(key))
      );
    })
  );
  self.clients.claim();
});

// Обработка запросов
self.addEventListener('fetch', event => {
  // Игнорируем POST-запросы, админку и AJAX-поиск
  if (event.request.method !== 'GET' || 
      event.request.url.includes('/admin') || 
      event.request.url.includes('/search_ajax')) return;

  const url = new URL(event.request.url);

  // СТРАТЕГИЯ ДЛЯ СТАТИКИ (Картинки, CSS, JS, Шрифты) - Cache First
  if (url.pathname.startsWith('/static/') || 
      event.request.destination === 'image' ||
      event.request.destination === 'font' ||
      url.hostname.includes('cdn.jsdelivr.net') ||
      url.hostname.includes('fonts.googleapis.com') ||
      url.hostname.includes('fonts.gstatic.com')) {
    
    event.respondWith(
      caches.match(event.request).then(cachedResponse => {
        if (cachedResponse) return cachedResponse;
        
        return fetch(event.request).then(response => {
          if (response.status === 200) {
            const responseClone = response.clone();
            caches.open(STATIC_CACHE).then(cache => cache.put(event.request, responseClone));
          }
          return response;
        });
      })
    );
    return;
  }

  // СТРАТЕГИЯ ДЛЯ СТРАНИЦ (Navigation) - Network First (Всегда свежее, кэш как запаска)
  event.respondWith(
    fetch(event.request).then(response => {
      // Если всё ок, сохраняем/обновляем в динамическом кэше
      if (response.status === 200 && event.request.mode === 'navigate') {
        const responseClone = response.clone();
        caches.open(DYNAMIC_CACHE).then(cache => cache.put(event.request, responseClone));
      }
      return response;
    }).catch(() => {
      // Если сети нет, ищем в кэшах
      return caches.match(event.request).then(cachedResponse => {
        if (cachedResponse) return cachedResponse;
        
        // Окончательный фоллбэк на главную, если страницы совсем нет в кэше
        if (event.request.mode === 'navigate') {
          return caches.match('/');
        }
      });
    })
  );
});
