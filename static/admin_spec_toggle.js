/**
 * Admin Spec Toggle
 * Автоматически показывает/скрывает поля характеристик
 * в зависимости от выбранной категории.
 */

// Поля для каждой группы (по id input-элемента)
const CAR_FIELDS = ['sc_drive', 'sc_transmission', 'sc_fuel', 'sc_color', 'sc_body'];
const TRUCK_FIELDS = ['st_wheel', 'st_capacity', 'st_eco', 'st_gearbox', 'st_cabin'];
const SPEC_FIELDS = ['ss_type', 'ss_lift', 'ss_load', 'ss_chassis', 'ss_drive'];
const ALL_SPEC_FIELDS = [...CAR_FIELDS, ...TRUCK_FIELDS, ...SPEC_FIELDS];

function getFieldRow(fieldId) {
    const input = document.getElementById(fieldId);
    if (!input) return null;
    // Flask-Admin оборачивает каждое поле в div.form-group
    return input.closest('.form-group') || input.closest('tr');
}

function hideAll() {
    ALL_SPEC_FIELDS.forEach(id => {
        const row = getFieldRow(id);
        if (row) row.style.display = 'none';
    });
}

function showGroup(fields, groupLabel) {
    hideAll();

    // Добавим заголовок группы, если ещё не добавлен
    const firstRow = getFieldRow(fields[0]);
    if (firstRow && !firstRow.previousSibling?.classList?.contains('spec-group-header')) {
        const header = document.createElement('div');
        header.className = 'spec-group-header form-group';
        header.innerHTML = `<div class="col-md-offset-2 col-md-10">
            <h4 style="color:#e63946; border-bottom:1px solid rgba(230,57,70,0.3); 
                       padding-bottom:10px; margin:20px 0 10px;">
                ✦ ${groupLabel}
            </h4>
        </div>`;
        firstRow.parentNode.insertBefore(header, firstRow);
    }

    fields.forEach(id => {
        const row = getFieldRow(id);
        if (row) row.style.display = '';
    });
}

function updateVisibility(categoryValue) {
    if (!categoryValue) { hideAll(); return; }

    if (categoryValue.startsWith('cars')) {
        showGroup(CAR_FIELDS, 'Характеристики легкового автомобиля');
    } else if (categoryValue.startsWith('trucks')) {
        showGroup(TRUCK_FIELDS, 'Характеристики грузового автомобиля');
    } else if (categoryValue.startsWith('special')) {
        showGroup(SPEC_FIELDS, 'Характеристики спецтехники');
    } else {
        hideAll();
    }
}

document.addEventListener('DOMContentLoaded', function () {
    const catSelect = document.getElementById('category');
    if (!catSelect) return;

    // Инициализация при загрузке страницы
    hideAll();
    updateVisibility(catSelect.value);

    // Обновление при смене категории
    catSelect.addEventListener('change', function () {
        updateVisibility(this.value);
    });
});
// Глобальная функция для переключения фиксации цены (через AJAX)
function adminToggleFixed(id, isChecked) {
    let formData = new FormData();
    formData.append('id', id);
    formData.append('field', 'is_currency_fixed');
    formData.append('value', isChecked);

    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

    fetch('/admin/update_price', {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken
        },
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            if (!data.success) {
                alert('Ошибка при сохранении: ' + data.error);
            }
        })
        .catch(err => {
            console.error('Ошибка сети:', err);
        });
}
