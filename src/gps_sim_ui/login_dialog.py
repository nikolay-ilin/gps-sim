"""Диалог входа Earthdata (NASA)."""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from gps_sim.brdc_download import verify_earthdata_credentials
from gps_sim.settings import load_settings, save_settings


class _VerifyThread(QThread):
    success = Signal()
    failed = Signal(str)

    def __init__(self, login: str, password: str) -> None:
        super().__init__()
        self._login = login
        self._password = password

    def run(self) -> None:
        try:
            verify_earthdata_credentials(self._login, self._password)
        except Exception as e:
            self.failed.emit(str(e))
        else:
            self.success.emit()


class LoginDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("gps-sim-ui — вход Earthdata")
        self._cfg = load_settings()
        self._verify_thread: _VerifyThread | None = None

        self._login = QLineEdit(self)
        self._login.setPlaceholderText("логин Earthdata / NASA")
        stored_login = (self._cfg.get("nasa_login") or "").strip()
        if stored_login:
            self._login.setText(stored_login)

        self._password = QLineEdit(self)
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("пароль")
        stored_pass = (self._cfg.get("nasa_pass") or "").strip()
        if stored_pass:
            self._password.setText(stored_pass)

        self._status = QLabel("")
        self._status.setWordWrap(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        form = QFormLayout()
        form.addRow("Логин:", self._login)
        form.addRow("Пароль:", self._password)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._status)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        login = self._login.text().strip()
        password = self._password.text()
        if not login or not password:
            QMessageBox.warning(self, "Вход", "Укажите логин и пароль.")
            return

        self._status.setText("Проверка учётных данных…")
        for w in (self._login, self._password):
            w.setEnabled(False)

        self._verify_thread = _VerifyThread(login, password)
        self._verify_thread.success.connect(self._on_verify_ok)
        self._verify_thread.failed.connect(self._on_verify_fail)
        self._verify_thread.finished.connect(self._on_verify_finished)
        self._verify_thread.start()

    def _on_verify_ok(self) -> None:
        cfg = load_settings()
        cfg["nasa_login"] = self._login.text().strip()
        cfg["nasa_pass"] = self._password.text()
        save_settings(cfg)
        self.accept()

    def _on_verify_fail(self, message: str) -> None:
        QMessageBox.critical(
            self,
            "Ошибка проверки",
            "Не удалось подтвердить учётные данные Earthdata.\n\n" + message,
        )

    def _on_verify_finished(self) -> None:
        self._status.setText("")
        for w in (self._login, self._password):
            w.setEnabled(True)
        self._verify_thread = None
