# -*- coding: utf-8 -*-
"""
scripts/auto_fixer.py — Безопасный авто-правщик кода Марфы.
Использует RouterAI (DeepSeek) для генерации патча.
Применяет патч, запускает тесты. Если тесты упали — откатывает бэкап.
Запуск: venv\\Scripts\\python.exe scripts\\auto_fixer.py --file core/agent.py --error "NameError: name 'math' is not defined"
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    sys.exit("Ошибка: pip install openai")

# Настройки RouterAI
API_KEY = os.environ.get("ROUTERAI_API_KEY")
BASE_URL = "https://routerai.ru/api/v1"
MODEL = "deepseek/deepseek-v4.1-flash" # Актуальная модель DeepSeek V3

def get_fix_from_ai(file_path, error_log, code_content):
    if not API_KEY:
        print("❌ Ошибка: Не задана переменная окружения ROUTERAI_API_KEY")
        print("Введите в CMD: set ROUTERAI_API_KEY=ваш_ключ")
        return None

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    
    prompt = f"""
Ты — эксперт по Python. В файле `{file_path}` произошла ошибка.
Вот лог ошибки:
{error_log}

Вот текущий код файла:
{code_content}

Напиши ТОЛЬКО исправленный код файла целиком, без markdown-тегов и пояснений.
Не добавляй комментарии типа "вот исправленный код". Просто выдай готовый Python-код.
Если ошибка не в этом файле, верни исходный код без изменений.
"""
    print(f"🤖 Спрашиваю RouterAI ({MODEL})...")
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"❌ Ошибка API: {e}")
        return None

def apply_fix(file_path, new_code):
    file_path = Path(file_path)
    backup_path = file_path.with_suffix(file_path.suffix + ".bak")
    
    # 1. Делаем бэкап
    shutil.copy(file_path, backup_path)
    print(f"💾 Бэкап создан: {backup_path.name}")

    # Очистка от markdown-тегов, если ИИ их добавил
    clean_code = new_code.strip()
    if clean_code.startswith("```python"):
        clean_code = clean_code[9:]
    if clean_code.startswith("```"):
        clean_code = clean_code[3:]
    if clean_code.endswith("```"):
        clean_code = clean_code[:-3]
    clean_code = clean_code.strip() + "\n"

    try:
        # 2. Записываем новый код
        file_path.write_text(clean_code, encoding="utf-8")
        print("✍️  Код обновлен. Запускаю тесты...")

        # 3. Запускаем тесты (МАРФА-ТЕСТЫ)
        venv_python = Path("venv/Scripts/python.exe")
        if not venv_python.exists():
            venv_python = Path("venv/bin/python") # Для Linux/Mac
            
        result = subprocess.run(
            [str(venv_python), "-m", "pytest", "tests/", "-q"],
            capture_output=True, text=True
        )
        
        if result.returncode == 0:
            print("✅ Все тесты пройдены! Код успешно обновлен.")
            os.remove(backup_path)
            return True
        else:
            print("❌ Тесты упали! Откатываю изменения.")
            print(result.stdout[-500:]) # Показываем хвост ошибки
            shutil.move(backup_path, file_path)
            print("🔄 Откат выполнен. Файл в исходном состоянии.")
            return False

    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        if backup_path.exists():
            shutil.move(backup_path, file_path)
            print("🔄 Откат выполнен.")
        return False

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Путь к файлу (например, core/agent.py)")
    parser.add_argument("--error", required=True, help="Текст ошибки из лога")
    args = parser.parse_args()

    file_path = Path(args.file)
    if not file_path.exists():
        sys.exit(f"Файл {file_path} не найден.")

    code_content = file_path.read_text(encoding="utf-8")
    
    fixed_code = get_fix_from_ai(str(file_path), args.error, code_content)
    if fixed_code:
        success = apply_fix(file_path, fixed_code)
        if success:
            print("\n🎉 Готово! Можете перезапускать Марфу.")
        else:
            print("\n⚠️ ИИ не смог исправить так, чтобы прошли тесты. Нужен ручной разбор.")

if __name__ == "__main__":
    main()