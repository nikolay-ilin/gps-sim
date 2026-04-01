#!/bin/sh
# Общие функции для install-*.sh (источник через . ./_common.sh)

repo_root_from_script() {
	# Скрипт лежит в scripts/install/name.sh → корень репозитория на два уровня выше
	(cd "$(dirname "$0")/../.." && pwd)
}

venv_python() {
	printf '%s\n' "$1/.venv/bin/python3"
}

venv_pip() {
	printf '%s\n' "$1/.venv/bin/pip"
}

exec_gps_sim_ui_unix() {
	printf '%s\n' "$1/.venv/bin/gps-sim-ui"
}

ensure_venv_and_install() {
	repo="$1"
	shift
	extras="$1"

	cd "$repo" || exit 1
	if [ ! -d .venv ]; then
		python3 -m venv .venv || exit 1
	fi
	# shellcheck disable=SC1090
	. .venv/bin/activate
	pip install -U pip
	pip install -e ".$extras" || exit 1
}

render_desktop_template() {
	template="$1"
	out="$2"
	exec_path="$3"
	sed "s|@@EXEC_GPS_SIM_UI@@|$exec_path|g" "$template" >"$out"
}
