# Скрипты установки

Запускайте из **корня клонированного репозитория** (где лежит `pyproject.toml`).

| Скрипт | Платформа |
|--------|-----------|
| `install-macos.sh` | macOS (Apple Silicon и Intel с Python 3) |
| `install-ubuntu.sh` | Ubuntu / Debian с `apt` |
| `install-raspberry-pi-os.sh` | Raspberry Pi OS 64-bit |
| `install-windows.ps1` | Windows (PowerShell) |

Переменная окружения **`REPO_ROOT`** задаёт каталог проекта, если скрипт вызывают не из стандартного расположения.

Скрипты создают `.venv`, выполняют `pip install -e ".[dev,ui]"` и копируют шаблоны из `scripts/install/templates/`: на Linux (Ubuntu, Raspberry Pi OS) — пункт в меню приложений **и** ярлык на рабочем столе (`chmod +x`, при наличии — `gio set … trusted`).

Отдельно: **`linux-qtwebengine-runtime-deps.sh`** — только `apt install` системных библиотек для Qt WebEngine (Chromium) на Debian / Ubuntu / Raspberry Pi OS; запуск с `sudo` (если `gps-sim-ui` ругается на WebEngine).
