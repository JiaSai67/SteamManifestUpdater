import re
import os

files = [
    'src/main.py',
    'src/ui/one_click_install_ui.py',
    'src/ui/lua_tools_ui.py'
]

def replace_colors(content):
    if 'from ui.theme_utils import get_state_color' not in content:
        # For main.py, it's not in ui package, so import differs
        # wait, src is in sys.path when running main.py. So `from ui.theme_utils` works.
        content = re.sub(r'(import sys\n)', r'\1from ui.theme_utils import get_state_color\n', content)
        if 'import sys' not in content:
            content = 'from ui.theme_utils import get_state_color\n' + content
            
    # Success
    content = re.sub(r'setStyleSheet\("color:\s*(?:#00CC6A|#4CAF50)\s*;?\s*"?\)', r'setStyleSheet(f"color: {get_state_color(\'success\')};")', content)
    content = re.sub(r'setStyleSheet\("color:\s*(?:#00CC6A|#4CAF50)\s*;\s*font-weight:\s*bold\s*;?\s*"?\)', r'setStyleSheet(f"color: {get_state_color(\'success\')}; font-weight: bold;")', content)

    # Error
    content = re.sub(r'setStyleSheet\("color:\s*(?:#FF5C5C|#F44336)\s*;?\s*"?\)', r'setStyleSheet(f"color: {get_state_color(\'error\')};")', content)
    content = re.sub(r'setStyleSheet\("color:\s*(?:#FF5C5C|#F44336)\s*;\s*font-weight:\s*bold\s*;?\s*"?\)', r'setStyleSheet(f"color: {get_state_color(\'error\')}; font-weight: bold;")', content)

    # Warning
    content = re.sub(r'setStyleSheet\("color:\s*(?:#FFB900)\s*;?\s*"?\)', r'setStyleSheet(f"color: {get_state_color(\'warning\')};")', content)

    # Muted
    content = re.sub(r'setStyleSheet\("color:\s*(?:#999|#999999)\s*;?\s*"?\)', r'setStyleSheet(f"color: {get_state_color(\'muted\')};")', content)

    # Accent (purple)
    content = re.sub(r'setStyleSheet\("color:\s*#a855f7;\s*border:\s*1px\s*solid\s*#a855f7(.*?)?"?\)', r'setStyleSheet(f"color: {get_state_color(\'accent\')}; border: 1px solid {get_state_color(\'accent\')}\1")', content)

    return content

for path in files:
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()
    new_content = replace_colors(content)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
print('Colors updated successfully')
