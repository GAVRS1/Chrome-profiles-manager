from __future__ import annotations
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QLineEdit, QLabel,
    QCheckBox, QGroupBox, QAbstractItemView
)
from PySide6.QtCore import QTimer, QThread, Signal, QObject
from .profile_manager import ProfileManager, ProfileInfo
from .chrome_window_manager import ChromeWindowManager, WindowInfo
from .sync_manager import SyncManager
from .ws_hub import WSHub
import threading
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

        self.sync = SyncManager(self._get_target_windows)
        self.sync.set_master_provider(self._master_hwnd)

        self.hub = WSHub()
        # стартуем хаб в отдельном потоке
        self._hub_thread = threading.Thread(target=self.hub.start_sync, daemon=True)
        self._hub_thread.start()

        # UI
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        layout.addWidget(QLabel("Профили"))

        self.list_profiles = QListWidget()
        # мультивыбор профилей
        self.list_profiles.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.list_profiles)

        # ряд управления профилями (пакетные действия)
        row1 = QHBoxLayout()
        self.btn_refresh = QPushButton("Обновить")
        self.btn_launch_sel = QPushButton("Запустить выбранные")
        self.btn_stop_sel = QPushButton("Остановить выбранные")
        self.btn_create = QPushButton("Создать")
        self.input_name = QLineEdit(); self.input_name.setPlaceholderText("Имя профиля")

        row1.addWidget(self.btn_refresh)
        row1.addWidget(self.btn_launch_sel)
        row1.addWidget(self.btn_stop_sel)
        row1.addWidget(self.input_name)
        row1.addWidget(self.btn_create)
        layout.addLayout(row1)

        # блок синхронизации ввода
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
        layout.addWidget(gb)

        # список WS-клиентов
        layout.addWidget(QLabel("WS-клиенты (расширение)"))
        self.list_clients = QListWidget()
        # мультивыбор клиентов (на случай будущих массовых действий)
        self.list_clients.setSelectionMode(QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.list_clients)

        row2 = QHBoxLayout()
        self.btn_refresh_clients = QPushButton("Обновить клиентов")
        self.btn_set_master_client = QPushButton("Назначить Мастером (клиент)")
        row2.addWidget(self.btn_refresh_clients)
        row2.addWidget(self.btn_set_master_client)
        layout.addLayout(row2)

        # сигналы
        self.btn_refresh.clicked.connect(self._refresh_filesystem)
        self.btn_create.clicked.connect(self._create_profile)
        self.btn_launch_sel.clicked.connect(self._launch_selected_many)
        self.btn_stop_sel.clicked.connect(self._stop_selected_many_async)
        self.btn_set_master_profile.clicked.connect(self._set_master_from_profile_selection)
        self.btn_set_master_client.clicked.connect(self._set_master_from_client_selection)
        self.btn_toggle_sync.clicked.connect(self._toggle_sync)
        self.btn_refresh_clients.clicked.connect(self._rebuild_clients)

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

    # ---------- действия с профилями ----------
    def _create_profile(self):
        name = self.input_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Ошибка", "Укажите имя профиля"); return
        try:
            self.pm.create(name)
            self.input_name.clear()
            self._rebuild_list(force=True)
            self.statusBar().showMessage(f"Профиль '{name}' создан", 4000)
        except FileExistsError:
            QMessageBox.warning(self, "Ошибка", f"Профиль '{name}' уже существует")

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
        if self._tick_i % 8 == 0:
            self._rebuild_clients()

    def _rebuild_clients(self):
        self.list_clients.clear()
        st = self.hub.list_clients()
        master = self.hub.current_master()
        master_present = False
        for prof, meta in st.items():
            if prof == master:
                master_present = True
            it = QListWidgetItem(f"{'[MASTER] ' if prof==master else ''}{prof}  —  {meta['since']}")
            it.setData(32, prof)  # имя клиента (совпадает с именем профиля в расширении)
            self.list_clients.addItem(it)
        if master and not master_present:
            self.statusBar().showMessage(
                f"Мастер '{master}' отсутствует среди клиентов WS. Проверьте имя профиля в Options расширения.",
                8000
            )

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
        # здесь можно добавить корректное выключение хаба при необходимости
        super().closeEvent(e)
