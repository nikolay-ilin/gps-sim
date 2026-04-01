#!/bin/sh
# Установка gps-sim на Ubuntu (amd64): системные пакеты, venv, pip, ярлык .desktop в меню.
# Запуск: ./scripts/install/install-ubuntu.sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck source=scripts/install/_common.sh
. "$SCRIPT_DIR/_common.sh"

REPO="${REPO_ROOT:-$(repo_root_from_script)}"

echo "Каталог проекта: $REPO"

if command -v apt-get >/dev/null 2>&1; then
	sudo apt-get update
	sudo apt-get install -y python3-venv python3-pip git
	sudo apt-get install -y hackrf || true
else
	echo "Ожидался apt (Ubuntu/Debian)." >&2
	exit 1
fi

ensure_venv_and_install "$REPO" "[dev,ui]"

EXEC_UI=$(exec_gps_sim_ui_unix "$REPO")
TEMPLATE="$REPO/docs/templates/gps-sim-ui.desktop.template"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APP_DIR"
OUT_DESKTOP="$APP_DIR/gps-sim-ui.desktop"

if [ -f "$TEMPLATE" ]; then
	render_desktop_template "$TEMPLATE" "$OUT_DESKTOP" "$EXEC_UI"
	chmod 644 "$OUT_DESKTOP"
	echo "Создан ярлык меню: $OUT_DESKTOP"
	update-desktop-database "$APP_DIR" 2>/dev/null || true
else
	echo "Шаблон не найден: $TEMPLATE" >&2
fi

echo ""
echo "Консоль (после: cd \"$REPO\" && source .venv/bin/activate): gps-sim, gps-sim-run, gps-sim-ui"
echo "На Ubuntu x86_64 встроенного бинарника gps-sdr-sim в пакете нет — установите gps-sdr-sim в PATH или укажите путь в настройках."
