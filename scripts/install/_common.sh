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

# Встроенные бинарники gps-sdr-sim в git часто без +x; pip/wheel тоже не всегда сохраняют режим.
ensure_bundled_binaries_executable() {
	repo="$1"
	bin="$repo/src/gps_sim/bin"
	for name in gps-sdr-sim-debian-arm64 gps-sdr-sim-macos-apple; do
		f="$bin/$name"
		if [ -f "$f" ]; then
			chmod +x "$f" || true
			echo "Права на исполнение для встроенного бинарника: $f"
		fi
	done
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
	ensure_bundled_binaries_executable "$repo"
}

render_desktop_template() {
	template="$1"
	out="$2"
	exec_path="$3"
	sed "s|@@EXEC_GPS_SIM_UI@@|$exec_path|g" "$template" >"$out"
}
