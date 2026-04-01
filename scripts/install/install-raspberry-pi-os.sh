#!/bin/sh
# Установка gps-sim на Raspberry Pi OS (64-bit, aarch64): venv, pip, ярлык и автозапуск UI.
# Запуск: ./scripts/install/install-raspberry-pi-os.sh

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
	echo "Ожидался apt." >&2
	exit 1
fi

ensure_venv_and_install "$REPO" "[dev,ui]"

EXEC_UI=$(exec_gps_sim_ui_unix "$REPO")
T_DESKTOP="$REPO/docs/templates/gps-sim-ui.desktop.template"
T_AUTOSTART="$REPO/docs/templates/gps-sim-ui-autostart.desktop.template"

APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
mkdir -p "$APP_DIR" "$AUTOSTART_DIR"

if [ -f "$T_DESKTOP" ]; then
	render_desktop_template "$T_DESKTOP" "$APP_DIR/gps-sim-ui.desktop" "$EXEC_UI"
	chmod 644 "$APP_DIR/gps-sim-ui.desktop"
	echo "Создан ярлык меню: $APP_DIR/gps-sim-ui.desktop"
fi

if [ -f "$T_AUTOSTART" ]; then
	render_desktop_template "$T_AUTOSTART" "$AUTOSTART_DIR/gps-sim-ui.desktop" "$EXEC_UI"
	chmod 644 "$AUTOSTART_DIR/gps-sim-ui.desktop"
	echo "Создан автозапуск: $AUTOSTART_DIR/gps-sim-ui.desktop"
fi

update-desktop-database "$APP_DIR" 2>/dev/null || true

echo ""
echo "Консоль (после: cd \"$REPO\" && source .venv/bin/activate): gps-sim, gps-sim-run, gps-sim-ui"
echo "Отключить автозапуск: удалите или переименуйте $AUTOSTART_DIR/gps-sim-ui.desktop"
