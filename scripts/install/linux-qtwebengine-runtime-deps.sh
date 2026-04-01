#!/bin/sh
# Системные библиотеки для Qt WebEngine (Chromium) на Debian / Ubuntu / Raspberry Pi OS.
# Запуск: sudo ./scripts/install/linux-qtwebengine-runtime-deps.sh

set -eu

if [ "$(id -u)" -ne 0 ]; then
	echo "Запустите с sudo." >&2
	exit 1
fi

apt-get update
apt-get install -y \
	libnss3 \
	libnspr4 \
	libatk1.0-0 \
	libdrm2 \
	libgbm1 \
	libxcomposite1 \
	libxdamage1 \
	libxfixes3 \
	libxrandr2 \
	libxkbcommon0 \
	libasound2 \
	libfontconfig1 \
	libfreetype6 \
	libegl1 \
	libopengl0

echo "Готово. Перезапустите терминал и снова: pip install -U 'gps-sim[ui]'"
