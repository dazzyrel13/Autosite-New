"""
Custom widgets for the admin interface.
"""

from wtforms import Field
from markupsafe import Markup
import json


class GalleryWidget(object):
    def __call__(self, field, **kwargs):
        images = field.data or []
        if isinstance(images, str):
            try:
                images = json.loads(images)
            except Exception:
                images = []
        
        html = ['<div id="image-gallery" class="d-flex flex-wrap" style="gap: 15px; margin-bottom: 20px;">']
        from flask import url_for
        for path in images:
            # Игнорируем битые или пустые пути
            if not path: continue
            img_url = url_for('static', filename=path)
            html.append(f'''
                <div class="gallery-item card" data-path="{path}" 
                     style="width: 120px; cursor: grab; position: relative; border: 2px solid rgba(255,255,255,0.1); border-radius: 12px; overflow: hidden; background: #1a0505; user-select: none; -webkit-user-select: none;">
                    <img src="{img_url}" draggable="false" 
                         style="width: 100%; height: 100px; object-fit: cover; pointer-events: none; -webkit-user-drag: none;">
                    <div class="remove-img" onclick="event.stopPropagation(); this.parentElement.remove(); updateGalleryJSON();" 
                         style="position: absolute; top: 4px; right: 4px; background: #e63946; color: white; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; cursor: pointer; font-size: 12px; z-index: 10; border: 2px solid #1a0505;">
                        <i class="fas fa-times"></i>
                    </div>
                </div>
            ''')
        html.append('</div>')
        html.append(f'<input type="hidden" id="gallery-data" name="{field.name}" value=\'{json.dumps(images)}\'>')
        html.append('''
            <style>
                .gallery-item.sortable-ghost { opacity: 0.2; }
                .gallery-item.sortable-chosen { border: 2px solid #e63946 !important; }
                .gallery-item.sortable-drag { cursor: grabbing; }
            </style>
            <script>
                (function() {
                    function initSortable() {
                        var el = document.getElementById('image-gallery');
                        if (el && typeof Sortable !== 'undefined') {
                            Sortable.create(el, {
                                animation: 150,
                                ghostClass: 'sortable-ghost',
                                chosenClass: 'sortable-chosen',
                                dragClass: 'sortable-drag',
                                delay: 50,
                                delayOnTouchOnly: true,
                                onEnd: function() {
                                    updateGalleryJSON();
                                }
                            });
                            console.log('SortableJS initialized');
                        } else {
                            setTimeout(initSortable, 100);
                        }
                    }
                    if (document.readyState === 'complete') {
                        initSortable();
                    } else {
                        window.addEventListener('load', initSortable);
                    }
                })();

                function updateGalleryJSON() {
                    var el = document.getElementById('image-gallery');
                    if (!el) return;
                    var items = el.querySelectorAll(".gallery-item");
                    var paths = [];
                    items.forEach(function(item) {
                        paths.push(item.getAttribute("data-path"));
                    });
                    document.getElementById("gallery-data").value = JSON.stringify(paths);
                }
            </script>
        ''')
        return Markup(''.join(html))


class GalleryField(Field):
    widget = GalleryWidget()

    def __init__(self, label=None, validators=None, **kwargs):
        super(GalleryField, self).__init__(label, validators, **kwargs)

    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = json.loads(valuelist[0])
            except Exception:
                self.data = []
        else:
            self.data = []