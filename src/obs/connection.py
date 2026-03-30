"""
Gestor de conexión OBS WebSocket - VERSIÓN CORREGIDA
- Eliminado método duplicado get_last_replay_path
- wait_for_file mejorado con timeout configurable
- Logs más detallados
"""

import threading
import time
import logging
from typing import Optional, Callable
from dataclasses import dataclass
from enum import Enum

import obsws_python as obs

from src.utils.logging_unified import get_logger, log_function

logger = logging.getLogger(__name__)


class OBSConnectionState(Enum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 3


@dataclass
class OBSConnectionStatus:
    state: OBSConnectionState
    last_error: Optional[str] = None
    version: Optional[str] = None
    is_streaming: bool = False
    is_recording: bool = False
    replay_buffer_active: bool = False
    replay_buffer_available: bool = True


class OBSConnectionManager:
    def __init__(self, config):
        self.config = config
        self.status = OBSConnectionStatus(state=OBSConnectionState.DISCONNECTED)
        self.client: Optional[obs.ReqClient] = None
        self.event_client: Optional[obs.EventClient] = None
        self.reconnect_thread: Optional[threading.Thread] = None
        self.stop_reconnect = threading.Event()
        self.connection_handlers = []
        self.ulog = get_logger()

    def _notify_handlers(self):
        for handler in self.connection_handlers:
            try:
                handler(self.status)
            except Exception as e:
                self.ulog.error("OBSConnectionManager", "notify_handlers",
                                f"Error en handler: {e}")

    def add_connection_handler(self, handler: Callable):
        if handler not in self.connection_handlers:
            self.connection_handlers.append(handler)

    def remove_connection_handler(self, handler: Callable):
        if handler in self.connection_handlers:
            self.connection_handlers.remove(handler)

    @log_function("obs_connect")
    def connect(self) -> bool:
        self.ulog.trigger_start("obs_connect", "Conectando a OBS", module="OBS")
        start_time = time.time()
        timeout = 5

        try:
            self._cleanup_connections()
            self.status.state = OBSConnectionState.CONNECTING
            self._notify_handlers()

            self.ulog.info("OBS", "connect", f"Conectando a {self.config.host}:{self.config.port}")

            self.client = obs.ReqClient(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password if self.config.password else None,
                timeout=timeout
            )

            version_info = self.client.get_version()
            self.status.version = version_info.obs_version
            self.status.state = OBSConnectionState.CONNECTED
            self.status.last_error = None

            self._check_streaming_status()
            self._check_replay_buffer()

            duration = (time.time() - start_time) * 1000
            self.ulog.obs_command(
                "connect",
                {"host": self.config.host, "port": self.config.port},
                f"Conectado a OBS v{self.status.version}",
                duration,
                module="OBS"
            )
            self.ulog.trigger_end("obs_connect", "Conexión exitosa", module="OBS")
            self._notify_handlers()
            return True

        except TimeoutError as e:
            duration = (time.time() - start_time) * 1000
            self.status.state = OBSConnectionState.ERROR
            self.status.last_error = f"Timeout después de {timeout}s"
            self.ulog.trigger_error("obs_connect", "Timeout", e, module="OBS")
            self._notify_handlers()
            return False
        except Exception as e:
            duration = (time.time() - start_time) * 1000
            self.status.state = OBSConnectionState.ERROR
            self.status.last_error = str(e)
            self.ulog.trigger_error("obs_connect", "Error de conexión", e, module="OBS")
            self._notify_handlers()
            return False

    def _check_streaming_status(self):
        try:
            stream_status = self.client.get_stream_status()
            self.status.is_streaming = stream_status.output_active
            record_status = self.client.get_record_status()
            self.status.is_recording = record_status.output_active
            self.ulog.info("OBS", "status",
                          f"Streaming: {'ACTIVO' if self.status.is_streaming else 'INACTIVO'}, "
                          f"Grabación: {'ACTIVA' if self.status.is_recording else 'INACTIVA'}")
        except Exception as e:
            self.ulog.error("OBS", "check_streaming", f"Error: {e}")
            self.status.is_streaming = False
            self.status.is_recording = False

    def _check_replay_buffer(self):
        try:
            replay_status = self.client.get_replay_buffer_status()
            self.status.replay_buffer_active = replay_status.output_active
            self.status.replay_buffer_available = replay_status.output_active
            self.ulog.info("OBS", "replay_buffer",
                          f"Replay Buffer: {'ACTIVO' if self.status.replay_buffer_active else 'INACTIVO'}")
        except Exception as e:
            self.ulog.error("OBS", "check_replay", f"Error: {e}")
            self.status.replay_buffer_active = False
            self.status.replay_buffer_available = False

    def update_replay_status(self):
        """Actualiza el estado del Replay Buffer y notifica si cambió."""
        old = self.status.replay_buffer_active
        self._check_replay_buffer()
        if old != self.status.replay_buffer_active:
            self.ulog.info("OBS", "update_replay_status",
                           f"Cambio detectado: {old} → {self.status.replay_buffer_active}")
            self._notify_handlers()
        else:
            self.ulog.debug("OBS", "update_replay_status", "Sin cambios")

    def _cleanup_connections(self):
        try:
            if self.client:
                self.client.disconnect()
            if self.event_client:
                self.event_client.disconnect()
        except:
            pass
        finally:
            self.client = None
            self.event_client = None

    def disconnect(self):
        self.stop_reconnect.set()
        self._cleanup_connections()
        self.status.state = OBSConnectionState.DISCONNECTED
        self._notify_handlers()
        self.ulog.info("OBS", "disconnect", "Desconectado de OBS")

    def is_connected(self) -> bool:
        return self.status.state == OBSConnectionState.CONNECTED

    def get_status(self) -> OBSConnectionStatus:
        return self.status

    def save_replay_buffer(self) -> bool:
        if not self.is_connected():
            self.ulog.error("OBS", "save_replay", "No conectado")
            return False
        try:
            self.client.save_replay_buffer()
            self.ulog.info("OBS", "save_replay", "Comando enviado")
            return True
        except Exception as e:
            self.ulog.error("OBS", "save_replay", f"Error: {e}")
            return False

    def get_last_replay_path(self, wait: bool = True, timeout: float = 5.0) -> Optional[str]:
        """
        Obtener la ruta del último clip guardado del replay buffer.

        Args:
            wait: Si es True, espera hasta que la ruta esté disponible (reintentos).
            timeout: Tiempo máximo de espera en segundos (solo si wait=True).

        Returns:
            Ruta del archivo o None si no se pudo obtener.
        """
        if not self.is_connected():
            self.ulog.error("OBS", "get_last_replay_path", "No conectado")
            return None

        start_time = time.time()
        last_error = None

        while True:
            try:
                # Método específico de OBS WebSocket v5
                response = self.client.get_last_replay_buffer_replay()
                if hasattr(response, 'saved_replay_path') and response.saved_replay_path:
                    path = response.saved_replay_path
                    self.ulog.info("OBS", "get_last_replay_path", f"Ruta obtenida: {path}")
                    return path
                else:
                    # La respuesta no contiene la ruta
                    last_error = "Respuesta sin ruta"
            except AttributeError:
                # El método no está disponible en esta versión
                last_error = "Método get_last_replay_buffer_replay no disponible"
                self.ulog.warning("OBS", "get_last_replay_path", last_error)
                break
            except Exception as e:
                last_error = str(e)
                self.ulog.debug("OBS", "get_last_replay_path", f"Intento fallido: {e}")

            if not wait or (time.time() - start_time) > timeout:
                break

            time.sleep(0.2)  # esperar un poco antes de reintentar

        self.ulog.error("OBS", "get_last_replay_path",
                        f"No se pudo obtener la ruta: {last_error}")
        return None

    def wait_for_file(self, timeout: float = 15.0) -> Optional[str]:
        """
        Espera a que el archivo del último clip esté completamente escrito y accesible.

        Args:
            timeout: Tiempo máximo de espera en segundos (por defecto 15s).

        Returns:
            Ruta del archivo si está listo, None en caso contrario.
        """
        path = self.get_last_replay_path(wait=True, timeout=timeout)
        if not path:
            self.ulog.warning("OBS", "wait_for_file", "No se pudo obtener la ruta del archivo")
            return None

        import os
        start_time = time.time()
        self.ulog.info("OBS", "wait_for_file", f"Esperando que el archivo esté listo: {path}")

        while time.time() - start_time < timeout:
            try:
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    # Verificar que el tamaño no cambie durante un breve lapso
                    size1 = os.path.getsize(path)
                    time.sleep(0.1)
                    size2 = os.path.getsize(path)
                    if size1 == size2:
                        self.ulog.info("OBS", "wait_for_file",
                                       f"Archivo listo: {path} ({size1} bytes)")
                        return path
            except Exception as e:
                self.ulog.debug("OBS", "wait_for_file", f"Esperando archivo: {e}")

            time.sleep(0.2)

        self.ulog.warning("OBS", "wait_for_file", f"Timeout esperando archivo: {path}")
        return None

    def check_connection(self) -> bool:
        if not self.is_connected():
            return False
        try:
            self.client.get_version()
            return True
        except Exception as e:
            self.ulog.warning("OBS", "check_connection", f"Conexión perdida: {e}")
            self.status.state = OBSConnectionState.ERROR
            self.status.last_error = str(e)
            self._notify_handlers()
            return False