"""Главное окно: карта (Leaflet) и запуск симуляции."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QEvent, QSize, Qt, QThread, QTimer
from PySide6.QtGui import QCloseEvent, QResizeEvent, QShowEvent, QTextCursor
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gps_sim.brdc_download import parse_ephemeris_updated_at
from gps_sim.history import (
    format_history_entry_label,
    record_transmission,
    remove_history_entry_at_coords,
    sorted_history_entries,
)
from gps_sim.run_sim import (
    _bundled_gps_sdr_sim_path,
    _gps_sdr_sim_debug,
    _is_executable_file,
)
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
    #map-wrap {{ position: relative; height: 100%; width: 100%; }}
    #map {{ height: 100%; width: 100%; }}
    #map-search-wrap {{
      position: absolute;
      z-index: 1000;
      top: 10px;
      left: 50px;
      right: 12px;
      max-width: 420px;
      display: flex;
      gap: 8px;
      align-items: center;
      background: rgba(255, 255, 255, 0.95);
      padding: 8px 10px;
      border-radius: 6px;
      box-shadow: 0 1px 5px rgba(0, 0, 0, 0.35);
    }}
    #map-search-input {{
      flex: 1;
      min-width: 0;
      border: 1px solid #bbb;
      border-radius: 4px;
      padding: 8px 10px;
      font-size: 14px;
    }}
    #map-search-btn {{
      flex-shrink: 0;
      padding: 8px 14px;
      font-size: 14px;
      cursor: pointer;
      border: 1px solid #2e7d32;
      border-radius: 4px;
      background: #2e7d32;
      color: #fff;
      font-weight: 600;
    }}
    #map-search-btn:hover {{ background: #1b5e20; }}
  </style>
</head>
<body>
  <div id="map-wrap">
    <div id="map"></div>
    <div id="map-search-wrap">
      <input type="text" id="map-search-input" placeholder="Поиск места (OpenStreetMap)…"
             autocomplete="off" spellcheck="false"/>
      <button type="button" id="map-search-btn">Найти</button>
    </div>
  </div>
  <script>
    var mapClickBlocked = false;
    var bridge = null;
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
    var searchInput = document.getElementById('map-search-input');
    var searchBtn = document.getElementById('map-search-btn');
    function runSearch() {{
      if (mapClickBlocked) return;
      var q = searchInput.value.trim();
      if (!q) return;
      var url = 'https://nominatim.openstreetmap.org/search?q=' +
        encodeURIComponent(q) + '&format=json&limit=1';
      fetch(url, {{
        method: 'GET',
        headers: {{
          'Accept': 'application/json',
          'Accept-Language': 'ru,en'
        }}
      }})
        .then(function (r) {{ return r.json(); }})
        .then(function (data) {{
          if (!data || !data.length) {{
            alert('Ничего не найдено. Уточните запрос.');
            return;
          }}
          var lat = parseFloat(data[0].lat);
          var lng = parseFloat(data[0].lon);
          if (isNaN(lat) || isNaN(lng)) return;
          mapClickBlocked = true;
          marker.setLatLng([lat, lng]);
          var z = Math.max(map.getZoom(), 14);
          map.setView([lat, lng], z);
          if (bridge) bridge.reportClick(lat, lng);
        }})
        .catch(function () {{
          alert('Не удалось выполнить поиск. Проверьте сеть.');
        }});
    }}
    searchBtn.addEventListener('click', runSearch);
    searchInput.addEventListener('keydown', function (e) {{
      if (e.key === 'Enter') runSearch();
    }});
    window.__setMapClickBlocked = function(blocked) {{
      mapClickBlocked = !!blocked;
    }};
    window.__flyToSelection = function(lat, lng) {{
      var z = map.getZoom();
      map.setView([lat, lng], z);
      marker.setLatLng([lat, lng]);
    }};
    new QWebChannel(qt.webChannelTransport, function(channel) {{
      bridge = channel.objects.bridge;
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
        _gps_sdr_sim_debug("UI: встроенный gps-sdr-sim найден — диалог выбора файла не нужен")
        return False
    raw = cfg.get("gps_sdr_sim_path")
    if raw:
        p = Path(str(raw)).expanduser().resolve()
        if _is_executable_file(p):
            _gps_sdr_sim_debug(f"UI: исполняемый gps_sdr_sim_path в настройках: {p}")
            return False
    if shutil.which("gps-sdr-sim"):
        _gps_sdr_sim_debug("UI: gps-sdr-sim есть в PATH")
        return False
    _gps_sdr_sim_debug(
        "UI: нужен ручной выбор файла (нет встроенного бинарника, нет исполняемого пути в "
        "настройках и нет gps-sdr-sim в PATH)"
    )
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

# Явные цвета: на X11/Fusion фон по умолчанию у виджетов другой, чем на macOS.
_UI_BOTTOM_BAR_BG = "#2e2e2e"
_UI_PANEL_BLACK = "#000000"
_UI_TEXT_ON_DARK = "#e8e8e8"
_UI_TEXT_MUTED = "#9e9e9e"
_UI_BAR_BTN_BG = "#3d3d3d"
_UI_BAR_BTN_HOVER = "#4a4a4a"
_UI_BAR_BTN_PRESSED = "#353535"

# Кнопки эфемерид / координат на тёмно-серой нижней панели (без palette(...)).
_EPHEM_BTN_STYLE = (
    "QPushButton {"
    "  border-radius: 4px;"
    "  padding: 6px 10px;"
    "  text-align: left;"
    f"  background-color: {_UI_BAR_BTN_BG};"
    f"  color: {_UI_TEXT_ON_DARK};"
    "  border: none;"
    "  outline: none;"
    "}"
    "QPushButton:hover {"
    f"  background-color: {_UI_BAR_BTN_HOVER};"
    f"  color: {_UI_TEXT_ON_DARK};"
    "}"
    f"QPushButton:pressed {{ background-color: {_UI_BAR_BTN_PRESSED}; }}"
    "QPushButton:disabled {"
    f"  background-color: {_UI_BOTTOM_BAR_BG};"
    f"  color: {_UI_TEXT_MUTED};"
    "}"
)

# Нижняя полоса под картой.
_BOTTOM_BAR_WRAP_STYLE = f"QWidget#BottomBar {{ background-color: {_UI_BOTTOM_BAR_BG}; }}"

# Мелкие кнопки на нижней панели (⌖, журнал, полный экран).
_BAR_CHROME_BTN_STYLE = (
    f"QPushButton {{ background-color: {_UI_BAR_BTN_BG}; color: {_UI_TEXT_ON_DARK}; "
    "border: none; border-radius: 4px; }"
    f"QPushButton:hover {{ background-color: {_UI_BAR_BTN_HOVER}; }}"
    f"QPushButton:pressed {{ background-color: {_UI_BAR_BTN_PRESSED}; }}"
)

# Журнал и список истории — чёрный фон (одинаково на всех платформах).
_LOG_TEXT_STYLE = (
    f"QTextEdit {{ background-color: {_UI_PANEL_BLACK}; color: {_UI_TEXT_ON_DARK}; "
    "border: none; }"
    "QScrollBar:vertical { background: #1a1a1a; width: 12px; margin: 0; }"
    "QScrollBar::handle:vertical { background: #555555; min-height: 24px; border-radius: 4px; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
)

_HISTORY_LIST_STYLE = (
    f"QListWidget {{ background-color: {_UI_PANEL_BLACK}; color: {_UI_TEXT_ON_DARK}; "
    "border: none; }"
    "QListWidget::item { margin-bottom: 10px; }"
    "QScrollBar:vertical { background: #1a1a1a; width: 12px; margin: 0; }"
    "QScrollBar::handle:vertical { background: #555555; min-height: 24px; border-radius: 4px; }"
    "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
)

_HISTORY_PANEL_STYLE = f"QWidget#HistorySidePanel {{ background-color: {_UI_PANEL_BLACK}; }}"
_HISTORY_TITLE_STYLE = f"color: {_UI_TEXT_ON_DARK}; background: transparent;"


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
        self._first_show_handled = False
        self._fullscreen_persist_enabled = False

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
        self._action_btn.setMinimumHeight(max(36, sh.height() * 2))
        self._action_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._apply_action_button_style_idle()
        self._action_btn.clicked.connect(self._on_action)

        self._ephem_btn = QPushButton()
        self._ephem_btn.setStyleSheet(_EPHEM_BTN_STYLE)
        self._ephem_btn.setMinimumWidth(140)
        self._ephem_btn.setToolTip("Обновить файл broadcast-эфемерид BRDC с CDDIS (принудительно)")
        self._ephem_btn.clicked.connect(self._on_ephem_clicked)
        self._refresh_ephem_button()

        self._location_btn = QPushButton()
        self._location_btn.setStyleSheet(_EPHEM_BTN_STYLE)
        self._location_btn.setFixedWidth(180)
        self._location_btn.setToolTip(
            "Текущая точка; нажмите, чтобы перейти к ней на карте",
        )
        self._location_btn.clicked.connect(self._on_recenter_map)

        self._history_btn = QPushButton()
        self._history_btn.setFixedWidth(36)
        self._history_btn.setStyleSheet(_BAR_CHROME_BTN_STYLE)
        self._history_btn.clicked.connect(self._on_history_btn_clicked)

        self._autostart_btn = QPushButton("⌖")
        self._autostart_btn.setToolTip("Перейти к выбранным координатам")
        self._autostart_btn.setFixedWidth(36)
        self._autostart_btn.setStyleSheet(_BAR_CHROME_BTN_STYLE)
        self._autostart_btn.clicked.connect(self._on_recenter_map)

        self._refresh_hint_initial()

        history_col = QVBoxLayout()
        history_col.setSpacing(4)
        history_col.setContentsMargins(0, 0, 0, 0)
        history_col.addWidget(self._history_btn)
        history_col.addWidget(self._autostart_btn)

        bar = QHBoxLayout()
        bar.addLayout(history_col)
        bar.addWidget(self._location_btn)
        bar.addWidget(self._action_btn, stretch=1)
        bar.addSpacing(12)
        bar.addWidget(self._ephem_btn)
        bar.addSpacing(8)
        self._toggle_logs_btn = QPushButton()
        self._toggle_logs_btn.setFixedWidth(32)
        self._toggle_logs_btn.setToolTip("Показать или скрыть панель журнала")
        self._toggle_logs_btn.clicked.connect(self._on_toggle_logs_panel)

        self._fullscreen_btn = QPushButton()
        self._fullscreen_btn.setFixedWidth(32)
        self._fullscreen_btn.setIconSize(QSize(18, 18))
        self._fullscreen_btn.clicked.connect(self._on_toggle_fullscreen)

        logs_col = QVBoxLayout()
        logs_col.setSpacing(4)
        logs_col.setContentsMargins(0, 0, 0, 0)
        logs_col.addWidget(self._toggle_logs_btn)
        logs_col.addWidget(self._fullscreen_btn)
        bar.addLayout(logs_col)

        self._toggle_logs_btn.setStyleSheet(_BAR_CHROME_BTN_STYLE)
        self._fullscreen_btn.setStyleSheet(_BAR_CHROME_BTN_STYLE)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setPlaceholderText("Здесь появится журнал запуска симуляции…")
        self._log.setMinimumWidth(200)
        self._log.setStyleSheet(_LOG_TEXT_STYLE)

        self._bar_wrap = QWidget()
        self._bar_wrap.setObjectName("BottomBar")
        self._bar_wrap.setStyleSheet(_BOTTOM_BAR_WRAP_STYLE)
        bar_l = QVBoxLayout(self._bar_wrap)
        bar_l.setContentsMargins(8, 4, 8, 4)
        bar_l.addLayout(bar)

        self._history_panel = QWidget()
        self._history_panel.setObjectName("HistorySidePanel")
        self._history_panel.setStyleSheet(_HISTORY_PANEL_STYLE)
        self._history_panel.setVisible(False)
        hist_lay = QVBoxLayout(self._history_panel)
        hist_lay.setContentsMargins(8, 8, 8, 8)
        _hist_title = QLabel("История локаций")
        _hist_title.setStyleSheet(_HISTORY_TITLE_STYLE)
        hist_lay.addWidget(_hist_title)
        self._history_list = QListWidget()
        self._history_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._history_list.setStyleSheet(_HISTORY_LIST_STYLE)
        hist_lay.addWidget(self._history_list, stretch=1)

        self._left_panel = QWidget()
        left_lay = QVBoxLayout(self._left_panel)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.addWidget(self._view, stretch=1)
        left_lay.addWidget(self._bar_wrap)

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._history_panel, 0)
        root.addWidget(self._left_panel, stretch=1)
        root.addWidget(self._log, stretch=1)
        self.setCentralWidget(central)

        self._apply_logs_panel_visibility()
        self._apply_history_panel_button_appearance()
        self._apply_fullscreen_button_appearance()

    def _apply_logs_panel_visibility(self) -> None:
        self._log.setVisible(self._show_logs_panel)
        self._toggle_logs_btn.setText(">" if self._show_logs_panel else "<")
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

    def _apply_history_panel_button_appearance(self) -> None:
        """Как у кнопки журнала: «>» — панель истории открыта, «<» — скрыта."""
        show = self._history_panel.isVisible()
        self._history_btn.setText("<" if show else ">")
        self._history_btn.setToolTip(
            "Скрыть панель истории локаций"
            if show
            else "Показать панель истории локаций слева",
        )

    def _on_history_btn_clicked(self) -> None:
        show = not self._history_panel.isVisible()
        self._history_panel.setVisible(show)
        self._apply_history_panel_button_appearance()
        if show:
            self._populate_history_list()
            self._apply_history_panel_width()

    def _populate_history_list(self) -> None:
        self._history_list.clear()
        trash_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_TrashIcon)
        for entry in sorted_history_entries():
            try:
                lat = float(entry["lat"])
                lng = float(entry["lng"])
                elev = float(entry.get("elevation_m", 0.0))
            except (KeyError, TypeError, ValueError):
                continue
            row = QWidget()
            row_lay = QHBoxLayout(row)
            row_lay.setContentsMargins(2, 2, 2, 2)
            row_lay.setSpacing(4)
            pick_btn = QPushButton(format_history_entry_label(entry))
            pick_btn.setFlat(True)
            pick_btn.setStyleSheet(
                f"QPushButton {{ text-align: left; padding: 4px 2px; border: none; "
                f"background: transparent; color: {_UI_TEXT_ON_DARK}; }}"
                "QPushButton:hover { background: #333333; }"
                "QPushButton:pressed { background: #444444; }"
            )
            pick_btn.clicked.connect(
                lambda _c=False, la=lat, ln=lng, el=elev: self._apply_history_entry(la, ln, el),
            )
            row_lay.addWidget(pick_btn, stretch=1)
            del_btn = QToolButton()
            del_btn.setIcon(trash_icon)
            del_btn.setToolTip("Удалить из истории")
            del_btn.setAutoRaise(True)
            del_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            del_btn.clicked.connect(
                lambda _c=False, la=lat, ln=lng: self._on_history_delete_clicked(la, ln),
            )
            row_lay.addWidget(del_btn, stretch=0)
            item = QListWidgetItem()
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._history_list.addItem(item)
            self._history_list.setItemWidget(item, row)
            item.setSizeHint(row.sizeHint() + QSize(0, 8))

    def _on_history_delete_clicked(self, lat: float, lng: float) -> None:
        remove_history_entry_at_coords(lat, lng)
        self._populate_history_list()

    def _apply_history_entry(self, lat: float, lng: float, elev_m: float) -> None:
        cfg = load_settings()
        cfg["lat"] = lat
        cfg["lng"] = lng
        cfg["elevation_m"] = elev_m
        save_settings(cfg)
        self._cfg = cfg
        self._pending_lat = lat
        self._pending_lng = lng
        self._lat = lat
        self._lng = lng
        self._location_btn.setText(_hint_text_coords_elevation(lat, lng, elev_m))
        self._view.page().runJavaScript(
            "if (typeof window.__flyToSelection === 'function') { "
            f"window.__flyToSelection({lat}, {lng}); "
            "}",
        )
        self._update_autostart_button_state()
        self._sync_start_button_enabled()

    def _apply_history_panel_width(self) -> None:
        if not self._history_panel.isVisible():
            return
        cw = self.centralWidget()
        base = cw.width() if cw is not None else self.width()
        w = max(120, int(base * 0.30))
        self._history_panel.setFixedWidth(w)

    def _is_fullscreen(self) -> bool:
        return bool(self.windowState() & Qt.WindowState.WindowFullScreen)

    def _apply_fullscreen_button_appearance(self) -> None:
        if self._is_fullscreen():
            self._fullscreen_btn.setText("⇲")
            self._fullscreen_btn.setToolTip("Выйти из полного экрана")
        else:
            self._fullscreen_btn.setText("⇱")
            self._fullscreen_btn.setToolTip("Полный экран")

    def _persist_fullscreen_setting(self) -> None:
        if not self._fullscreen_persist_enabled:
            return
        fs = self._is_fullscreen()
        cfg = load_settings()
        if cfg.get("ui_fullscreen") == fs:
            return
        cfg["ui_fullscreen"] = fs
        save_settings(cfg)
        self._cfg = cfg

    def _restore_fullscreen_session(self) -> None:
        self.showFullScreen()
        QTimer.singleShot(0, self._enable_fullscreen_persist)

    def _enable_fullscreen_persist(self) -> None:
        self._fullscreen_persist_enabled = True

    def _on_toggle_fullscreen(self) -> None:
        if self._is_fullscreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._apply_fullscreen_button_appearance()
            self._persist_fullscreen_setting()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._apply_history_panel_width()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._first_show_handled:
            self._first_show_handled = True
            if bool(self._cfg.get("ui_fullscreen", False)):
                QTimer.singleShot(0, self._restore_fullscreen_session)
            else:
                QTimer.singleShot(0, self._enable_fullscreen_persist)
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
        cfg = load_settings()
        rla = cfg.get("lat")
        rln = cfg.get("lng")
        try:
            if rla is not None and rln is not None:
                lat = float(rla)
                lng = float(rln)
            else:
                raise ValueError
        except (TypeError, ValueError):
            lat = self._pending_lat if self._pending_lat is not None else 0.0
            lng = self._pending_lng if self._pending_lng is not None else 0.0
        raw_e = cfg.get("elevation_m")
        try:
            elev = float(raw_e) if raw_e is not None else 0.0
        except (TypeError, ValueError):
            elev = 0.0
        record_transmission(lat, lng, elev)
        if self._history_panel.isVisible():
            self._populate_history_list()

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

    def _update_autostart_button_state(self) -> None:
        ok = self._pending_lat is not None and self._pending_lng is not None
        self._autostart_btn.setEnabled(ok)

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
            self._location_btn.setText("Нажми на карту для выбора точки")
        else:
            lat = float(cfg["lat"])
            lng = float(cfg["lng"])
            em = cfg.get("elevation_m")
            if em is not None:
                self._location_btn.setText(_hint_text_coords_elevation(lat, lng, float(em)))
            else:
                self._location_btn.setText(f"{lat:.6f}, {lng:.6f}\nвысота: —")
        self._update_autostart_button_state()

    def _on_map_click(self, lat: float, lng: float) -> None:
        self._pending_lat = lat
        self._pending_lng = lng
        self._update_autostart_button_state()
        self._fetch_seq += 1
        seq = self._fetch_seq

        self._location_btn.setText(f"{lat:.6f}, {lng:.6f}\nопределение высоты...")
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
            self._location_btn.setText(_hint_text_coords_elevation(la, ln, elev))
            if self._worker is None or not self._worker.isRunning():
                self._sync_start_button_enabled()

        def on_fail(msg: str) -> None:
            if seq != self._fetch_seq:
                return
            self._location_btn.setText(f"{lat:.6f}, {lng:.6f}\nошибка высоты: {msg}")
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
                self._location_btn.setText(
                    _hint_text_coords_elevation(self._pending_lat, self._pending_lng, float(em)),
                )
            else:
                self._refresh_hint_initial()
        else:
            self._refresh_hint_initial()
        self._update_autostart_button_state()
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
