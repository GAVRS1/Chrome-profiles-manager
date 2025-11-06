from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QLineEdit, QLabel,
    QCheckBox, QGroupBox, QAbstractItemView, QTabWidget, QFormLayout,
    QSpinBox
)
from PySide6.QtCore import QTimer, QThread, Signal, QObject, Qt
from PySide6.QtGui import QIntValidator
from .profile_manager import ProfileManager, ProfileInfo
from .profile_settings import ProfileSettings
from .chrome_window_manager import ChromeWindowManager, WindowInfo
from .sync_manager import SyncManager
from .ws_hub import WSHub
from typing import List

# ───────── воркеры ─────────

class StopWorker(QObject):
    finished = Signal(str)
    def __init__(self, pm: ProfileManager, name: str) -> None:
        super().__init__()
        self.pm = pm
        self.name = name
    def run(self):
        try:
            self.pm.stop_fast(self.name)
        finally:
            self.finished.emit(self.name)

class StopManyWorker(QObject):
    finished_all = Signal(list)  # список успешно остановленных
    def __init__(self, pm: ProfileManager, names: List[str]) -> None:
        super().__init__()
        self.pm = pm
        self.names = names
    def run(self):
        stopped = []
        for n in self.names:
            try:
                self.pm.stop_fast(n)
                stopped.append(n)
            except Exception:
                pass
        self.finished_all.emit(stopped)

# ───────── основное окно ─────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Chrome Profiles Synchronizer")
        self.pm = ProfileManager()
        self.wm = ChromeWindowManager()
        self._master_profile: str | None = None
        self._sync_enabled = False
        self._hub_running = False
        self._updating_client_list = False

        self.sync = SyncManager(self._get_target_windows)
        self.sync.set_master_provider(self._master_hwnd)

        self.hub = WSHub()

        # UI
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # ---- вкладка профилей ----
        tab_profiles = QWidget()
        tab_profiles_layout = QVBoxLayout(tab_profiles)

        tab_profiles_layout.addWidget(QLabel("Профили"))
        self.list_profiles = QListWidget()
        self.list_profiles.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tab_profiles_layout.addWidget(self.list_profiles)

        row1 = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить")
        self.btn_launch_sel = QPushButton("Запустить выбранные")
        self.btn_stop_sel = QPushButton("Остановить выбранные")
        self.btn_create = QPushButton("Создать")
        self.input_name = QLineEdit(); self.input_name.setPlaceholderText("Имя профиля")
        self.input_count = QSpinBox()
        self.input_count.setRange(1, 999)
        self.input_count.setValue(1)
        self.input_count.setToolTip("Количество профилей для создания")
        self.input_count.setMaximumWidth(80)
        label_count = QLabel("×")
        label_count.setAlignment(Qt.AlignCenter)
        self._label_count = label_count

        row1.addWidget(self.btn_refresh)
        row1.addWidget(self.btn_launch_sel)
        row1.addWidget(self.btn_stop_sel)
        row1.addWidget(self.input_name)
        row1.addWidget(label_count)
        row1.addWidget(self.input_count)
        row1.addWidget(self.btn_create)
        tab_profiles_layout.addLayout(row1)

        settings_group = QGroupBox("Настройки профиля")
        settings_form = QFormLayout(settings_group)
        self.input_start_url = QLineEdit()
        self.input_start_url.setPlaceholderText("https://example.com")
        self.chk_proxy_enabled = QCheckBox("Использовать прокси")
        self.input_proxy_host = QLineEdit()
        self.input_proxy_host.setPlaceholderText("host")
        self.input_proxy_port = QLineEdit()
        self.input_proxy_port.setPlaceholderText("порт")
        self.input_proxy_port.setValidator(QIntValidator(1, 65535, self))
        self.btn_save_settings = QPushButton("Сохранить настройки")

        settings_form.addRow(QLabel("Начальная страница:"), self.input_start_url)
        settings_form.addRow(self.chk_proxy_enabled)
        proxy_row = QHBoxLayout()
        proxy_row.addWidget(self.input_proxy_host)
        proxy_row.addWidget(self.input_proxy_port)
        settings_form.addRow(QLabel("Прокси:"), proxy_row)
        settings_form.addRow(self.btn_save_settings)

        tab_profiles_layout.addWidget(settings_group)

        self.tabs.addTab(tab_profiles, "Профили")

        # ---- вкладка синхронизации ----
        tab_sync = QWidget()
        tab_sync_layout = QVBoxLayout(tab_sync)

        self.chk_server_enabled = QCheckBox("Включить синхронизатор (WS сервер)")
        self.lbl_server_status = QLabel("Сервер выключен")
        tab_sync_layout.addWidget(self.chk_server_enabled)
        tab_sync_layout.addWidget(self.lbl_server_status)

        gb = QGroupBox("Синхронизация ввода (нативная, WinAPI)")
        gbl = QHBoxLayout(gb)
        self.btn_set_master_profile = QPushButton("Назначить Мастером (профиль)")
        self.chk_keyboard = QCheckBox("Клавиатура"); self.chk_keyboard.setChecked(True)
        self.chk_mouse = QCheckBox("Мышь/Колесо"); self.chk_mouse.setChecked(True)
        self.btn_toggle_sync = QPushButton("Включить синхронизацию")
        gbl.addWidget(self.btn_set_master_profile)
        gbl.addWidget(self.chk_keyboard)
        gbl.addWidget(self.chk_mouse)
        gbl.addWidget(self.btn_toggle_sync)
        tab_sync_layout.addWidget(gb)

        tab_sync_layout.addWidget(QLabel("WS-клиенты (расширение)"))
        self.list_clients = QListWidget()
        self.list_clients.setSelectionMode(QAbstractItemView.ExtendedSelection)
        tab_sync_layout.addWidget(self.list_clients)

        row2 = QHBoxLayout()
        self.btn_refresh_clients = QPushButton("Обновить клиентов")
        self.btn_set_master_client = QPushButton("Назначить Мастером (клиент)")
        row2.addWidget(self.btn_refresh_clients)
        row2.addWidget(self.btn_set_master_client)
        tab_sync_layout.addLayout(row2)

        self.tabs.addTab(tab_sync, "Синхронизация")

        # сигналы
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.list_profiles.currentItemChanged.connect(self._on_profile_selection_changed)
        self.btn_refresh.clicked.connect(self._refresh_filesystem)
        self.btn_create.clicked.connect(self._create_profile)
        self.btn_launch_sel.clicked.connect(self._launch_selected_many)
        self.btn_stop_sel.clicked.connect(self._stop_selected_many_async)
        self.btn_set_master_profile.clicked.connect(self._set_master_from_profile_selection)
        self.btn_set_master_client.clicked.connect(self._set_master_from_client_selection)
        self.btn_toggle_sync.clicked.connect(self._toggle_sync)
        self.btn_refresh_clients.clicked.connect(self._rebuild_clients)
        self.btn_save_settings.clicked.connect(self._save_profile_settings)
        self.chk_server_enabled.stateChanged.connect(self._toggle_hub)
        self.chk_proxy_enabled.stateChanged.connect(self._on_proxy_checked)
        self.list_clients.itemChanged.connect(self._on_client_toggled)

        # кэши
        self._cache_profiles: dict[str, tuple[bool, bool]] = {}
        self._winmap: dict[int, WindowInfo] = {}

        self._refresh_filesystem()
        self._tick_i = 0

        self.timer = QTimer()
        self.timer.timeout.connect(self._tick)
        self.timer.start(500)

    # ---------- helpers ----------
    def _selected_profile_names(self) -> List[str]:
        names: List[str] = []
        for it in self.list_profiles.selectedItems():
            n = it.data(32)
            if n:
                names.append(n)
        return names

    def _selected_client_names(self) -> List[str]:
        names: List[str] = []
        for it in self.list_clients.selectedItems():
            n = it.data(32)
            if n:
                names.append(n)
        return names

    def _selected_profile(self) -> str | None:
        it = self.list_profiles.currentItem()
        return None if it is None else it.data(32)

    def _current_profile_info(self) -> ProfileInfo | None:
        name = self._selected_profile()
        if not name:
            return None
        try:
            return self.pm.get(name)
        except KeyError:
            return None

    def _refresh_filesystem(self):
        self.pm.refresh_filesystem()
        self.pm.attach_running_pids()
        self._rebuild_list(force=True)

    def _rebuild_list(self, force: bool=False):
        new_state: dict[str, tuple[bool, bool]] = {}
        for p in self.pm.list():
            running = bool(p.pid)
            is_master = (self._master_profile == p.name)
            new_state[p.name] = (running, is_master)
        if not force and new_state == self._cache_profiles:
            return

        # сохранить множество выбранных для восстановления
        selected = set(self._selected_profile_names())

        self.list_profiles.clear()
        for p in self.pm.list():
            text = f"{'[MASTER] ' if self._master_profile==p.name else ''}{p.name}  —  {'RUNNING' if p.pid else 'STOPPED'}"
            it = QListWidgetItem(text); it.setData(32, p.name)
            self.list_profiles.addItem(it)
            if p.name in selected:
                it.setSelected(True)

        self._cache_profiles = new_state
        self._update_profile_settings_panel()

    def _update_profile_settings_panel(self):
        info = self._current_profile_info()
        enabled = info is not None
        self.input_start_url.setEnabled(enabled)
        self.chk_proxy_enabled.setEnabled(enabled)
        self.input_proxy_host.setEnabled(enabled and self.chk_proxy_enabled.isChecked())
        self.input_proxy_port.setEnabled(enabled and self.chk_proxy_enabled.isChecked())
        self.btn_save_settings.setEnabled(enabled)
        if not enabled:
            self.input_start_url.clear()
            self.chk_proxy_enabled.setChecked(False)
            self.input_proxy_host.clear()
            self.input_proxy_port.clear()
            return

        settings = info.settings
        self.input_start_url.setText(settings.start_url)
        block = self.chk_proxy_enabled.blockSignals(True)
        self.chk_proxy_enabled.setChecked(settings.proxy_enabled)
        self.chk_proxy_enabled.blockSignals(block)
        self.input_proxy_host.setText(settings.proxy_host)
        self.input_proxy_port.setText(str(settings.proxy_port or ""))
        self.input_proxy_host.setEnabled(settings.proxy_enabled)
        self.input_proxy_port.setEnabled(settings.proxy_enabled)

    def _on_profile_selection_changed(self, *_):
        self._update_profile_settings_panel()

    def _on_proxy_checked(self, *_):
        enabled = self.chk_proxy_enabled.isChecked()
        self.input_proxy_host.setEnabled(enabled)
        self.input_proxy_port.setEnabled(enabled)

    def _save_profile_settings(self):
        info = self._current_profile_info()
        if not info:
            QMessageBox.information(self, "Настройки", "Выберите профиль")
            return
        settings = ProfileSettings(
            start_url=self.input_start_url.text().strip(),
            proxy_enabled=self.chk_proxy_enabled.isChecked(),
            proxy_host=self.input_proxy_host.text().strip(),
        )
        if settings.proxy_enabled and not settings.proxy_host:
            QMessageBox.warning(self, "Ошибка", "Укажите адрес прокси сервера")
            return
        port_text = self.input_proxy_port.text().strip()
        if port_text:
            try:
                settings.proxy_port = max(1, min(65535, int(port_text)))
            except ValueError:
                QMessageBox.warning(self, "Ошибка", "Некорректный порт прокси")
                return
        self.pm.update_settings(info.name, settings)
        self.statusBar().showMessage("Настройки профиля сохранены", 4000)
        self._update_profile_settings_panel()

    # ---------- управление хабом ----------
    def _on_tab_changed(self, idx: int):
        if self.tabs.tabText(idx) == "Синхронизация" and self.chk_server_enabled.isChecked():
            self._ensure_hub_running()

    def _toggle_hub(self, state: int):
        if state == Qt.Checked:
            self._ensure_hub_running()
        else:
            self._stop_hub()

    def _ensure_hub_running(self):
        if self._hub_running:
            return
        self.hub.start_background()
        self._hub_running = True
        block = self.chk_server_enabled.blockSignals(True)
        self.chk_server_enabled.setChecked(True)
        self.chk_server_enabled.blockSignals(block)
        self.lbl_server_status.setText("Сервер запущен")
        self.statusBar().showMessage("WS сервер запущен", 4000)
        self._rebuild_clients()

    def _stop_hub(self):
        if not self._hub_running:
            return
        self.sync.disable()
        self._sync_enabled = False
        self.btn_toggle_sync.setText("Включить синхронизацию")
        self.hub.stop_background()
        self._hub_running = False
        self.lbl_server_status.setText("Сервер выключен")
        self.list_clients.clear()
        block = self.chk_server_enabled.blockSignals(True)
        self.chk_server_enabled.setChecked(False)
        self.chk_server_enabled.blockSignals(block)
        self.statusBar().showMessage("WS сервер остановлен", 4000)

    # ---------- действия с профилями ----------
    def _create_profile(self):
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Укажите имя профиля"); return

        count = max(1, int(self.input_count.value()))
        created: list[str] = []
        skipped: list[str] = []

        for idx in range(count):
            candidate = name if count == 1 else f"{name}{idx + 1}"
            try:
                self.pm.create(candidate)
                created.append(candidate)
            except FileExistsError:
                skipped.append(candidate)

        self._rebuild_list(force=True)
        if created:
            if len(created) <= 5:
                msg = "Созданы профили: " + ", ".join(created)
            else:
                sample = ", ".join(created[:5])
                msg = f"Создано профилей: {len(created)} (пример: {sample} …)"
            self.statusBar().showMessage(msg, 6000)
        if skipped:
            QMessageBox.warning(
                self,
                "Внимание",
                "Не удалось создать: " + ", ".join(skipped) + " — уже существуют"
            )

        self.input_name.clear()
        self.input_count.setValue(1)

    def _launch_selected_many(self):
        names = self._selected_profile_names()
        if not names:
            # если ничего не выделено — пробуем один «текущий»
            one = self._selected_profile()
            if one: names = [one]
        if not names:
            QMessageBox.information(self, "Запуск", "Выберите один или несколько профилей")
            return

        launched = []
        for n in names:
            try:
                self.pm.launch(n)
                launched.append(n)
            except Exception as e:
                self.statusBar().showMessage(f"Не удалось запустить '{n}': {e}", 6000)

        self.pm.attach_running_pids()
        self._rebuild_list()
        if launched:
            self.statusBar().showMessage(f"Запущено: {', '.join(launched)}", 6000)

    def _stop_selected_many_async(self):
        names = self._selected_profile_names()
        if not names:
            one = self._selected_profile()
            if one: names = [one]
        if not names:
            QMessageBox.information(self, "Остановка", "Выберите один или несколько профилей")
            return

        # дизейблим кнопки, чтобы избежать повторных кликов
        self.btn_stop_sel.setEnabled(False)

        self._stop_many_thread = QThread(self)
        self._stop_many_worker = StopManyWorker(self.pm, names)
        self._stop_many_worker.moveToThread(self._stop_many_thread)
        self._stop_many_thread.started.connect(self._stop_many_worker.run)
        self._stop_many_worker.finished_all.connect(self._on_stopped_many)
        self._stop_many_worker.finished_all.connect(self._stop_many_thread.quit)
        self._stop_many_worker.finished_all.connect(self._stop_many_worker.deleteLater)
        self._stop_many_thread.finished.connect(self._stop_many_thread.deleteLater)
        self._stop_many_thread.start()

    def _on_stopped_many(self, names: List[str]):
        # если среди них был мастер — снимаем мастера
        if self._master_profile and self._master_profile in names:
            self._master_profile = None
            self.hub.set_master(None)
        self.pm.attach_running_pids()
        self._rebuild_list()
        self.btn_stop_sel.setEnabled(True)
        if names:
            self.statusBar().showMessage(f"Остановлены: {', '.join(names)}", 6000)

    # ---------- мастер по профилю ----------
    def _set_master_from_profile_selection(self):
        # берём первый из выбранных профилей
        names = self._selected_profile_names()
        target = names[0] if names else self._selected_profile()
        if not target:
            QMessageBox.information(self, "Мастер", "Выберите профиль")
            return
        prof = self.pm.get(target)
        if not prof.pid:
            QMessageBox.warning(self, "Ошибка", "Профиль не запущен"); return
        self._master_profile = target
        self.hub.set_master(target)
        self._rebuild_list()
        self.statusBar().showMessage(f"Мастер назначен по профилю: {target}", 6000)

    # ---------- мастер по клиенту (нижний список) ----------
    def _set_master_from_client_selection(self):
        items = self.list_clients.selectedItems()
        if not items:
            QMessageBox.information(self, "Мастер (клиент)", "Выберите клиента в нижнем списке")
            return
        # берём первого выбранного клиента
        client_name = items[0].data(32)
        if not client_name:
            return
        # по запросу: мастер — именно клиент (имя клиента == profile из расширения)
        self._master_profile = client_name
        self.hub.set_master(client_name)
        self._rebuild_list()
        self._rebuild_clients()
        self.statusBar().showMessage(f"Мастер назначен по клиенту: {client_name}", 6000)

    # ---------- синхронизация ----------
    def _toggle_sync(self):
        # чекбоксы управляют флагами, а кнопка включает/выключает хуки
        self.sync.forward_keyboard = self.chk_keyboard.isChecked()
        self.sync.forward_mouse = self.chk_mouse.isChecked()

        if not self._hub_running:
            QMessageBox.warning(self, "Синхронизация", "Включите синхронизатор, чтобы использовать WS клиенты")
        
        if not self._sync_enabled:
            self.sync.enable()
            self._sync_enabled = True
            self.btn_toggle_sync.setText("Выключить синхронизацию")
            self.statusBar().showMessage("Синхронизация включена", 4000)
        else:
            self.sync.disable()
            self._sync_enabled = False
            self.btn_toggle_sync.setText("Включить синхронизацию")
            self.statusBar().showMessage("Синхронизация выключена", 4000)

    # ---------- runtime ----------
    def _tick(self):
        self._tick_i += 1
        if self._tick_i % 4 == 0:
            self.pm.attach_running_pids()
            self._rebuild_list()
        if self._tick_i % 6 == 0:
            pids = [p.pid for p in self.pm.list() if p.pid]
            self._winmap = self.wm.refresh([pid for pid in pids if pid])
        if self._hub_running and self._tick_i % 8 == 0:
            self._rebuild_clients()

    def _rebuild_clients(self):
        if not self._hub_running:
            self.list_clients.clear()
            return
        self._updating_client_list = True
        self.list_clients.clear()
        st = self.hub.list_clients()
        master = self.hub.current_master()
        master_present = False
        for prof, meta in st.items():
            if prof == master:
                master_present = True
            text = f"{'[MASTER] ' if prof==master else ''}{prof}  —  {meta['since']}"
            it = QListWidgetItem(text)
            it.setData(32, prof)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if meta.get("enabled", True) else Qt.Unchecked)
            self.list_clients.addItem(it)
        if master and not master_present:
            self.statusBar().showMessage(
                f"Мастер '{master}' отсутствует среди клиентов WS. Проверьте имя профиля в Options расширения.",
                8000
            )
        self._updating_client_list = False

    def _on_client_toggled(self, item: QListWidgetItem):
        if self._updating_client_list:
            return
        name = item.data(32)
        if not name:
            return
        enabled = item.checkState() == Qt.Checked
        self.hub.set_client_enabled(name, enabled)
        status = "включен" if enabled else "отключен"
        self.statusBar().showMessage(f"Клиент '{name}' {status}", 4000)

    def _master_hwnd(self) -> int | None:
        if not self._master_profile: return None
        try:
            prof = self.pm.get(self._master_profile)
        except KeyError:
            return None
        if not prof.pid: return None
        win = self.wm.get_by_pid(prof.pid)
        return None if not win else win.hwnd

    def _get_target_windows(self) -> list[WindowInfo]:
        return list(self._winmap.values()) if self._winmap else []

    def closeEvent(self, e):
        self._stop_hub()
        super().closeEvent(e)
