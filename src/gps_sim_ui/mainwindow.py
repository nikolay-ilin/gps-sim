"""Главное окно: карта (Leaflet) и запуск симуляции."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QThread, QTimer
from PySide6.QtGui import QCloseEvent, QShowEvent, QTextCursor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from gps_sim.brdc_download import parse_ephemeris_updated_at
from gps_sim.run_sim import _bundled_gps_sdr_sim_path, _is_executable_file
from gps_sim.settings import broadcast_ephemeris_file, load_settings, save_settings
from gps_sim_ui.brdc_thread import BrdcFetchThread
from gps_sim_ui.bridge import MapBridge
from gps_sim_ui.elevation_thread import ElevationFetchThread
from gps_sim_ui.worker import SimulationWorker

MAP_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
        integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
        crossorigin=""/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
          integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo="
          crossorigin=""></script>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
  <style>
    html, body {{ margin: 0; height: 100%; }}
    #map {{ height: 100%; width: 100%; }}
  </style>
</head>
<body>
  <div id="map"></div>
  <script>
    var mapClickBlocked = false;
    var map = L.map('map').setView([{lat}, {lng}], {zoom});
    var mapAttr =
      'Спутник: Esri, Maxar &mdash; '
      'административные подписи: Esri, Garmin, OSM &mdash; '
      'заведения и организации (POI): © OpenStreetMap, © CARTO';
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{ maxZoom: 19, attribution: mapAttr }}
    ).addTo(map);
    L.tileLayer(
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}',
      {{ maxZoom: 19, opacity: 1, attribution: '' }}
    ).addTo(map);
    L.tileLayer(
      'https://{{s}}.basemaps.cartocdn.com/rastertiles/voyager/{{z}}/{{x}}/{{y}}.png',
      {{
        subdomains: 'abcd',
        maxZoom: 19,
        opacity: 0.38,
        attribution: '',
      }}
    ).addTo(map);
    var marker = L.marker([{lat}, {lng}]).addTo(map);
    window.__setMapClickBlocked = function(blocked) {{
      mapClickBlocked = !!blocked;
    }};
    window.__flyToSelection = function(lat, lng) {{
      var z = map.getZoom();
      map.setView([lat, lng], z);
      marker.setLatLng([lat, lng]);
    }};
    new QWebChannel(qt.webChannelTransport, function(channel) {{
      var bridge = channel.objects.bridge;
      map.on('click', function(e) {{
        if (mapClickBlocked) return;
        mapClickBlocked = true;
        var la = e.latlng.lat;
        var ln = e.latlng.lng;
        marker.setLatLng([la, ln]);
        bridge.reportClick(la, ln);
      }});
    }});
  </script>
</body>
</html>
"""


def needs_manual_gps_sdr_sim_path(cfg: dict[str, Any]) -> bool:
    """Нужен ли явный путь к бинарнику (нет встроенного бинарника для ОС и PATH)."""
    if _bundled_gps_sdr_sim_path() is not None:
        return False
    raw = cfg.get("gps_sdr_sim_path")
    if raw:
        p = Path(str(raw)).expanduser().resolve()
        if _is_executable_file(p):
            return False
    if shutil.which("gps-sdr-sim"):
        return False
    return True


def pick_gps_sdr_sim_path_if_needed(parent: QWidget | None) -> bool:
    """Возвращает False, если пользователь отменил выбор при неизвестном gps-sdr-sim."""
    cfg = load_settings()
    if not needs_manual_gps_sdr_sim_path(cfg):
        return True
    path, _ = QFileDialog.getOpenFileName(
        parent,
        "Выберите исполняемый файл gps-sdr-sim",
        str(Path.home()),
    )
    if not path:
        return False
    p = Path(path).expanduser().resolve()
    if not _is_executable_file(p):
        QMessageBox.warning(parent, "gps-sdr-sim", "Файл не найден или не исполняемый.")
        return False
    cfg["gps_sdr_sim_path"] = str(p)
    save_settings(cfg)
    return True


def _default_lat_lng(cfg: dict[str, Any]) -> tuple[float, float]:
    lat = cfg.get("lat")
    lng = cfg.get("lng")
    try:
        if lat is not None and lng is not None:
            return float(lat), float(lng)
    except (TypeError, ValueError):
        pass
    return 55.751244, 37.618423


def _has_saved_coordinates(cfg: dict[str, Any]) -> bool:
    lat = cfg.get("lat")
    lng = cfg.get("lng")
    if lat is None or lng is None:
        return False
    try:
        float(lat)
        float(lng)
    except (TypeError, ValueError):
        return False
    return True


def _hint_text_coords_elevation(lat: float, lng: float, elev_m: float) -> str:
    return f"{lat:.6f}, {lng:.6f}\nвысота: {elev_m:.2f} м"


def _short_filename(name: str, max_len: int = 26) -> str:
    if len(name) <= max_len:
        return name
    return name[: max_len - 1] + "…"


def _format_broadcast_elapsed(seconds: float) -> str:
    """Длительность: чч:мм:сс при >= 1 ч, иначе мм:сс."""
    total = int(max(0, seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


_ACTION_BTN_STYLE_IDLE = (
    "QPushButton { background-color: #2e7d32; color: #ffffff; border: none; "
    "border-radius: 6px; padding: 10px 20px; font-weight: 600; }"
    "QPushButton:disabled { background-color: #81c784; color: #e8f5e9; }"
)
_ACTION_BTN_STYLE_PREP = (
    "QPushButton { background-color: #ef6c00; color: #ffffff; border: none; "
    "border-radius: 6px; padding: 10px 20px; font-weight: 600; }"
)
# Явные семейства: generic «monospace» в Qt даёт поиск несуществующего «Monospace» на macOS.
_ACTION_BTN_STYLE_TX = (
    "QPushButton { background-color: #c62828; color: #ffffff; border: none; "
    "border-radius: 6px; padding: 10px 20px; font-weight: 600; "
    "font-family: 'Menlo', 'Consolas', 'DejaVu Sans Mono', 'Courier New'; }"
)

# Фон как у панели бара (palette(window)); скругление требует непустого стиля кнопки.
_EPHEM_BTN_STYLE = (
    "QPushButton {"
    "  border-radius: 4px;"
    "  padding: 6px 10px;"
    "  text-align: left;"
    "  background-color: palette(window);"
    "  color: #ffffff;"
    "  border: none;"
    "  outline: none;"
    "}"
    "QPushButton:hover {"
    "  background-color: palette(light);"
    "  color: #ffffff;"
    "}"
    "QPushButton:pressed { background-color: palette(mid); }"
    "QPushButton:disabled {"
    "  background-color: palette(window);"
    "  color: #9e9e9e;"
    "}"
)


def _safe_wait_thread(thread: QThread | None, ms: int) -> None:
    """Ожидание QThread без обращения к уже удалённому QObject (deleteLater)."""
    if thread is None:
        return
    try:
        if thread.isRunning():
            thread.wait(ms)
    except RuntimeError:
        pass


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("GPS Simulation")
        self.resize(900, 700)

        self._cfg = load_settings()
        self._lat, self._lng = _default_lat_lng(self._cfg)
        self._pending_lat: float | None = None
        self._pending_lng: float | None = None
        if _has_saved_coordinates(self._cfg):
            self._pending_lat = self._lat
            self._pending_lng = self._lng
        self._worker: SimulationWorker | None = None
        self._elev_thread: ElevationFetchThread | None = None
        self._brdc_thread: BrdcFetchThread | None = None
        self._brdc_user_initiated = False
        self._brdc_startup_scheduled = False
        self._fetch_seq = 0
        self._tx_start_monotonic: float | None = None
        self._broadcast_elapsed_timer: QTimer | None = None
        self._show_logs_panel = bool(self._cfg.get("ui_show_logs_panel", False))

        self._view = QWebEngineView()
        s = self._view.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        self._bridge = MapBridge(self)
        self._bridge.pointClicked.connect(self._on_map_click)
        channel = QWebChannel(self)
        channel.registerObject("bridge", self._bridge)
        self._view.page().setWebChannel(channel)

        html = MAP_HTML.format(lat=self._lat, lng=self._lng, zoom=13)
        self._view.setHtml(html)

        self._action_btn = QPushButton("Запуск")
        sh = self._action_btn.sizeHint()
        self._action_btn.setMinimumSize(max(96, sh.width() * 2), max(36, sh.height() * 2))
        self._apply_action_button_style_idle()
        self._action_btn.clicked.connect(self._on_action)

        self._ephem_btn = QPushButton()
        self._ephem_btn.setStyleSheet(_EPHEM_BTN_STYLE)
        self._ephem_btn.setMinimumWidth(200)
        self._ephem_btn.setToolTip("Обновить файл broadcast-эфемерид BRDC с CDDIS (принудительно)")
        self._ephem_btn.clicked.connect(self._on_ephem_clicked)
        self._refresh_ephem_button()

        self._hint_label = QLabel()
        self._hint_label.setWordWrap(True)

        self._recenter_btn = QPushButton("⌖")
        self._recenter_btn.setToolTip("Перейти к выбранным координатам")
        self._recenter_btn.setFixedWidth(36)
        self._recenter_btn.clicked.connect(self._on_recenter_map)

        self._refresh_hint_initial()

        bar = QHBoxLayout()
        bar.addWidget(self._recenter_btn)
        bar.addWidget(self._hint_label, stretch=1)
        actions = QHBoxLayout()
        actions.setSpacing(0)
        actions.addWidget(self._action_btn)
        actions.addSpacing(12)
        actions.addWidget(self._ephem_btn)
        actions.addSpacing(8)
        self._toggle_logs_btn = QPushButton()
        self._toggle_logs_btn.setFixedWidth(32)
        self._toggle_logs_btn.setToolTip("Показать или скрыть панель журнала")
        self._toggle_logs_btn.clicked.connect(self._on_toggle_logs_panel)
        actions.addWidget(self._toggle_logs_btn)
        bar.addLayout(actions)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Здесь появится журнал запуска симуляции…")
        self._log.setMinimumWidth(200)

        self._bar_wrap = QWidget()
        bar_l = QVBoxLayout(self._bar_wrap)
        bar_l.setContentsMargins(8, 4, 8, 4)
        bar_l.addLayout(bar)

        self._left_panel = QWidget()
        left_lay = QVBoxLayout(self._left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(self._view, stretch=1)
        left_lay.addWidget(self._bar_wrap)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._left_panel, stretch=1)
        root.addWidget(self._log, stretch=1)
        self.setCentralWidget(central)

        self._apply_logs_panel_visibility()

    def _apply_logs_panel_visibility(self) -> None:
        self._log.setVisible(self._show_logs_panel)
        self._toggle_logs_btn.setText("<" if self._show_logs_panel else ">")
        self._toggle_logs_btn.setToolTip(
            "Скрыть панель журнала" if self._show_logs_panel else "Показать панель журнала справа",
        )

    def _on_toggle_logs_panel(self) -> None:
        self._show_logs_panel = not self._show_logs_panel
        cfg = load_settings()
        cfg["ui_show_logs_panel"] = self._show_logs_panel
        save_settings(cfg)
        self._cfg = cfg
        self._apply_logs_panel_visibility()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._brdc_startup_scheduled:
            return
        self._brdc_startup_scheduled = True
        QTimer.singleShot(0, self._schedule_startup_brdc)

    def _has_nasa_credentials(self) -> bool:
        cfg = load_settings()
        return bool((cfg.get("nasa_login") or "").strip() and (cfg.get("nasa_pass") or "").strip())

    def _sync_start_button_enabled(self) -> None:
        """Кнопка Start: только при выбранной точке и без запроса высоты / обновления BRDC."""
        if self._worker is not None and self._worker.isRunning():
            return
        brdc_busy = self._brdc_thread is not None and self._brdc_thread.isRunning()
        elev_busy = self._elev_thread is not None and self._elev_thread.isRunning()
        pending_ok = self._pending_lat is not None and self._pending_lng is not None
        self._action_btn.setEnabled(pending_ok and not brdc_busy and not elev_busy)

    def _apply_action_button_style_idle(self) -> None:
        self._action_btn.setStyleSheet(_ACTION_BTN_STYLE_IDLE)

    def _apply_action_button_style_prep(self) -> None:
        self._action_btn.setStyleSheet(_ACTION_BTN_STYLE_PREP)

    def _apply_action_button_style_tx(self) -> None:
        self._action_btn.setStyleSheet(_ACTION_BTN_STYLE_TX)

    def _tick_broadcast_elapsed(self) -> None:
        if self._tx_start_monotonic is None:
            return
        elapsed = time.monotonic() - self._tx_start_monotonic
        self._action_btn.setText(_format_broadcast_elapsed(elapsed))

    def _on_transmission_started(self) -> None:
        self._set_map_click_blocked(True)
        self._apply_action_button_style_tx()
        self._tx_start_monotonic = time.monotonic()
        if self._broadcast_elapsed_timer is None:
            self._broadcast_elapsed_timer = QTimer(self)
            self._broadcast_elapsed_timer.setInterval(1000)
            self._broadcast_elapsed_timer.timeout.connect(self._tick_broadcast_elapsed)
        self._broadcast_elapsed_timer.start()
        self._tick_broadcast_elapsed()

    def _stop_broadcast_elapsed_timer(self) -> None:
        self._tx_start_monotonic = None
        if self._broadcast_elapsed_timer is not None:
            self._broadcast_elapsed_timer.stop()

    def _refresh_ephem_button(self) -> None:
        busy_worker = self._worker is not None and self._worker.isRunning()
        busy_brdc = self._brdc_thread is not None and self._brdc_thread.isRunning()
        if busy_brdc:
            self._ephem_btn.setText("Обновление...")
            self._ephem_btn.setEnabled(
                self._has_nasa_credentials() and not busy_worker and not busy_brdc,
            )
            self._sync_start_button_enabled()
            return

        cfg = load_settings()
        self._cfg = cfg
        p = broadcast_ephemeris_file(cfg)
        if p is None or not p.is_file():
            text = "Нет файла BRDC\nнажмите для загрузки"
        else:
            nm = _short_filename(p.name)
            dt = parse_ephemeris_updated_at(cfg)
            if dt is None:
                sub = "время обновления неизвестно"
            else:
                local = dt.astimezone()
                sub = f"{local.strftime('%Y-%m-%d %H:%M')}"
            text = f"{nm}\n{sub}"
        self._ephem_btn.setText(text)
        self._ephem_btn.setEnabled(
            self._has_nasa_credentials() and not busy_worker and not busy_brdc,
        )
        self._sync_start_button_enabled()

    def _schedule_startup_brdc(self) -> None:
        if not self._has_nasa_credentials():
            return
        self._brdc_user_initiated = False
        self._start_brdc_thread(force_update=False)

    def _on_ephem_clicked(self) -> None:
        if not self._has_nasa_credentials():
            QMessageBox.information(
                self,
                "Эфемериды BRDC",
                "Укажите логин и пароль NASA Earthdata в настройках.",
            )
            return
        self._brdc_user_initiated = True
        self._start_brdc_thread(force_update=True)

    def _start_brdc_thread(self, force_update: bool) -> None:
        if self._brdc_thread is not None and self._brdc_thread.isRunning():
            return
        self._ephem_btn.setText("Обновление...")
        self._ephem_btn.setEnabled(False)
        t = BrdcFetchThread(force_update)
        self._brdc_thread = t
        t.log_line.connect(self._append_log)
        t.failed.connect(self._on_brdc_failed)
        t.finished.connect(self._on_brdc_thread_finished)
        t.start()
        self._sync_start_button_enabled()

    def _on_brdc_failed(self, msg: str) -> None:
        self._append_log(f"[BRDC] Ошибка: {msg}\n")
        if self._brdc_user_initiated:
            QMessageBox.warning(self, "Эфемериды BRDC", msg)

    def _on_brdc_thread_finished(self) -> None:
        self._brdc_thread = None
        self._cfg = load_settings()
        self._refresh_ephem_button()

    def _set_map_click_blocked(self, blocked: bool) -> None:
        """Синхронизация с JS: разрешить/запретить следующий клик по карте."""
        b = "true" if blocked else "false"
        self._view.page().runJavaScript(
            f"if (typeof window.__setMapClickBlocked === 'function') "
            f"{{ window.__setMapClickBlocked({b}); }}",
        )

    def _on_elev_fetch_finished(self, t: ElevationFetchThread) -> None:
        if t.request_seq != self._fetch_seq:
            return
        self._set_map_click_blocked(False)

    def _clear_elev_thread_ref(self, t: ElevationFetchThread) -> None:
        if self._elev_thread is t:
            self._elev_thread = None

    def _update_recenter_button_state(self) -> None:
        ok = self._pending_lat is not None and self._pending_lng is not None
        self._recenter_btn.setEnabled(ok)

    def _on_recenter_map(self) -> None:
        if self._pending_lat is None or self._pending_lng is None:
            return
        la, ln = self._pending_lat, self._pending_lng
        self._view.page().runJavaScript(
            "if (typeof window.__flyToSelection === 'function') { "
            f"window.__flyToSelection({la}, {ln}); "
            "}",
        )

    def _refresh_hint_initial(self) -> None:
        cfg = self._cfg
        if not _has_saved_coordinates(cfg):
            self._hint_label.setText("Нажми на карту для выбора точки")
        else:
            lat = float(cfg["lat"])
            lng = float(cfg["lng"])
            em = cfg.get("elevation_m")
            if em is not None:
                self._hint_label.setText(_hint_text_coords_elevation(lat, lng, float(em)))
            else:
                self._hint_label.setText(f"{lat:.6f}, {lng:.6f}\nвысота: —")
        self._update_recenter_button_state()

    def _on_map_click(self, lat: float, lng: float) -> None:
        self._pending_lat = lat
        self._pending_lng = lng
        self._update_recenter_button_state()
        self._fetch_seq += 1
        seq = self._fetch_seq

        self._hint_label.setText(f"{lat:.6f}, {lng:.6f}\nопределение высоты...")
        self._append_log(f"[высота] выбор точки #{seq}: {lat:.6f}, {lng:.6f}\n")

        if self._worker is None or not self._worker.isRunning():
            self._action_btn.setText("Start")

        t = ElevationFetchThread(lat, lng, seq)
        self._elev_thread = t
        t.log_line.connect(self._append_log)

        def on_ready(la: float, ln: float, elev: float) -> None:
            if seq != self._fetch_seq:
                return
            self._cfg = load_settings()
            self._lat, self._lng = la, ln
            self._hint_label.setText(_hint_text_coords_elevation(la, ln, elev))
            if self._worker is None or not self._worker.isRunning():
                self._sync_start_button_enabled()

        def on_fail(msg: str) -> None:
            if seq != self._fetch_seq:
                return
            self._hint_label.setText(f"{lat:.6f}, {lng:.6f}\nошибка высоты: {msg}")
            if self._worker is None or not self._worker.isRunning():
                self._sync_start_button_enabled()
            short = msg if len(msg) <= 500 else msg[:500] + "…"
            QMessageBox.warning(
                self,
                "Высота",
                f"Не удалось получить высоту по выбранной точке:\n{short}",
            )

        t.elevation_ready.connect(on_ready)
        t.failed.connect(on_fail)
        t.finished.connect(lambda tt=t: self._on_elev_fetch_finished(tt))
        t.finished.connect(lambda tt=t: self._clear_elev_thread_ref(tt))
        t.finished.connect(t.deleteLater)
        try:
            t.start()
        except Exception:
            self._set_map_click_blocked(False)
            raise
        self._sync_start_button_enabled()

    def _on_action(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            return
        if self._pending_lat is None or self._pending_lng is None:
            return

        self._log.clear()
        self._action_btn.setText("Stop")
        self._apply_action_button_style_prep()
        self._action_btn.setEnabled(True)
        self._worker = SimulationWorker(self._pending_lat, self._pending_lng)
        self._worker.log_line.connect(self._append_log)
        self._worker.transmission_started.connect(self._on_transmission_started)
        self._worker.run_finished.connect(self._on_worker_finished)
        self._worker.start()
        self._refresh_ephem_button()

    def _append_log(self, text: str) -> None:
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(text)
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    def _on_worker_finished(self, _code: int) -> None:
        w = self._worker
        self._worker = None
        if w is not None:
            w.wait()
        self._stop_broadcast_elapsed_timer()
        self._set_map_click_blocked(False)
        self._action_btn.setText("Start")
        self._apply_action_button_style_idle()
        self._cfg = load_settings()
        self._lat, self._lng = _default_lat_lng(self._cfg)
        if self._pending_lat is not None and self._pending_lng is not None:
            em = self._cfg.get("elevation_m")
            if em is not None:
                self._hint_label.setText(
                    _hint_text_coords_elevation(self._pending_lat, self._pending_lng, float(em)),
                )
            else:
                self._refresh_hint_initial()
        else:
            self._refresh_hint_initial()
        self._update_recenter_button_state()
        self._refresh_ephem_button()

    def closeEvent(self, event: QCloseEvent) -> None:
        self._stop_broadcast_elapsed_timer()
        self._set_map_click_blocked(False)
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(300_000)
        self._worker = None
        _safe_wait_thread(self._elev_thread, 5_000)
        self._elev_thread = None
        _safe_wait_thread(self._brdc_thread, 5_000)
        self._brdc_thread = None
        event.accept()
