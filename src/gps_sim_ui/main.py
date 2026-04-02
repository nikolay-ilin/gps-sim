"""Точка входа gps-sim-ui."""

from __future__ import annotations

import os
import platform
import sys


def _maybe_apply_webengine_linux_arm_gpu_workaround() -> None:
    """
    На Linux ARM (Raspberry Pi и др.) Qt WebEngine/Chromium часто пишет в stderr ошибки
    gbm_wrapper.cc (dma_buf / plane) — неполная поддержка GBM в драйвере.

    До импорта Qt WebEngine задаём флаги Chromium, отключающие GPU-композитинг.
    Переопределение: задать QTWEBENGINE_CHROMIUM_FLAGS до запуска или
    GPS_SIM_WEBENGINE_USE_GPU=1 (не подставлять этот набор флагов).
    """
    if not sys.platform.startswith("linux"):
        return
    if os.environ.get("GPS_SIM_WEBENGINE_USE_GPU", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    if os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS"):
        return
    machine = platform.machine().lower()
    if machine not in ("aarch64", "arm64", "armv7l", "armv8l"):
        return
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = (
        "--disable-gpu --disable-gpu-compositing --disable-accelerated-compositing"
    )


def _webengine_failure_message(exc: BaseException) -> str:
    lines = [
        "Не удалось загрузить Qt WebEngine (PySide6.QtWebEngineWidgets).",
        f"Причина: {exc!r}",
        "",
    ]
    if "No module named" in str(exc) or "cannot import name" in str(exc):
        lines.extend(
            [
                "Похоже, в установленном PySide6 нет модуля WebEngine для этой платформы.",
                "Обновите пакет: pip install -U 'PySide6>=6.5'",
                "",
            ]
        )
    if sys.platform.startswith("linux"):
        lines.extend(
            [
                "На Debian / Raspberry Pi OS движок WebEngine (Chromium) требует "
                "системные библиотеки.",
                "Установите их и перезапустите приложение:",
                "",
                "  sudo apt update",
                "  sudo apt install -y libnss3 libnspr4 libatk1.0-0 libdrm2 libgbm1 \\",
                "    libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libxkbcommon0 \\",
                "    libasound2 libfontconfig1 libfreetype6 libegl1 libopengl0",
                "",
                "Либо из корня репозитория: "
                "sudo ./scripts/install/linux-qtwebengine-runtime-deps.sh",
                "",
                "Затем в venv: pip install -U 'gps-sim[ui]'",
            ]
        )
    else:
        lines.extend(
            [
                "Переустановите зависимости: pip install -U 'gps-sim[ui]'",
            ]
        )
    return "\n".join(lines)


def main() -> int:
    _maybe_apply_webengine_linux_arm_gpu_workaround()
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "Требуется PySide6. Установите: pip install 'gps-sim[ui]'",
            file=sys.stderr,
        )
        return 1

    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
    except ImportError as exc:
        print(_webengine_failure_message(exc), file=sys.stderr)
        return 1

    from gps_sim.settings import load_settings
    from gps_sim_ui.login_dialog import LoginDialog
    from gps_sim_ui.mainwindow import MainWindow, pick_gps_sdr_sim_path_if_needed

    app = QApplication(sys.argv)
    cfg = load_settings()
    has_login = bool((cfg.get("nasa_login") or "").strip() and (cfg.get("nasa_pass") or "").strip())
    if not has_login:
        from PySide6.QtWidgets import QDialog

        login = LoginDialog()
        if login.exec() != QDialog.DialogCode.Accepted:
            return 0
    if not pick_gps_sdr_sim_path_if_needed(None):
        return 0
    w = MainWindow()
    w.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
