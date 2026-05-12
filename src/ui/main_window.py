"""
Ventana principal con pestañas - VERSIÓN CORREGIDA Y MEJORADA
Integra barra de progreso, estado de cola y actualización de clips recientes.
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
    """Ventana principal de la aplicación."""

    config_changed = pyqtSignal(dict)
    test_sound_requested = pyqtSignal()
    create_clip_requested = pyqtSignal()
    refresh_recent_clips_requested = pyqtSignal()

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
        self.setFixedSize(550, 650)  # Aumentado un poco para la barra de progreso

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Panel de estado (incluye barra de progreso)
        self.status_frame = StatusFrame()
        main_layout.addWidget(self.status_frame)

        # Pestañas
        self.tabs = QTabWidget()
        self.obs_tab = OBSConfigTab()
        self.hotkey_tab = HotkeyConfigTab()
        self.clip_tab = ClipConfigTab()
        self.audio_tab = AudioConfigTab()
        self.recent_tab = RecentClipsTab()

        self.tabs.addTab(self.obs_tab, "OBS")
        self.tabs.addTab(self.hotkey_tab, "Hotkey")
        self.tabs.addTab(self.clip_tab, "Clips")
        self.tabs.addTab(self.audio_tab, "Audio")
        self.tabs.addTab(self.recent_tab, "Clips recientes")

        main_layout.addWidget(self.tabs)

        # Botones de acción
        self.action_buttons = ActionButtons()
        main_layout.addWidget(self.action_buttons)

        self.setStatusBar(QStatusBar())

    def connect_signals(self):
        # Señales de la UI hacia el controlador
        self.action_buttons.create_clip_clicked.connect(self.create_clip_requested.emit)
        self.action_buttons.test_sound_clicked.connect(self.test_sound_requested.emit)
        self.action_buttons.hide_to_tray_clicked.connect(self.hide)

        # Cambios en pestañas de configuración
        self.obs_tab.config_changed.connect(self._on_config_changed)
        self.hotkey_tab.config_changed.connect(self._on_config_changed)
        self.clip_tab.config_changed.connect(self._on_config_changed)
        self.audio_tab.config_changed.connect(self._on_config_changed)

        # Refresco de clips recientes
        self.recent_tab.refresh_requested.connect(self.refresh_recent_clips_requested.emit)

        # Señal de nuevo clip guardado (para actualizar automáticamente)
        if hasattr(self.controller, 'clip_saved'):
            self.controller.clip_saved.connect(self._on_clip_saved)

        # Conectar señales de progreso del orquestador (a través del controlador)
        if hasattr(self.controller, 'orchestrator') and self.controller.orchestrator:
            self.controller.orchestrator.progress_signal.connect(self._on_clip_progress)
            self.controller.orchestrator.error_signal.connect(self._on_clip_error)

    def setup_timers(self):
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(1000)

    def update_status(self):
        """Actualiza el tamaño de la cola cada segundo."""
        if hasattr(self.controller, 'get_queue_size'):
            queue_size = self.controller.get_queue_size()
            self.status_frame.update_queue_status(queue_size)
            # Si la cola está vacía y el progress bar no está al 100%, resetearlo gradualmente
            if queue_size == 0 and self.status_frame.progress_bar.value() not in (0, 100):
                # Opcional: resetear después de un breve retardo
                pass

    def _on_config_changed(self, config_data: dict):
        """Reúne toda la configuración de todas las pestañas y la emite."""
        full_config = {}
        full_config.update(self.obs_tab.get_config_data())
        full_config.update(self.hotkey_tab.get_config_data())
        full_config.update(self.clip_tab.get_config_data())
        full_config.update(self.audio_tab.get_config_data())
        self.config_changed.emit(full_config)

    def _on_clip_saved(self, clip_info):
        """Cuando se guarda un clip, refrescar la lista de recientes."""
        self.refresh_recent_clips_requested.emit()

    def _on_clip_progress(self, message: str, percent: int):
        """Actualiza la barra de progreso y el mensaje desde el orquestador."""
        self.status_frame.update_clip_progress(message, percent)
        # Si el clip se completó (percent >= 100), mostrar notificación en la bandeja
        if percent >= 100:
            self.tray_manager.show_info("Clip completado", message)

    def _on_clip_error(self, error_msg: str):
        """Muestra el error en la barra de estado y en la bandeja."""
        self.statusBar().showMessage(f"Error: {error_msg}", 5000)
        self.tray_manager.show_error("Error en clip", error_msg[:100])

    def load_config(self, config):
        """Carga la configuración en todas las pestañas."""
        self.obs_tab.load_config(config.obs)
        self.hotkey_tab.load_config(config.hotkey)
        self.clip_tab.load_config(config.clip)
        self.audio_tab.load_config(config.audio)
        logger.info("UI", "load_config", "Configuración cargada en UI")

    def update_app_state(self, state_name: str):
        """Actualiza el estado general de la app en el frame."""
        self.status_frame.update_app_state(state_name)
        tooltip = f"OBS Clip Manager - Estado: {state_name}"
        self.tray_manager.set_tooltip(tooltip)

        # Habilitar/deshabilitar botón de crear clip
        can_create = (state_name == "CONNECTED" and
                      hasattr(self.controller, 'obs_manager') and
                      self.controller.obs_manager and
                      hasattr(self.controller.obs_manager.status, 'is_streaming') and
                      self.controller.obs_manager.status.is_streaming)
        self.action_buttons.set_create_clip_enabled(can_create)

    def update_obs_status(self, status: dict):
        """Actualiza los indicadores de OBS en el frame de estado."""
        self.status_frame.update_obs_status(status)
        self.tray_manager.update_status(
            status.get('connected', False),
            status.get('is_streaming', False)
        )

    def update_recent_clips(self, clips: list):
        """Actualiza la pestaña de clips recientes con la lista proporcionada."""
        self.recent_tab.update_recent_clips(clips)

    def closeEvent(self, event):
        """Sobrescribe el evento de cierre para llamar al apagado controlado."""
        self.close_application()
        event.accept()

    def close_application(self):
        """Cierra la aplicación de forma ordenada."""
        logger.info("UI", "close", "Cerrando aplicación desde UI")
        self.controller.shutdown()