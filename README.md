# gps-sim

Инструменты для подготовки настроек и запуска **GPS L1-симуляции** ([gps-sdr-sim](https://github.com/osqzss/gps-sdr-sim)) с выводом в **HackRF One** (`hackrf_transfer`).

## Возможности

- **gps-sim** — координаты, высота (опционально), загрузка broadcast-эфемерид **BRDC** с CDDIS (NASA Earthdata), сохранение настроек; по желанию сразу запуск симуляции. Есть `--force-brdc` для принудительной загрузки без проверки интервала с последнего обновления.
- **gps-sim-run** — только конвейер `gps-sdr-sim → hackrf_transfer` по уже сохранённым настройкам (`--duration`, `--gain`).
- **gps-sim-ui** — графический интерфейс (PySide6): карта **Leaflet** в **Qt WebEngine**, выбор точки, загрузка BRDC, запуск симуляции. При первом запросе может открыться диалог логина Earthdata, если учётные данные ещё не сохранены в настройках.
- Перед вызовом `gps-sdr-sim` время старта **подгоняется к допустимому окну** из RINEX NAV (как в симуляторе). Если текущий UTC-час вне диапазона эфемерид, берётся ближайшая граница; при ошибке чтения файла выводится предупреждение.
- В поставку пакета могут входить встроенные бинарники `gps-sdr-sim` для отдельных платформ; иначе путь задаётся в настройках или ищется в `PATH`.

---

## macOS

### Консольная утилита

**Установка**

1. Установите **Python 3** (с [python.org](https://www.python.org/downloads/macos/) или `brew install python`). В терминале должна быть команда `python3`.
2. Установите инструменты для HackRF (по желанию до первой передачи):

   ```bash
   brew install hackrf
   ```

3. Клонируйте репозиторий и перейдите в его каталог. Создайте виртуальное окружение и установите пакет в режиме разработки **без** графического интерфейса:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -U pip
   pip install -e ".[dev]"
   ```

**Запуск**

```bash
cd /путь/к/gps-sim
source .venv/bin/activate
gps-sim --help
gps-sim-run --help
```

Примеры:

```bash
gps-sim 55.75 37.62
gps-sim-run --duration 30 --gain 20
```

### Приложение с графическим интерфейсом

**Установка**

В том же репозитории с активированным `source .venv/bin/activate`:

```bash
pip install -e ".[dev,ui]"
```

Для UI нужны **PySide6** и **Qt WebEngine** (обычно ставятся колёсами `pip` для macOS).

**Создание ярлыка для запуска**

1. Узнайте полный путь к программе (из корня репозитория):

   ```bash
   python3 -c "import pathlib; print((pathlib.Path('.venv') / 'bin' / 'gps-sim-ui').resolve())"
   ```

2. **Вариант A — скрипт `.command`:** в репозитории есть шаблон `docs/templates/run-gps-sim-ui-macos.sh.template`. Скопируйте его, замените плейсхолдер `@@EXEC_GPS_SIM_UI@@` на путь из шага 1, сохраните файл с расширением `.command`, выполните `chmod +x файл.command`. Двойной щелчок в Finder запустит UI; ярлык можно перетащить в Dock.

3. **Вариант B — Automator:** приложение «Automator» → тип «Программа» → действие «Запустить shell-скрипт», оболочка `/bin/zsh`, в теле одна строка: `exec "/полный/путь/к/.venv/bin/gps-sim-ui"`. Сохраните как `gps-sim-ui.app` в каталог «Программы». При блокировке Gatekeeper разрешите запуск в «Системные настройки → Конфиденциальность и безопасность».

**Автоматическая установка (консоль + UI + скрипт запуска)**

Из корня репозитория:

```bash
chmod +x scripts/install/install-macos.sh
./scripts/install/install-macos.sh
```

Будет создан файл `run-gps-sim-ui.command` в корне проекта с подставленным путём.

---

## Raspberry Pi OS

Ориентир: **64-bit** Raspberry Pi OS на базе Debian (Bookworm), архитектура **aarch64**. Для неё в wheel пакета может поставляться бинарник **`gps-sdr-sim-debian-arm64`**. На **32-bit (armhf)** предсобранного бинарника в пакете нет — соберите `gps-sdr-sim` сами и укажите путь в настройках.

### Консольная утилита

**Установка**

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git hackrf
cd /путь/к/gps-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

**Запуск**

```bash
cd /путь/к/gps-sim
source .venv/bin/activate
gps-sim --help
gps-sim-run --help
```

На платах с 1–2 ГБ ОЗУ консольный режим предпочтительнее тяжёлого UI.

### Приложение с графическим интерфейсом

**Установка**

```bash
cd /путь/к/gps-sim
source .venv/bin/activate
pip install -e ".[dev,ui]"
```

**Создание ярлыка для запуска**

1. Полный путь к `gps-sim-ui`:

   ```bash
   python3 -c "import pathlib; print((pathlib.Path('.venv') / 'bin' / 'gps-sim-ui').resolve())"
   ```

2. Создайте каталог меню приложений и файл ярлыка, подставив путь вместо плейсхолдера. Образец содержимого — файл **`docs/templates/gps-sim-ui.desktop.template`** в репозитории: скопируйте его в `~/.local/share/applications/gps-sim-ui.desktop` и замените строку `Exec=@@EXEC_GPS_SIM_UI@@` на `Exec=/полный/путь/к/.venv/bin/gps-sim-ui`.

3. При необходимости выполните `update-desktop-database ~/.local/share/applications`.

**Автозагрузка графического приложения**

Автозапуск выполняется **после входа пользователя в графическую сессию** (стандарт XDG).

1. Создайте каталог:

   ```bash
   mkdir -p ~/.config/autostart
   ```

2. Поместите туда файл `~/.config/autostart/gps-sim-ui.desktop`. Шаблон: **`docs/templates/gps-sim-ui-autostart.desktop.template`** — скопируйте и подставьте тот же путь в `Exec=`, что и для ярлыка.

3. Чтобы отключить автозапуск, удалите или переименуйте этот `.desktop`.

**Автоматическая установка (apt, venv, ярлык и автозапуск)**

```bash
chmod +x scripts/install/install-raspberry-pi-os.sh
./scripts/install/install-raspberry-pi-os.sh
```

---

## Windows

### Консольная утилита

**Установка**

1. Установите **Python 3** с [python.org](https://www.python.org/downloads/windows/), отметьте **Add python.exe to PATH**.
2. Откройте **cmd** или **PowerShell**, перейдите в каталог с клоном репозитория:

   ```bat
   py -m venv .venv
   .venv\Scripts\activate.bat
   python -m pip install -U pip
   pip install -e ".[dev]"
   ```

3. Утилиты **HackRF** для Windows установите отдельно с сайта производителя или соберите `hackrf_transfer`, чтобы он был в `PATH`.

**Запуск**

```bat
cd C:\путь\к\gps-sim
.venv\Scripts\activate.bat
gps-sim --help
gps-sim-run --help
```

### Приложение с графическим интерфейсом

**Установка**

С активированным venv:

```bat
pip install -e ".[dev,ui]"
```

**Создание ярлыка для запуска**

1. Полный путь к программе проверьте командой:

   ```bat
   python -c "import pathlib; print((pathlib.Path('.venv') / 'Scripts' / 'gps-sim-ui.exe').resolve())"
   ```

2. В проводнике откройте `.venv\Scripts\`, правый щелчок по `gps-sim-ui.exe` → «Отправить» → «Рабочий стол (создать ярлык)».

3. Для создания ярлыка скриптом в репозитории есть **`docs/templates/gps-sim-ui-windows-shortcut.vbs.template`**: скопируйте файл, подставьте в текст пути к `gps-sim-ui.exe` и к каталогу проекта вместо `@@EXEC_GPS_SIM_UI@@` и `@@WORKING_DIR@@`, сохраните как `.vbs` и выполните: `cscript //nologo имя.vbs`.

**Автоматическая установка**

В PowerShell из корня репозитория (при необходимости: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`):

```powershell
.\scripts\install\install-windows.ps1
```

---

## Ubuntu

### Консольная утилита

**Установка**

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip git
sudo apt install -y hackrf
cd /путь/к/gps-sim
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

На **Ubuntu x86_64** встроенного бинарника `gps-sdr-sim` в этом пакете нет — установите [gps-sdr-sim](https://github.com/osqzss/gps-sdr-sim) в систему и убедитесь, что `gps-sdr-sim` в `PATH`, либо укажите полный путь в настройках приложения.

**Запуск**

```bash
cd /путь/к/gps-sim
source .venv/bin/activate
gps-sim --help
gps-sim-run --help
```

### Приложение с графическим интерфейсом

**Установка**

```bash
source .venv/bin/activate
pip install -e ".[dev,ui]"
```

**Создание ярлыка для запуска**

1. Путь к UI:

   ```bash
   python3 -c "import pathlib; print((pathlib.Path('.venv') / 'bin' / 'gps-sim-ui').resolve())"
   ```

2. Файл `~/.local/share/applications/gps-sim-ui.desktop` создайте по образцу **`docs/templates/gps-sim-ui.desktop.template`**: замените `@@EXEC_GPS_SIM_UI@@` на полный путь к `gps-sim-ui` из шага 1.

3. Выполните `update-desktop-database ~/.local/share/applications` при необходимости.

**Автоматическая установка**

```bash
chmod +x scripts/install/install-ubuntu.sh
./scripts/install/install-ubuntu.sh
```

---

## Шаблоны и скрипты установки

В репозитории:

- **`docs/templates/`** — файлы-шаблоны ярлыков и автозапуска с плейсхолдером `@@EXEC_GPS_SIM_UI@@`; описание плейсхолдеров — в `docs/templates/README.md`.
- **`scripts/install/`** — готовые установщики для каждой ОС (venv, `pip install -e ".[dev,ui]"`, копирование шаблонов). Подробности — в `scripts/install/README.md`.

Переменная окружения **`REPO_ROOT`** задаёт каталог проекта, если скрипт запускают не из клона по умолчанию.

---

## Настройки и доступ к CDDIS

Файл настроек и каталог эфемерид создаются при первом использовании (`gps-sim --settings`). Для загрузки BRDC с CDDIS нужны учётные данные [NASA Earthdata](https://urs.earthdata.nasa.gov/) (в UI сохраняются в настройках; в CLI можно использовать `~/.netrc` — см. модуль `brdc_download`).

## Тесты

```bash
pip install -e ".[dev]"
pytest
```
