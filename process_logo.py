import os
from PIL import Image

def process_logo(input_path, output_path):
    print("Открываю исходный логотип...")
    try:
        img = Image.open(input_path).convert("RGBA")
    except Exception as e:
        print(f"Ошибка открытия файла: {e}")
        return

    # 1. Сделать белый (фона) полностью прозрачным
    print("Убираю белый фон...")
    datas = img.getdata()
    new_data = []
    # Цвет логотипа красный. Белый фон обычно (255,255,255)
    # Используем порог > 220 для удаления JPEG артефактов на фоне
    for item in datas:
        # Если пиксель очень светлый (ближе к белому)
        if item[0] > 230 and item[1] > 230 and item[2] > 230:
            new_data.append((255, 255, 255, 0)) # Делаем прозрачным
        else:
            new_data.append(item)
    img.putdata(new_data)

    width, height = img.size

    # Считаем сумму непрозрачности по горизонтальным линиям
    row_alphas = []
    for y in range(height):
        alpha_sum = sum(img.getpixel((x, y))[3] for x in range(width))
        row_alphas.append(alpha_sum)

    # Ищем верхнюю границу логотипа (начало красного круга)
    top = 0
    while top < height and row_alphas[top] < 500:
        top += 1

    # Ищем щель (разрыв) между кругом и нижним текстом TURBO-DV
    gap_row = height
    in_content = False
    for y in range(top, height):
        is_empty = row_alphas[y] < 100  # почту пустая строка

        if not is_empty and not in_content:
            in_content = True  # Мы внутри красного круга

        # Если мы внутри главного контента, опустились ниже 40% картинки и наткнулись на пустую строку
        if is_empty and in_content and y > height * 0.5:
            gap_row = y
            break

    # Обрезаем ширину пустых отступов слева и справа
    left = 0
    while left < width:
        col_alpha = sum(img.getpixel((left, y))[3] for y in range(top, gap_row))
        if col_alpha > 500:
            break
        left += 1

    right = width - 1
    while right > left:
        col_alpha = sum(img.getpixel((right, y))[3] for y in range(top, gap_row))
        if col_alpha > 500:
            break
        right -= 1

    # Добавим небольшой отступ внутрь, чтобы избежать оборванных теней
    margin = 5
    crop_box = (
        max(0, left - margin), 
        max(0, top - margin), 
        min(width, right + margin), 
        min(height, gap_row + margin)
    )

    print(f"Обрезаю текст по координатам: {crop_box}")
    cropped = img.crop(crop_box)

    # Сохраняем в WebP
    cropped.save(output_path, "WEBP", quality=90)
    print(f"Готово! Новый логотип сохранен как: {output_path}")

input_img = r"d:\Chaos\alfa0_9_1\Host\Autosite\static\logo_raw.png"
output_img = r"d:\Chaos\alfa0_9_1\Host\Autosite\static\logo_emblem.webp"
process_logo(input_img, output_img)
