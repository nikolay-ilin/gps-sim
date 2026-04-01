"""Главное окно: карта (Leaflet) и запуск симуляции."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from PySide6.QtGui import QCloseEvent, QTextCursor
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

from gps_sim.run_sim import _bundled_gps_sdr_sim_path, _is_executable_file
from gps_sim.settings import load_settings, save_settings
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


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("gps-sim-ui")
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
        self._fetch_seq = 0

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

        self._action_btn = QPushButton("Start")
        self._action_btn.setEnabled(self._pending_lat is not None and self._pending_lng is not None)
        self._action_btn.clicked.connect(self._on_action)

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
        bar.addWidget(self._action_btn)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Здесь появится журнал запуска симуляции…")
        self._log.setMinimumHeight(160)

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view, stretch=1)
        bar_wrap = QWidget()
        bar_l = QVBoxLayout(bar_wrap)
        bar_l.setContentsMargins(8, 4, 8, 4)
        bar_l.addLayout(bar)
        lay.addWidget(bar_wrap)
        lay.addWidget(self._log)
        self.setCentralWidget(central)

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
            self._action_btn.setEnabled(False)

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
                self._action_btn.setEnabled(True)

        def on_fail(msg: str) -> None:
            if seq != self._fetch_seq:
                return
            self._hint_label.setText(f"{lat:.6f}, {lng:.6f}\nошибка высоты: {msg}")
            if self._worker is None or not self._worker.isRunning():
                self._action_btn.setEnabled(True)
            short = msg if len(msg) <= 500 else msg[:500] + "…"
            QMessageBox.warning(
                self,
                "Высота",
                f"Не удалось получить высоту по выбранной точке:\n{short}",
            )

        t.elevation_ready.connect(on_ready)
        t.failed.connect(on_fail)
        t.finished.connect(lambda tt=t: self._on_elev_fetch_finished(tt))
        t.finished.connect(t.deleteLater)
        try:
            t.start()
        except Exception:
            self._set_map_click_blocked(False)
            raise

    def _on_action(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            return
        if self._pending_lat is None or self._pending_lng is None:
            return

        self._log.clear()
        self._action_btn.setText("Stop")
        self._action_btn.setEnabled(True)
        self._worker = SimulationWorker(self._pending_lat, self._pending_lng)
        self._worker.log_line.connect(self._append_log)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _append_log(self, text: str) -> None:
        self._log.moveCursor(QTextCursor.MoveOperation.End)
        self._log.insertPlainText(text)
        self._log.moveCursor(QTextCursor.MoveOperation.End)

    def _on_worker_finished(self, _code: int) -> None:
        self._worker = None
        self._action_btn.setText("Start")
        self._action_btn.setEnabled(self._pending_lat is not None and self._pending_lng is not None)
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

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self._worker.wait(300_000)
        self._worker = None
        if self._elev_thread is not None and self._elev_thread.isRunning():
            self._elev_thread.wait(5_000)
        self._elev_thread = None
        event.accept()
