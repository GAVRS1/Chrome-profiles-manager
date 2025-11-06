from pathlib import Path

# Корень проекта: .../chrome-profiles-sync/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Каталог профилей (создаётся автоматически)
PROFILES_ROOT = PROJECT_ROOT / "profiles"
PROFILES_ROOT.mkdir(exist_ok=True)

# Пути к chrome.exe (проверь и при необходимости укажи свой)
CANDIDATE_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

# Базовые аргументы запуска Chrome
CHROME_ARGS_BASE = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-mode",
    "--disable-renderer-backgrounding",
]

# Классы окон Chrome на Windows (актуальны для Win10/11)
# Основной класс:
CHROME_WINDOW_CLASS = "Chrome_WidgetWin_1"

# Резервный список, если нужно перебирать несколько вариантов
CHROME_WINDOW_CLASSES = [
    "Chrome_WidgetWin_1",
    "Chrome_WidgetWin_2",        # встречается у некоторых билдов
]

# Путь к локальному расширению MV3 (если используешь автоподхват --load-extension)
EXTENSION_PATH = PROJECT_ROOT / "extension"
