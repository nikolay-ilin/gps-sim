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
	sudo apt-get install -y \
		libnss3 libnspr4 libatk1.0-0 libdrm2 libgbm1 \
		libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libxkbcommon0 \
		libasound2 libfontconfig1 libfreetype6 libegl1 libopengl0
else
	echo "Ожидался apt (Ubuntu/Debian)." >&2
	exit 1
fi

ensure_venv_and_install "$REPO" "[dev,ui]"

EXEC_UI=$(exec_gps_sim_ui_unix "$REPO")
TEMPLATE="$SCRIPT_DIR/templates/gps-sim-ui.desktop.template"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
mkdir -p "$APP_DIR"
OUT_DESKTOP="$APP_DIR/gps-sim-ui.desktop"

if [ -f "$TEMPLATE" ]; then
	render_desktop_template "$TEMPLATE" "$OUT_DESKTOP" "$EXEC_UI"
	chmod 644 "$OUT_DESKTOP"
	echo "Создан пункт меню приложений: $OUT_DESKTOP"
	DESKTOP_DIR=""
	if command -v xdg-user-dir >/dev/null 2>&1; then
		DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || true)
	fi
	if [ -z "$DESKTOP_DIR" ] || [ ! -d "$DESKTOP_DIR" ]; then
		DESKTOP_DIR="$HOME/Desktop"
	fi
	mkdir -p "$DESKTOP_DIR"
	render_desktop_template "$TEMPLATE" "$DESKTOP_DIR/gps-sim-ui.desktop" "$EXEC_UI"
	chmod +x "$DESKTOP_DIR/gps-sim-ui.desktop"
	if command -v gio >/dev/null 2>&1; then
		gio set "$DESKTOP_DIR/gps-sim-ui.desktop" metadata::trusted true 2>/dev/null || true
	fi
	echo "Создан ярлык на рабочем столе: $DESKTOP_DIR/gps-sim-ui.desktop"
	update-desktop-database "$APP_DIR" 2>/dev/null || true
else
	echo "Шаблон не найден: $TEMPLATE" >&2
fi

echo ""
echo "Консоль (после: cd \"$REPO\" && source .venv/bin/activate): gps-sim, gps-sim-run, gps-sim-ui"
echo "На Ubuntu x86_64 встроенного бинарника gps-sdr-sim в пакете нет — установите gps-sdr-sim в PATH или укажите путь в настройках."
