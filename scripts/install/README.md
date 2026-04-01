# Скрипты установки

Запускайте из **корня клонированного репозитория** (где лежит `pyproject.toml`).

| Скрипт | Платформа |
|--------|-----------|
| `install-macos.sh` | macOS (Apple Silicon и Intel с Python 3) |
| `install-ubuntu.sh` | Ubuntu / Debian с `apt` |
| `install-raspberry-pi-os.sh` | Raspberry Pi OS 64-bit |
| `install-windows.ps1` | Windows (PowerShell) |

Переменная окружения **`REPO_ROOT`** задаёт каталог проекта, если скрипт вызывают не из стандартного расположения.

Скрипты создают `.venv`, выполняют `pip install -e ".[dev,ui]"` и при необходимости копируют шаблоны из `docs/templates/` (ярлыки, автозапуск на Pi).
