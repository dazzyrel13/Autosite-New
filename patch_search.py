import os

path = r'd:\Chaos\alfa0_9_1\Host\Autosite\routes\main.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

new_lines = []
found_is_new = False
found_filter_data = False

for line in lines:
    if not found_is_new and 'if is_new: query = query.filter(Vehicle.mileage == 0)' in line:
        new_lines.append(line)
        # Handle the case where the if is not at the start
        if line.lstrip().startswith('if'):
            indent = line[:line.find('if')]
            new_lines.append(f"\n{indent}engine_from = request.args.get('engine_from', type=float)\n")
            new_lines.append(f"{indent}if engine_from: query = query.filter(Vehicle.engine_vol >= engine_from)\n")
            new_lines.append(f"\n{indent}body_type = request.args.get('body_type')\n")
            new_lines.append(f"{indent}if body_type: query = query.filter(Vehicle.body_type == body_type)\n")
            found_is_new = True
        else:
            new_lines.append(line)
    elif not found_filter_data and "'mileage_to': mileage_to or ''," in line:
        new_lines.append(line)
        indent = line[:line.find("'mileage_to'")]
        new_lines.append(f"{indent}'engine_from': engine_from or '',\n")
        new_lines.append(f"{indent}'body_type': body_type or '',\n")
        found_filter_data = True
    else:
        new_lines.append(line)

if found_is_new and found_filter_data:
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    print("Successfully patched main.py")
else:
    print(f"Failed to find all targets: found_is_new={found_is_new}, found_filter_data={found_filter_data}")
