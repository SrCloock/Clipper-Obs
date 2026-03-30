"""
Ventana principal con pestañas - VERSIÓN CORREGIDA
"""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTabWidget, QStatusBar
)
from PyQt6.QtCore import pyqtSignal, QTimer
import logging

from src.ui.ui_components import (
    StatusFrame, OBSConfigTab, HotkeyConfigTab,
    ClipConfigTab, AudioConfigTab, ActionButtons, RecentClipsTab
)
from src.ui.tray_manager import TrayManager
from src.utils.logging_unified import get_logger

logger = get_logger()


class MainWindow(QMainWindow):
    config_changed = pyqtSignal(dict)
    test_sound_requested = pyqtSignal()
    create_clip_requested = pyqtSignal()
    refresh_recent_clips_requested = pyqtSignal()  # Señal para refrescar clips recientes

    def __init__(self, controller):
        super().__init__()
        self.controller = controller

        self.tray_manager = TrayManager(self)
        self.tray_manager.show_window_requested.connect(self.show)
        self.tray_manager.hide_window_requested.connect(self.hide)
        self.tray_manager.quit_requested.connect(self.close_application)
        self.tray_manager.create_clip_requested.connect(self.create_clip_requested.emit)

        self.setup_ui()
        self.connect_signals()
        self.setup_timers()

        self.tray_manager.show()
        logger.info("UI", "init", "✅ Ventana principal creada")

    def setup_ui(self):
        self.setWindowTitle("OBS Clip Manager")
        self.setFixedSize(550, 600)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        self.status_frame = StatusFrame()
        main_layout.addWidget(self.status_frame)

        self.tabs = QTabWidget()
        self.obs_tab = OBSConfigTab()
        self.hotkey_tab = HotkeyConfigTab()  # Versión mejorada con botón de grabación
        self.clip_tab = ClipConfigTab()      # Versión mejorada con timeout y ayuda
        self.audio_tab = AudioConfigTab()
        self.recent_tab = RecentClipsTab()

        self.tabs.addTab(self.obs_tab, "OBS")
        self.tabs.addTab(self.hotkey_tab, "Hotkey")
        self.tabs.addTab(self.clip_tab, "Clips")
        self.tabs.addTab(self.audio_tab, "Audio")
        self.tabs.addTab(self.recent_tab, "Clips recientes")

        main_layout.addWidget(self.tabs)

        self.action_buttons = ActionButtons()
        main_layout.addWidget(self.action_buttons)

        self.setStatusBar(QStatusBar())

    def connect_signals(self):
        self.action_buttons.create_clip_clicked.connect(self.create_clip_requested.emit)
        self.action_buttons.test_sound_clicked.connect(self.test_sound_requested.emit)
        self.action_buttons.hide_to_tray_clicked.connect(self.hide)

        self.obs_tab.config_changed.connect(self._on_config_changed)
        self.hotkey_tab.config_changed.connect(self._on_config_changed)
        self.clip_tab.config_changed.connect(self._on_config_changed)
        self.audio_tab.config_changed.connect(self._on_config_changed)

        # Conectar señal de refresco de la pestaña reciente
        self.recent_tab.refresh_requested.connect(self.refresh_recent_clips_requested.emit)

        # Conectar señal de nuevo clip guardado (para actualizar automáticamente la lista)
        if hasattr(self.controller, 'clip_saved'):
            self.controller.clip_saved.connect(self._on_clip_saved)

    def setup_timers(self):
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(1000)

    def update_status(self):
        if hasattr(self.controller, 'get_queue_size'):
            queue_size = self.controller.get_queue_size()
            self.status_frame.update_queue_status(queue_size)

    def _on_config_changed(self, config_data: dict):
        full_config = {}
        full_config.update(self.obs_tab.get_config_data())
        full_config.update(self.hotkey_tab.get_config_data())
        full_config.update(self.clip_tab.get_config_data())
        full_config.update(self.audio_tab.get_config_data())
        self.config_changed.emit(full_config)

    def _on_clip_saved(self, clip_info):
        """Cuando se guarda un clip, refrescar la lista de recientes."""
        # Emitir señal para que el controlador refresque la pestaña
        self.refresh_recent_clips_requested.emit()

    def load_config(self, config):
        self.obs_tab.load_config(config.obs)
        self.hotkey_tab.load_config(config.hotkey)
        self.clip_tab.load_config(config.clip)
        self.audio_tab.load_config(config.audio)
        logger.info("UI", "load_config", "Configuración cargada en UI")

    def update_app_state(self, state_name: str):
        self.status_frame.update_app_state(state_name)
        tooltip = f"OBS Clip Manager - Estado: {state_name}"
        self.tray_manager.set_tooltip(tooltip)

        can_create = (state_name == "CONNECTED" and
                      hasattr(self.controller, 'obs_manager') and
                      self.controller.obs_manager and
                      hasattr(self.controller.obs_manager.status, 'is_streaming') and
                      self.controller.obs_manager.status.is_streaming)
        self.action_buttons.set_create_clip_enabled(can_create)

    def update_obs_status(self, status: dict):
        self.status_frame.update_obs_status(status)
        self.tray_manager.update_status(
            status.get('connected', False),
            status.get('is_streaming', False)
        )

    def update_recent_clips(self, clips: list):
        """Actualiza la pestaña de clips recientes con la lista proporcionada."""
        self.recent_tab.update_recent_clips(clips)

    def closeEvent(self, event):
        self.close_application()
        event.accept()

    def close_application(self):
        logger.info("UI", "close", "Cerrando aplicación desde UI")
        self.controller.shutdown()