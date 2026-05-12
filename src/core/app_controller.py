"""
Controlador principal de la aplicación - VERSIÓN FINAL CON MEJORAS
Integra todos los módulos, maneja señales de progreso, configuración y ciclo de vida.
"""

import logging
import sys
import threading
import time
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QTimer, QMetaObject, Qt
from PyQt6.QtWidgets import QApplication, QMessageBox

from src.utils.logging_unified import get_logger, log_function

from src.config.manager import ConfigManager
from src.obs.connection import OBSConnectionManager
from src.hotkey.manager import HotkeyManager
from src.orchestration.clip_orchestrator import ClipOrchestrator
from src.audio.feedback import AudioFeedbackManager
from src.file_manager.organizer import FileOrganizer
from src.ui.main_window import MainWindow
from src.core.app_state import AppState
from src.utils.retry_manager import RetryManager

logger = logging.getLogger(__name__)
ulog = get_logger()


class ModuleInitializer:
    """Inicializador de módulos con manejo de errores."""

    @staticmethod
    def initialize_audio(config):
        try:
            audio_manager = AudioFeedbackManager(config.audio)
            ulog.info("ModuleInitializer", "initialize_audio", "✅ Módulo de audio inicializado")
            return audio_manager
        except Exception as e:
            ulog.error("ModuleInitializer", "initialize_audio", f"❌ Error inicializando audio: {e}")
            return None

    @staticmethod
    def initialize_obs(config):
        try:
            obs_manager = OBSConnectionManager(config.obs)
            ulog.info("ModuleInitializer", "initialize_obs", "✅ Módulo OBS inicializado")
            return obs_manager
        except Exception as e:
            ulog.error("ModuleInitializer", "initialize_obs", f"❌ Error inicializando OBS: {e}")
            return None

    @staticmethod
    def initialize_hotkey():
        try:
            hotkey_manager = HotkeyManager()
            ulog.info("ModuleInitializer", "initialize_hotkey", "✅ Módulo de hotkeys inicializado")
            return hotkey_manager
        except Exception as e:
            ulog.error("ModuleInitializer", "initialize_hotkey", f"❌ Error inicializando hotkeys: {e}")
            return None

    @staticmethod
    def initialize_file_manager(config):
        try:
            file_manager = FileOrganizer(config.clip)
            ulog.info("ModuleInitializer", "initialize_file_manager", "✅ Módulo de archivos inicializado")
            return file_manager
        except Exception as e:
            ulog.error("ModuleInitializer", "initialize_file_manager", f"❌ Error inicializando gestor de archivos: {e}")
            return None

    @staticmethod
    def initialize_orchestrator(config, obs_manager, audio_manager, file_manager):
        try:
            if obs_manager:
                orchestrator = ClipOrchestrator(
                    config=config.clip,
                    obs_manager=obs_manager,
                    audio_manager=audio_manager,
                    file_manager=file_manager
                )
                ulog.info("ModuleInitializer", "initialize_orchestrator", "✅ Orquestador de clips inicializado")
                return orchestrator
            else:
                ulog.warning("ModuleInitializer", "initialize_orchestrator", "⚠ OBS no disponible, orquestador no inicializado")
                return None
        except Exception as e:
            ulog.error("ModuleInitializer", "initialize_orchestrator", f"❌ Error inicializando orquestador: {e}")
            return None


class ConnectionManager:
    """Gestor de reconexión automática a OBS."""

    def __init__(self, controller):
        self.controller = controller
        self._auto_connect_thread = None
        self._connection_check_interval = 5
        self._retry_manager = RetryManager(max_retries=5, base_delay=2, max_delay=30)
        self._consecutive_failures = 0
        self._last_notification_time = 0
        self._notification_interval = 60

    def start_auto_connect(self):
        if self._auto_connect_thread and self._auto_connect_thread.is_alive():
            return
        self._auto_connect_thread = threading.Thread(
            target=self._auto_connect_worker,
            daemon=True,
            name="AutoConnectWorker"
        )
        self._auto_connect_thread.start()
        ulog.info("ConnectionManager", "start_auto_connect", "Hilo de reconexión automática iniciado")

    def _auto_connect_worker(self):
        while not self.controller.shutting_down:
            try:
                if self.controller.obs_manager:
                    if not self.controller.obs_manager.is_connected():
                        ulog.info("ConnectionManager", "_auto_connect_worker", "🔄 Intentando reconexión automática a OBS")
                        self._retry_manager.reset()
                        success = self._retry_manager.execute_with_retry(
                            self.controller.obs_manager.connect
                        )
                        if success:
                            ulog.info("ConnectionManager", "_auto_connect_worker", "✅ Reconexión exitosa")
                            self._consecutive_failures = 0
                            # Actualizar límite de delay en UI
                            self.controller._update_delay_limit_from_obs()
                        else:
                            ulog.error("ConnectionManager", "_auto_connect_worker", "❌ No se pudo reconectar")
                            self._consecutive_failures += 1
                            if self._consecutive_failures >= 3:
                                current_time = time.time()
                                if current_time - self._last_notification_time > self._notification_interval:
                                    self._last_notification_time = current_time
                                    self.controller.ulog.warning(
                                        "ConnectionManager", "auto_connect",
                                        f"Fallo de conexión persistente ({self._consecutive_failures} intentos)"
                                    )
                                    if self.controller.ui and hasattr(self.controller.ui, 'tray_manager'):
                                        self.controller.ui.tray_manager.show_error(
                                            "Conexión OBS perdida",
                                            f"No se pudo reconectar después de {self._consecutive_failures} intentos.\nVerifica que OBS esté abierto y el WebSocket activo."
                                        )
                            wait = min(30, 2 ** self._consecutive_failures)
                            time.sleep(wait)
                    else:
                        if not self.controller.obs_manager.check_connection():
                            ulog.warning("ConnectionManager", "_auto_connect_worker", "Conexión perdida, actualizando estado")
                time.sleep(self._connection_check_interval)
            except Exception as e:
                ulog.error("ConnectionManager", "_auto_connect_worker", f"Error: {e}")
                time.sleep(self._connection_check_interval)

    def stop(self):
        self._auto_connect_thread = None


class ConfigHandler:
    """Aplica cambios de configuración en caliente."""

    def __init__(self, controller):
        self.controller = controller

    def apply_config_update(self, new_config: dict) -> bool:
        try:
            # Guardar cambios en archivo y recargar configuración
            success = self.controller.config_manager.update(**new_config)
            if not success:
                return False
            self.controller.config = self.controller.config_manager.load()

            # Aplicar cambios a módulos específicos
            self._apply_hotkey_changes(new_config)
            self._apply_audio_changes(new_config)
            self._apply_obs_changes(new_config)
            self._apply_clip_changes(new_config)
            self._apply_file_changes(new_config)

            ulog.info("ConfigHandler", "apply_config_update", "✅ Configuración actualizada y aplicada")
            return True
        except Exception as e:
            ulog.error("ConfigHandler", "apply_config_update", f"❌ Error aplicando configuración: {e}")
            return False

    def _apply_hotkey_changes(self, new_config):
        if 'hotkey' in new_config or 'hotkey_enabled' in new_config:
            if self.controller.hotkey_manager:
                self.controller.hotkey_manager.unregister()
                if (self.controller.config.hotkey.enabled and
                        self.controller.config.hotkey.key_combination):
                    ulog.info("ConfigHandler", "_apply_hotkey_changes",
                              f"🔄 Actualizando hotkey: {self.controller.config.hotkey.key_combination}")
                    self.controller.hotkey_manager.register(
                        self.controller.config.hotkey.key_combination,
                        self.controller.on_hotkey_triggered
                    )

    def _apply_audio_changes(self, new_config):
        if 'volume' in new_config and self.controller.audio_manager:
            self.controller.audio_manager.set_volume(new_config['volume'])
        if 'sound_path' in new_config and self.controller.audio_manager:
            if new_config['sound_path']:
                success = self.controller.audio_manager.load_custom_sound(new_config['sound_path'])
                if not success and self.controller.ui:
                    self.controller.ui.statusBar().showMessage("Sonido personalizado no válido, usando por defecto", 5000)
            else:
                # Si se borró la ruta, recargar sonido por defecto
                self.controller.audio_manager._load_sound_file()

    def _apply_obs_changes(self, new_config):
        obs_changed = any(k in new_config for k in ('host', 'port', 'password'))
        if obs_changed and self.controller.obs_manager:
            ulog.info("ConfigHandler", "_apply_obs_changes", "🔄 Cambios en OBS detectados, reconectando...")
            threading.Thread(
                target=self.controller._reconnect_obs,
                daemon=True,
                name="ObsReconnectThread"
            ).start()

    def _apply_clip_changes(self, new_config):
        if self.controller.orchestrator:
            delay = new_config.get('delay')
            max_queue = new_config.get('max_queue_size')
            file_timeout = new_config.get('file_timeout')
            if delay is not None or max_queue is not None or file_timeout is not None:
                self.controller.orchestrator.update_config(
                    delay=delay,
                    max_queue_size=max_queue,
                    file_timeout=file_timeout
                )
                if delay is not None and self.controller.ui:
                    self.controller._update_delay_limit_ui()

    def _apply_file_changes(self, new_config):
        if self.controller.file_manager:
            output_path = new_config.get('output_path')
            naming_template = new_config.get('naming_template')
            if output_path is not None or naming_template is not None:
                try:
                    self.controller.file_manager.update_config(
                        output_path=output_path,
                        naming_template=naming_template
                    )
                except Exception as e:
                    ulog.error("ConfigHandler", "_apply_file_changes", f"Error actualizando gestor de archivos: {e}")
                    if self.controller.ui and hasattr(self.controller.ui, 'tray_manager'):
                        self.controller.ui.tray_manager.show_error(
                            "Error al cambiar carpeta",
                            f"No se pudo cambiar la carpeta de salida: {e}"
                        )


class ApplicationController(QObject):
    """Controlador principal de la aplicación."""
    state_changed = pyqtSignal(str)
    obs_status_changed = pyqtSignal(dict)
    clip_saved = pyqtSignal(dict)
    initialization_complete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.state = AppState.INIT
        self.initialized = False
        self.shutting_down = False
        self._waiting_for_pending_tasks = False

        self.ulog = get_logger()
        self.config_manager = ConfigManager()
        self.config = None

        self.obs_manager = None
        self.hotkey_manager = None
        self.orchestrator = None
        self.audio_manager = None
        self.file_manager = None
        self.ui = None

        self.module_initializer = ModuleInitializer()
        self.connection_manager = ConnectionManager(self)
        self.config_handler = ConfigHandler(self)

        self.status_refresh_timer = QTimer()
        self.ui_ready = False

        self.initialization_complete.connect(self._on_initialization_complete)

    def initialize(self):
        """Inicia la aplicación: carga config, crea UI, arranca módulos en segundo plano."""
        try:
            self.ulog.info("ApplicationController", "initialize", "Iniciando inicialización")
            self.config = self.config_manager.load()
            self.set_state(AppState.INIT)
            self._create_ui()
            self._start_background_initialization()
        except Exception as e:
            self.ulog.error("ApplicationController", "initialize", f"Error crítico: {e}")
            self.set_state(AppState.ERROR)

    def _create_ui(self):
        try:
            self.ui = MainWindow(self)
            self.ui_ready = True
            self.ui.show()

            self.state_changed.connect(self.ui.update_app_state)
            self.ui.load_config(self.config)

            if hasattr(self.ui, 'create_clip_requested'):
                self.ui.create_clip_requested.connect(self.on_hotkey_triggered)

            if hasattr(self.ui, 'refresh_recent_clips_requested'):
                self.ui.refresh_recent_clips_requested.connect(self._refresh_recent_clips)

            self.ulog.info("ApplicationController", "_create_ui", "UI creada")
        except Exception as e:
            self.ulog.error("ApplicationController", "_create_ui", f"Error creando UI: {e}")
            raise

    def _start_background_initialization(self):
        init_thread = threading.Thread(
            target=self._initialize_modules,
            daemon=True,
            name="ModuleInitThread"
        )
        init_thread.start()

    def _initialize_modules(self):
        """Se ejecuta en hilo secundario. Inicializa módulos pesados."""
        try:
            self.ulog.info("ApplicationController", "_initialize_modules", "Inicializando módulos...")
            self.audio_manager = self.module_initializer.initialize_audio(self.config)
            self.obs_manager = self.module_initializer.initialize_obs(self.config)
            self.hotkey_manager = self.module_initializer.initialize_hotkey()
            self.file_manager = self.module_initializer.initialize_file_manager(self.config)
            self.orchestrator = self.module_initializer.initialize_orchestrator(
                self.config, self.obs_manager, self.audio_manager, self.file_manager
            )
            self._connect_signals()
            self.initialized = True
            self.ulog.info("ApplicationController", "_initialize_modules", "✅ Todos los módulos inicializados")
            self.initialization_complete.emit()
            if self.obs_manager:
                self.connection_manager.start_auto_connect()
        except Exception as e:
            self.ulog.error("ApplicationController", "_initialize_modules", f"Error: {e}")
            self.set_state(AppState.ERROR)

    def _connect_signals(self):
        """Conecta señales entre módulos y UI (puede llamarse desde hilo secundario, pero las conexiones son seguras)."""
        try:
            if self.obs_manager and self.ui_ready:
                self.obs_manager.add_connection_handler(self.on_obs_status_changed)

            if self.ui:
                self.ui.config_changed.connect(self.on_config_changed)
                self.ui.test_sound_requested.connect(self.test_audio)
                self.obs_status_changed.connect(self.ui.update_obs_status)

            if self.file_manager and hasattr(self.file_manager, 'clip_saved'):
                self.file_manager.clip_saved.connect(self.clip_saved)
                self.file_manager.clip_saved.connect(self._on_clip_saved_refresh)

            if self.orchestrator:
                # Conectar señales de progreso (usando Qt.AutoConnection, seguro desde hilos secundarios)
                self.orchestrator.progress_signal.connect(self._on_orchestrator_progress)
                self.orchestrator.error_signal.connect(self._on_orchestrator_error)
                self.orchestrator.task_status_signal.connect(self._on_task_status)
                self.orchestrator.clip_completed.connect(self._on_clip_completed)

        except Exception as e:
            self.ulog.error("ApplicationController", "_connect_signals", f"Error: {e}")

    def _on_initialization_complete(self):
        """Se ejecuta en el hilo principal después de la inicialización."""
        self.ulog.info("ApplicationController", "_on_initialization_complete", "Inicialización completa, UI lista")

        # Registrar hotkey en el hilo principal
        self._register_initial_hotkey()

        # Iniciar timer para refrescar estado del replay buffer (polling de respaldo)
        self.status_refresh_timer.timeout.connect(self._refresh_obs_status)
        self.status_refresh_timer.start(2000)
        self.ulog.info("ApplicationController", "_on_initialization_complete", "Temporizador de refresco iniciado (2s)")

        if self.obs_manager and self.obs_manager.is_connected():
            self.on_obs_status_changed(self.obs_manager.get_status())
            self._update_delay_limit_from_obs()
        else:
            self.set_state(AppState.DISCONNECTED)

        # Cargar clips recientes inicialmente
        self._refresh_recent_clips()

    def _register_initial_hotkey(self):
        if (self.hotkey_manager and
                self.config.hotkey.enabled and
                self.config.hotkey.key_combination):
            try:
                self.hotkey_manager.register(
                    self.config.hotkey.key_combination,
                    self.on_hotkey_triggered
                )
                self.ulog.info("ApplicationController", "_register_initial_hotkey",
                               f"✅ Hotkey registrada: {self.config.hotkey.key_combination}")
            except Exception as e:
                self.ulog.error("ApplicationController", "_register_initial_hotkey", f"Error: {e}")

    # ------------------------------------------------------------------------
    # Estado de la aplicación
    # ------------------------------------------------------------------------

    def set_state(self, new_state: AppState):
        if self.shutting_down:
            return
        old_state = self.state
        self.state = new_state
        self.ulog.info("ApplicationController", "set_state", f"🔄 Estado cambiado: {old_state.name} → {new_state.name}")
        self.state_changed.emit(new_state.name)

    # ------------------------------------------------------------------------
    # Refresco de estado OBS y límite de delay
    # ------------------------------------------------------------------------

    def _refresh_obs_status(self):
        """Llamado por el timer (polling de respaldo para replay buffer)."""
        if self.obs_manager and self.obs_manager.is_connected():
            self.obs_manager.update_replay_status()
        else:
            self.ulog.debug("ApplicationController", "_refresh_obs_status", "OBS no conectado")

    def _update_delay_limit_from_obs(self):
        if not self.obs_manager or not self.obs_manager.is_connected():
            return
        limit = self.obs_manager.get_replay_buffer_duration()
        if limit is not None:
            if self.orchestrator:
                self.orchestrator.max_allowed_delay = limit
                if self.config.clip.delay_seconds > limit:
                    self.ulog.warning("ApplicationController", "_update_delay_limit_from_obs",
                                      f"Delay configurado ({self.config.clip.delay_seconds}s) > límite ({limit}s). Ajustando...")
                    self.config.clip.delay_seconds = limit
                    self.config_manager.save()
                    if self.ui:
                        self.ui.clip_tab.delay_spin.setValue(limit)
            self._update_delay_limit_ui(limit)

    def _update_delay_limit_ui(self, limit: Optional[int] = None):
        if self.ui and hasattr(self.ui, 'clip_tab'):
            if limit is None and self.obs_manager and self.obs_manager.is_connected():
                limit = self.obs_manager.get_replay_buffer_duration()
            self.ui.clip_tab.set_max_delay_limit(limit)

    # ------------------------------------------------------------------------
    # Eventos de hotkey y clip
    # ------------------------------------------------------------------------

    def on_hotkey_triggered(self):
        if not self.initialized or self.shutting_down:
            self.ulog.warning("ApplicationController", "on_hotkey_triggered", "Hotkey ignorada - App no lista")
            return
        if self.state == AppState.CONNECTED:
            if (self.obs_manager and
                    hasattr(self.obs_manager.status, 'is_streaming') and
                    not self.obs_manager.status.is_streaming):
                self.ulog.warning("ApplicationController", "on_hotkey_triggered", "Hotkey ignorada - OBS no está en streaming")
                if self.ui:
                    self.ui.statusBar().showMessage("OBS no está en streaming. Inicia el streaming para guardar clips.", 5000)
                    if hasattr(self.ui, 'tray_manager'):
                        self.ui.tray_manager.show_info("Hotkey ignorada", "OBS no está en streaming.")
                return
            self.set_state(AppState.SAVING_CLIP)
            threading.Thread(target=self._trigger_clip_safe, daemon=True, name="ClipTriggerThread").start()
        else:
            self.ulog.warning("ApplicationController", "on_hotkey_triggered", f"Hotkey ignorada - estado: {self.state.name}")
            if self.ui:
                self.ui.statusBar().showMessage(f"Estado: {self.state.name}", 3000)

    def _trigger_clip_safe(self):
        try:
            if self.orchestrator:
                success = self.orchestrator.trigger_clip()
                if not success:
                    self.ulog.error("ApplicationController", "_trigger_clip_safe", "Error disparando clip")
                    self.set_state(AppState.CONNECTED)
                else:
                    self.ulog.info("ApplicationController", "_trigger_clip_safe", "Clip disparado exitosamente")
            else:
                self.ulog.error("ApplicationController", "_trigger_clip_safe", "Orquestador no disponible")
                self.set_state(AppState.CONNECTED)
        except Exception as e:
            self.ulog.error("ApplicationController", "_trigger_clip_safe", f"Error: {e}")
            self.set_state(AppState.CONNECTED)

    # ------------------------------------------------------------------------
    # Señales del orquestador (progreso y errores)
    # ------------------------------------------------------------------------

    def _on_orchestrator_progress(self, message: str, percent: int):
        """Actualiza la barra de estado de la UI con el mensaje y porcentaje."""
        if self.ui:
            # Mostrar mensaje en barra de estado
            self.ui.statusBar().showMessage(message, 2000)
            # Si tenemos un widget de progreso en el StatusFrame, actualizarlo
            if hasattr(self.ui.status_frame, 'update_clip_progress'):
                self.ui.status_frame.update_clip_progress(message, percent)

    def _on_orchestrator_error(self, error_msg: str):
        """Muestra error en la UI y en la bandeja."""
        self.ulog.error("ApplicationController", "_on_orchestrator_error", error_msg)
        if self.ui:
            self.ui.statusBar().showMessage(f"Error: {error_msg}", 5000)
            if hasattr(self.ui, 'tray_manager'):
                self.ui.tray_manager.show_error("Error en clip", error_msg[:100])

    def _on_task_status(self, task_id: str, status: str):
        """Registra cambios de estado de tareas."""
        self.ulog.debug("ApplicationController", "_on_task_status", f"Tarea {task_id} estado: {status}")

    def _on_clip_completed(self, clip_info: dict):
        """Cuando un clip se completa (combinado y organizado), actualiza UI y estado."""
        self.ulog.info("ApplicationController", "_on_clip_completed", f"Clip completado: {clip_info.get('filename')}")
        if self.ui:
            self.ui.statusBar().showMessage(f"Clip guardado: {clip_info.get('filename')}", 3000)
            if hasattr(self.ui, 'tray_manager'):
                self.ui.tray_manager.show_info("Clip guardado", f"Se ha guardado el clip en {clip_info.get('destination_path')}")
        # Volver al estado CONNECTED si no hay más tareas en cola
        if self.orchestrator and self.orchestrator.get_queue_size() == 0:
            self.set_state(AppState.CONNECTED)

    # ------------------------------------------------------------------------
    # Actualización de UI
    # ------------------------------------------------------------------------

    def on_obs_status_changed(self, status):
        if self.shutting_down:
            return
        self.ulog.info("ApplicationController", "on_obs_status_changed",
                       f"📡 Estado OBS: connected={status.state.name=='CONNECTED'}, replay_active={status.replay_buffer_active}, streaming={status.is_streaming}")

        obs_dict = {
            'connected': status.state.name == 'CONNECTED',
            'version': status.version,
            'replay_active': status.replay_buffer_active,
            'replay_available': status.replay_buffer_available,
            'is_streaming': status.is_streaming,
            'error': status.last_error
        }
        self.obs_status_changed.emit(obs_dict)

        if status.state.name == 'CONNECTED':
            self.set_state(AppState.CONNECTED)
            self._update_delay_limit_from_obs()
        elif status.state.name in ['DISCONNECTED', 'ERROR']:
            self.set_state(AppState.DISCONNECTED)

    def on_config_changed(self, new_config: dict):
        success = self.config_handler.apply_config_update(new_config)
        if not success:
            self.ulog.error("ApplicationController", "on_config_changed", "Error actualizando configuración")
            if self.ui:
                QMessageBox.warning(self.ui, "Error", "No se pudo actualizar la configuración")

    def test_audio(self):
        if self.audio_manager and not self.shutting_down:
            self.audio_manager.test_sound()

    def get_queue_size(self) -> int:
        if not self.orchestrator or self.shutting_down:
            return 0
        return self.orchestrator.get_queue_size()

    def _refresh_recent_clips(self):
        if self.file_manager and self.ui:
            clips = self.file_manager.get_recent_clips(limit=20)
            self.ui.update_recent_clips(clips)

    def _on_clip_saved_refresh(self, clip_info):
        self._refresh_recent_clips()

    # ------------------------------------------------------------------------
    # Cierre y limpieza
    # ------------------------------------------------------------------------

    def shutdown(self):
        if self.shutting_down:
            return

        # Verificar tareas pendientes
        pending = self.get_queue_size()
        if pending > 0 and not self._waiting_for_pending_tasks:
            msg = f"Hay {pending} clip(s) en cola. ¿Deseas esperar a que terminen antes de cerrar?"
            reply = QMessageBox.question(
                self.ui,
                "Cerrar con tareas pendientes",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._waiting_for_pending_tasks = True
                self._wait_for_pending_tasks()
                if self.get_queue_size() > 0:
                    self.ulog.warning("ApplicationController", "shutdown",
                                      f"Timeout esperando tareas pendientes ({self.get_queue_size()} restantes). Forzando cierre.")

        self.ulog.info("ApplicationController", "shutdown", "🛑 Iniciando apagado...")
        self.shutting_down = True

        try:
            if self.status_refresh_timer:
                self.status_refresh_timer.stop()
            if self.hotkey_manager:
                self.hotkey_manager.cleanup()
            if self.orchestrator:
                self.orchestrator.stop()
            self.connection_manager.stop()
            if self.obs_manager:
                self.obs_manager.disconnect()
            if self.config_manager:
                self.config_manager.save()
            if self.audio_manager:
                self.audio_manager.cleanup()
            if self.ui:
                self.ui.hide()
                self.ui.close()
            self.ulog.info("ApplicationController", "shutdown", "✅ Apagado completado")
        except Exception as e:
            self.ulog.error("ApplicationController", "shutdown", f"Error durante el apagado: {e}")

        QApplication.quit()

    def _wait_for_pending_tasks(self, timeout=10.0):
        start = time.time()
        while self.get_queue_size() > 0 and (time.time() - start) < timeout:
            time.sleep(0.2)
            QApplication.processEvents()

    def _reconnect_obs(self):
        """Reconectar OBS con la configuración actual (hilo secundario)."""
        if not self.obs_manager:
            return
        try:
            self.ulog.info("ApplicationController", "_reconnect_obs", "Desconectando OBS...")
            self.obs_manager.disconnect()
            time.sleep(1)
            self.ulog.info("ApplicationController", "_reconnect_obs", "Conectando con nueva configuración...")
            self.obs_manager.config = self.config.obs
            success = self.obs_manager.connect()
            if success:
                self.ulog.info("ApplicationController", "_reconnect_obs", "Reconexión exitosa")
                self._update_delay_limit_from_obs()
            else:
                self.ulog.error("ApplicationController", "_reconnect_obs", "Reconexión fallida")
        except Exception as e:
            self.ulog.error("ApplicationController", "_reconnect_obs", f"Error: {e}")