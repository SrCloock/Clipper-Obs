"""
Gestor de conexión OBS WebSocket - VERSIÓN MEJORADA PARA GRABACIÓN HACIA ADELANTE
- Obtiene duración del Replay Buffer para limitar delay
- Soporte para iniciar/detener grabación normal
- Método para obtener ruta del último archivo grabado
"""

import threading
import time
import logging
import os
from pathlib import Path
from typing import Optional, Callable, List
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

    # -------------------------------------------------------------------------
    # NUEVOS MÉTODOS PARA GRABACIÓN HACIA ADELANTE
    # -------------------------------------------------------------------------

    def get_replay_buffer_duration(self) -> Optional[int]:
        """
        Obtiene la duración configurada del Replay Buffer en OBS (en segundos).
        Retorna None si no se puede obtener.
        """
        if not self.is_connected():
            self.ulog.error("OBS", "get_replay_buffer_duration", "No conectado")
            return None

        try:
            # En obs-websocket 5.x, se usa GetProfileParameter
            response = self.client.get_profile_parameter(
                parameterCategory="Output",
                parameterName="ReplayBufferSeconds"
            )
            # El valor viene como string, lo convertimos a entero
            duration = int(response.parameter_value)
            self.ulog.info("OBS", "get_replay_buffer_duration",
                           f"Duración del Replay Buffer: {duration} segundos")
            return duration
        except Exception as e:
            self.ulog.error("OBS", "get_replay_buffer_duration",
                            f"No se pudo obtener la duración: {e}")
            return None

    def start_record(self) -> bool:
        """Inicia la grabación normal en OBS."""
        if not self.is_connected():
            self.ulog.error("OBS", "start_record", "No conectado")
            return False
        try:
            self.client.start_record()
            self.status.is_recording = True
            self.ulog.info("OBS", "start_record", "Grabación iniciada")
            return True
        except Exception as e:
            self.ulog.error("OBS", "start_record", f"Error al iniciar grabación: {e}")
            return False

    def stop_record(self) -> bool:
        """Detiene la grabación normal en OBS."""
        if not self.is_connected():
            self.ulog.error("OBS", "stop_record", "No conectado")
            return False
        try:
            self.client.stop_record()
            self.status.is_recording = False
            self.ulog.info("OBS", "stop_record", "Grabación detenida")
            return True
        except Exception as e:
            self.ulog.error("OBS", "stop_record", f"Error al detener grabación: {e}")
            return False

    def get_record_directory(self) -> Optional[str]:
        """Obtiene el directorio donde OBS guarda las grabaciones."""
        if not self.is_connected():
            return None
        try:
            resp = self.client.get_record_directory()
            return resp.record_directory
        except Exception as e:
            self.ulog.error("OBS", "get_record_directory", f"Error: {e}")
            return None

    def get_last_record_path(self, timeout: float = 10.0) -> Optional[str]:
        """
        Intenta obtener la ruta del último archivo de grabación generado.
        Como OBS no expone directamente la ruta, se usa una estrategia basada en
        el directorio de grabación y el archivo más reciente después de detener la grabación.

        Args:
            timeout: Tiempo máximo de espera para que aparezca el archivo (segundos).

        Returns:
            Ruta completa del archivo o None si no se encuentra.
        """
        record_dir = self.get_record_directory()
        if not record_dir:
            self.ulog.error("OBS", "get_last_record_path", "No se pudo obtener directorio de grabación")
            return None

        record_path = Path(record_dir)
        if not record_path.exists():
            self.ulog.error("OBS", "get_last_record_path", f"Directorio no existe: {record_dir}")
            return None

        # Obtener lista de archivos antes de la grabación (si estamos en medio de una)
        # Pero como llamamos a este método justo después de stop_record, podemos
        # tomar el archivo más reciente que haya aparecido en los últimos segundos.

        self.ulog.info("OBS", "get_last_record_path", f"Buscando archivo más reciente en {record_dir}")

        start_time = time.time()
        last_check = set()
        # Primero, registrar archivos existentes para ignorarlos
        try:
            for f in record_path.iterdir():
                if f.is_file():
                    last_check.add(f)
        except Exception:
            pass

        while time.time() - start_time < timeout:
            try:
                newest_file = None
                newest_mtime = 0
                for f in record_path.iterdir():
                    if f.is_file() and f not in last_check:
                        mtime = f.stat().st_mtime
                        if mtime > newest_mtime:
                            newest_mtime = mtime
                            newest_file = f

                if newest_file:
                    # Verificar que el archivo no esté siendo escrito aún
                    if self._wait_for_file_ready(str(newest_file), timeout=5.0):
                        self.ulog.info("OBS", "get_last_record_path", f"Archivo encontrado: {newest_file}")
                        return str(newest_file)
            except Exception as e:
                self.ulog.debug("OBS", "get_last_record_path", f"Esperando archivo: {e}")

            time.sleep(0.5)

        self.ulog.warning("OBS", "get_last_record_path", "Timeout buscando archivo de grabación")
        return None

    def _wait_for_file_ready(self, filepath: str, timeout: float = 10.0) -> bool:
        """Espera a que un archivo deje de crecer (escritura finalizada)."""
        path = Path(filepath)
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if not path.exists():
                    time.sleep(0.1)
                    continue
                size1 = path.stat().st_size
                time.sleep(0.2)
                size2 = path.stat().st_size
                if size1 == size2 and size1 > 0:
                    return True
            except Exception:
                time.sleep(0.1)
        return False

    # -------------------------------------------------------------------------
    # MÉTODOS EXISTENTES (REPLAY BUFFER)
    # -------------------------------------------------------------------------

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
        """
        if not self.is_connected():
            self.ulog.error("OBS", "get_last_replay_path", "No conectado")
            return None

        start_time = time.time()
        last_error = None

        while True:
            try:
                response = self.client.get_last_replay_buffer_replay()
                if hasattr(response, 'saved_replay_path') and response.saved_replay_path:
                    path = response.saved_replay_path
                    self.ulog.info("OBS", "get_last_replay_path", f"Ruta obtenida: {path}")
                    return path
                else:
                    last_error = "Respuesta sin ruta"
            except AttributeError:
                last_error = "Método get_last_replay_buffer_replay no disponible"
                self.ulog.warning("OBS", "get_last_replay_path", last_error)
                break
            except Exception as e:
                last_error = str(e)
                self.ulog.debug("OBS", "get_last_replay_path", f"Intento fallido: {e}")

            if not wait or (time.time() - start_time) > timeout:
                break

            time.sleep(0.2)

        self.ulog.error("OBS", "get_last_replay_path",
                        f"No se pudo obtener la ruta: {last_error}")
        return None

    def wait_for_file(self, timeout: float = 15.0) -> Optional[str]:
        """
        Espera a que el archivo del último clip esté completamente escrito y accesible.
        """
        path = self.get_last_replay_path(wait=True, timeout=timeout)
        if not path:
            self.ulog.warning("OBS", "wait_for_file", "No se pudo obtener la ruta del archivo")
            return None

        start_time = time.time()
        self.ulog.info("OBS", "wait_for_file", f"Esperando que el archivo esté listo: {path}")

        while time.time() - start_time < timeout:
            try:
                if os.path.exists(path) and os.path.getsize(path) > 0:
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