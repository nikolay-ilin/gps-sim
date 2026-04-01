#!/bin/sh
# Установка gps-sim в виртуальное окружение на macOS и генерация скрипта запуска UI.
# Запуск из корня репозитория: ./scripts/install/install-macos.sh
# Или: sh /path/to/gps-sim/scripts/install/install-macos.sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck source=scripts/install/_common.sh
. "$SCRIPT_DIR/_common.sh"

REPO="${REPO_ROOT:-$(repo_root_from_script)}"
cd "$REPO"

echo "Каталог проекта: $REPO"

if ! command -v python3 >/dev/null 2>&1; then
	echo "Установите Python 3 (https://www.python.org или brew install python)." >&2
	exit 1
fi

ensure_venv_and_install "$REPO" "[dev,ui]"

EXEC_UI=$(exec_gps_sim_ui_unix "$REPO")
TEMPLATE="$REPO/docs/templates/run-gps-sim-ui-macos.sh.template"
OUT_SH="$REPO/run-gps-sim-ui.command"

if [ -f "$TEMPLATE" ]; then
	sed "s|@@EXEC_GPS_SIM_UI@@|$EXEC_UI|g" "$TEMPLATE" >"$OUT_SH"
	chmod +x "$OUT_SH"
	echo "Создан исполняемый файл: $OUT_SH"
	echo "Двойной щелчок по нему в Finder запустит UI (или перетащите в Dock)."
else
	echo "Шаблон не найден: $TEMPLATE" >&2
fi

echo ""
echo "Консольные команды (после: cd \"$REPO\" && source .venv/bin/activate):"
echo "  gps-sim --help"
echo "  gps-sim-run --help"
echo "  gps-sim-ui"
echo ""
if ! command -v hackrf_transfer >/dev/null 2>&1; then
	echo "Для HackRF установите: brew install hackrf"
fi
