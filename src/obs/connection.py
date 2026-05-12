"""
Gestor de conexión OBS WebSocket - VERSIÓN MEJORADA
- Escucha eventos en tiempo real (streaming, grabación, replay buffer)
- Obtiene duración del Replay Buffer para limitar delay
- Soporte para iniciar/detener grabación normal
- Método para obtener ruta del último archivo grabado
- Reconexión automática con backoff
"""

import threading
import time
import os
from pathlib import Path
from typing import Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

import obsws_python as obs

from src.utils.logging_unified import get_logger, log_function

ulog = get_logger()


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
    """
    Gestor de conexión a OBS mediante WebSocket.
    Proporciona estado en tiempo real mediante event client y
    métodos para controlar replay buffer y grabación.
    """

    def __init__(self, config):
        self.config = config
        self.status = OBSConnectionStatus(state=OBSConnectionState.DISCONNECTED)
        self.client: Optional[obs.ReqClient] = None
        self.event_client: Optional[obs.EventClient] = None
        self.reconnect_thread: Optional[threading.Thread] = None
        self.stop_reconnect = threading.Event()
        self.connection_handlers = []  # Funciones a llamar cuando cambia el estado
        self._lock = threading.RLock()  # Para operaciones críticas

        # Caché para evitar consultas innecesarias
        self._last_replay_duration_check = 0
        self._cached_replay_duration: Optional[int] = None
        self._cache_ttl = 5.0  # segundos

    # ------------------------------------------------------------------------
    # Handlers y notificaciones
    # ------------------------------------------------------------------------

    def _notify_handlers(self):
        """Notifica a todos los handlers registrados del cambio de estado."""
        for handler in self.connection_handlers:
            try:
                handler(self.status)
            except Exception as e:
                ulog.error("OBSConnectionManager", "notify_handlers", f"Error en handler: {e}")

    def add_connection_handler(self, handler: Callable):
        if handler not in self.connection_handlers:
            self.connection_handlers.append(handler)

    def remove_connection_handler(self, handler: Callable):
        if handler in self.connection_handlers:
            self.connection_handlers.remove(handler)

    # ------------------------------------------------------------------------
    # Conexión y desconexión
    # ------------------------------------------------------------------------

    @log_function("obs_connect")
    def connect(self) -> bool:
        """Establece conexión con OBS y configura el cliente de eventos."""
        with self._lock:
            if self.status.state == OBSConnectionState.CONNECTED:
                return True

            self.status.state = OBSConnectionState.CONNECTING
            self._notify_handlers()

            start_time = time.time()
            timeout = 5

            try:
                ulog.info("OBSConnectionManager", "connect",
                          f"Conectando a {self.config.host}:{self.config.port}")

                # Cliente de peticiones
                self.client = obs.ReqClient(
                    host=self.config.host,
                    port=self.config.port,
                    password=self.config.password if self.config.password else None,
                    timeout=timeout
                )

                # Verificar versión para asegurar conexión
                version_info = self.client.get_version()
                self.status.version = version_info.obs_version

                # Cliente de eventos (para recibir cambios en tiempo real)
                try:
                    self.event_client = obs.EventClient(
                        host=self.config.host,
                        port=self.config.port,
                        password=self.config.password if self.config.password else None,
                        timeout=timeout
                    )
                    self.event_client.callback.register(self._on_obs_event)
                    ulog.info("OBSConnectionManager", "connect",
                              "EventClient iniciado, se recibirán eventos en tiempo real")
                except Exception as e:
                    ulog.warning("OBSConnectionManager", "connect",
                                 f"No se pudo crear EventClient: {e}. El estado se actualizará por polling.")

                # Actualizar estados iniciales
                self._check_streaming_status()
                self._check_replay_buffer()

                self.status.state = OBSConnectionState.CONNECTED
                self.status.last_error = None
                self._notify_handlers()

                duration_ms = (time.time() - start_time) * 1000
                ulog.obs_command("connect",
                                 {"host": self.config.host, "port": self.config.port},
                                 f"Conectado a OBS v{self.status.version}",
                                 duration_ms, module="OBS")
                return True

            except TimeoutError:
                self.status.state = OBSConnectionState.ERROR
                self.status.last_error = f"Timeout después de {timeout}s"
                self._notify_handlers()
                ulog.error("OBSConnectionManager", "connect", "Timeout conectando a OBS")
                return False
            except Exception as e:
                self.status.state = OBSConnectionState.ERROR
                self.status.last_error = str(e)
                self._notify_handlers()
                ulog.error("OBSConnectionManager", "connect", f"Error de conexión: {e}")
                return False

    def disconnect(self):
        """Desconecta de OBS y detiene el cliente de eventos."""
        with self._lock:
            self.stop_reconnect.set()
            self._cleanup_connections()
            self.status.state = OBSConnectionState.DISCONNECTED
            self._notify_handlers()
            ulog.info("OBSConnectionManager", "disconnect", "Desconectado de OBS")

    def _cleanup_connections(self):
        """Limpia los clientes de manera segura."""
        try:
            if self.event_client:
                self.event_client.disconnect()
        except:
            pass
        try:
            if self.client:
                self.client.disconnect()
        except:
            pass
        finally:
            self.client = None
            self.event_client = None

    def is_connected(self) -> bool:
        return self.status.state == OBSConnectionState.CONNECTED

    def check_connection(self) -> bool:
        """Verifica si la conexión sigue activa."""
        if not self.is_connected():
            return False
        try:
            self.client.get_version()
            return True
        except Exception as e:
            ulog.warning("OBSConnectionManager", "check_connection", f"Conexión perdida: {e}")
            self.status.state = OBSConnectionState.ERROR
            self.status.last_error = str(e)
            self._notify_handlers()
            return False

    def get_status(self) -> OBSConnectionStatus:
        return self.status

    # ------------------------------------------------------------------------
    # Eventos en tiempo real (desde EventClient)
    # ------------------------------------------------------------------------

    def _on_obs_event(self, event_type: str, event_data: dict):
        """
        Callback para eventos de OBS.
        Actualiza el estado inmediatamente.
        """
        ulog.debug("OBSConnectionManager", "_on_obs_event",
                   f"Evento recibido: {event_type} → {event_data}")

        changed = False
        if event_type == "StreamStateChanged":
            new_state = event_data.get("outputActive", False)
            if self.status.is_streaming != new_state:
                self.status.is_streaming = new_state
                changed = True
                ulog.info("OBSConnectionManager", "event",
                          f"Streaming {'ACTIVO' if new_state else 'INACTIVO'}")
        elif event_type == "RecordStateChanged":
            new_state = event_data.get("outputActive", False)
            if self.status.is_recording != new_state:
                self.status.is_recording = new_state
                changed = True
                ulog.info("OBSConnectionManager", "event",
                          f"Grabación {'ACTIVA' if new_state else 'INACTIVA'}")
        elif event_type == "ReplayBufferStateChanged":
            new_state = event_data.get("outputActive", False)
            if self.status.replay_buffer_active != new_state:
                self.status.replay_buffer_active = new_state
                changed = True
                ulog.info("OBSConnectionManager", "event",
                          f"Replay Buffer {'ACTIVO' if new_state else 'INACTIVO'}")

        if changed:
            self._notify_handlers()

    # ------------------------------------------------------------------------
    # Verificación de estados (polling como respaldo)
    # ------------------------------------------------------------------------

    def _check_streaming_status(self):
        """Consulta el estado de streaming y grabación mediante ReqClient."""
        try:
            stream_status = self.client.get_stream_status()
            self.status.is_streaming = stream_status.output_active
            record_status = self.client.get_record_status()
            self.status.is_recording = record_status.output_active
            ulog.debug("OBSConnectionManager", "status",
                       f"Streaming: {self.status.is_streaming}, Grabación: {self.status.is_recording}")
        except Exception as e:
            ulog.error("OBSConnectionManager", "_check_streaming_status", f"Error: {e}")
            self.status.is_streaming = False
            self.status.is_recording = False

    def _check_replay_buffer(self):
        """Consulta el estado del Replay Buffer."""
        try:
            replay_status = self.client.get_replay_buffer_status()
            self.status.replay_buffer_active = replay_status.output_active
            self.status.replay_buffer_available = replay_status.output_active
            ulog.debug("OBSConnectionManager", "replay_buffer",
                       f"Replay Buffer: {'ACTIVO' if self.status.replay_buffer_active else 'INACTIVO'}")
        except Exception as e:
            ulog.error("OBSConnectionManager", "_check_replay_buffer", f"Error: {e}")
            self.status.replay_buffer_active = False
            self.status.replay_buffer_available = False

    def update_replay_status(self):
        """Actualiza el estado del Replay Buffer manualmente (usado por el timer de polling)."""
        old = self.status.replay_buffer_active
        self._check_replay_buffer()
        if old != self.status.replay_buffer_active:
            ulog.info("OBSConnectionManager", "update_replay_status",
                      f"Cambio detectado: {old} → {self.status.replay_buffer_active}")
            self._notify_handlers()

    # ------------------------------------------------------------------------
    # Métodos para grabación hacia adelante y consulta de duración
    # ------------------------------------------------------------------------

    def get_replay_buffer_duration(self, use_cache: bool = True) -> Optional[int]:
        """
        Obtiene la duración configurada del Replay Buffer en OBS (en segundos).
        Utiliza caché para no consultar constantemente.
        """
        if not self.is_connected():
            ulog.error("OBSConnectionManager", "get_replay_buffer_duration", "No conectado")
            return None

        now = time.time()
        if use_cache and self._cached_replay_duration is not None and (now - self._last_replay_duration_check) < self._cache_ttl:
            return self._cached_replay_duration

        try:
            # En obs-websocket 5.x, se usa GetProfileParameter
            response = self.client.get_profile_parameter(
                parameterCategory="Output",
                parameterName="ReplayBufferSeconds"
            )
            duration = int(response.parameter_value)
            self._cached_replay_duration = duration
            self._last_replay_duration_check = now
            ulog.info("OBSConnectionManager", "get_replay_buffer_duration",
                      f"Duración del Replay Buffer: {duration} segundos")
            return duration
        except Exception as e:
            ulog.error("OBSConnectionManager", "get_replay_buffer_duration",
                       f"No se pudo obtener la duración: {e}")
            return None

    def start_record(self) -> bool:
        """Inicia la grabación normal en OBS."""
        if not self.is_connected():
            ulog.error("OBSConnectionManager", "start_record", "No conectado")
            return False
        try:
            self.client.start_record()
            self.status.is_recording = True
            ulog.info("OBSConnectionManager", "start_record", "Grabación iniciada")
            self._notify_handlers()
            return True
        except Exception as e:
            ulog.error("OBSConnectionManager", "start_record", f"Error al iniciar grabación: {e}")
            return False

    def stop_record(self) -> bool:
        """Detiene la grabación normal en OBS."""
        if not self.is_connected():
            ulog.error("OBSConnectionManager", "stop_record", "No conectado")
            return False
        try:
            self.client.stop_record()
            self.status.is_recording = False
            ulog.info("OBSConnectionManager", "stop_record", "Grabación detenida")
            self._notify_handlers()
            return True
        except Exception as e:
            ulog.error("OBSConnectionManager", "stop_record", f"Error al detener grabación: {e}")
            return False

    def save_replay_buffer(self) -> bool:
        """Guarda el contenido actual del Replay Buffer."""
        if not self.is_connected():
            ulog.error("OBSConnectionManager", "save_replay", "No conectado")
            return False
        try:
            self.client.save_replay_buffer()
            ulog.info("OBSConnectionManager", "save_replay", "Comando enviado")
            return True
        except Exception as e:
            ulog.error("OBSConnectionManager", "save_replay", f"Error: {e}")
            return False

    # ------------------------------------------------------------------------
    # Obtener rutas de archivos (último clip guardado por replay buffer o grabación)
    # ------------------------------------------------------------------------

    def get_last_replay_path(self, wait: bool = True, timeout: float = 5.0) -> Optional[str]:
        """Obtiene la ruta del último clip guardado con save_replay_buffer."""
        if not self.is_connected():
            ulog.error("OBSConnectionManager", "get_last_replay_path", "No conectado")
            return None

        start = time.time()
        last_error = None
        while True:
            try:
                response = self.client.get_last_replay_buffer_replay()
                if hasattr(response, 'saved_replay_path') and response.saved_replay_path:
                    path = response.saved_replay_path
                    ulog.info("OBSConnectionManager", "get_last_replay_path", f"Ruta obtenida: {path}")
                    return path
                else:
                    last_error = "Respuesta sin ruta"
            except AttributeError:
                last_error = "Método get_last_replay_buffer_replay no disponible"
                ulog.warning("OBSConnectionManager", "get_last_replay_path", last_error)
                break
            except Exception as e:
                last_error = str(e)
                ulog.debug("OBSConnectionManager", "get_last_replay_path", f"Intento fallido: {e}")

            if not wait or (time.time() - start) > timeout:
                break
            time.sleep(0.2)

        ulog.error("OBSConnectionManager", "get_last_replay_path", f"No se pudo obtener la ruta: {last_error}")
        return None

    def wait_for_file(self, timeout: float = 15.0) -> Optional[str]:
        """Espera a que el archivo del último clip esté listo y accesible."""
        path = self.get_last_replay_path(wait=True, timeout=timeout)
        if not path:
            ulog.warning("OBSConnectionManager", "wait_for_file", "No se pudo obtener la ruta del archivo")
            return None

        start = time.time()
        ulog.info("OBSConnectionManager", "wait_for_file", f"Esperando archivo: {path}")

        while time.time() - start < timeout:
            try:
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    size1 = os.path.getsize(path)
                    time.sleep(0.1)
                    size2 = os.path.getsize(path)
                    if size1 == size2:
                        ulog.info("OBSConnectionManager", "wait_for_file",
                                  f"Archivo listo: {path} ({size1} bytes)")
                        return path
            except Exception as e:
                ulog.debug("OBSConnectionManager", "wait_for_file", f"Esperando archivo: {e}")
            time.sleep(0.2)

        ulog.warning("OBSConnectionManager", "wait_for_file", f"Timeout esperando archivo: {path}")
        return None

    # ------------------------------------------------------------------------
    # Métodos para grabación normal (obtener directorio y último archivo)
    # ------------------------------------------------------------------------

    def get_record_directory(self) -> Optional[str]:
        """Obtiene el directorio donde OBS guarda las grabaciones."""
        if not self.is_connected():
            return None
        try:
            resp = self.client.get_record_directory()
            return resp.record_directory
        except Exception as e:
            ulog.error("OBSConnectionManager", "get_record_directory", f"Error: {e}")
            return None

    def get_last_record_path(self, timeout: float = 10.0) -> Optional[str]:
        """
        Intenta obtener la ruta del último archivo de grabación generado.
        Estrategia: monitorizar el directorio de grabación en busca del archivo más reciente.
        """
        record_dir = self.get_record_directory()
        if not record_dir:
            ulog.error("OBSConnectionManager", "get_last_record_path", "No se pudo obtener directorio")
            return None

        record_path = Path(record_dir)
        if not record_path.exists():
            ulog.error("OBSConnectionManager", "get_last_record_path", f"Directorio no existe: {record_dir}")
            return None

        ulog.info("OBSConnectionManager", "get_last_record_path", f"Buscando archivo reciente en {record_dir}")

        start = time.time()
        existing = set()
        # Guardar archivos ya existentes antes de detener la grabación
        try:
            for f in record_path.iterdir():
                if f.is_file():
                    existing.add(f)
        except:
            pass

        while time.time() - start < timeout:
            try:
                newest = None
                newest_mtime = 0
                for f in record_path.iterdir():
                    if f.is_file() and f not in existing:
                        mtime = f.stat().st_mtime
                        if mtime > newest_mtime:
                            newest_mtime = mtime
                            newest = f
                if newest:
                    if self._wait_for_file_ready(str(newest), timeout=5.0):
                        ulog.info("OBSConnectionManager", "get_last_record_path", f"Archivo encontrado: {newest}")
                        return str(newest)
            except Exception as e:
                ulog.debug("OBSConnectionManager", "get_last_record_path", f"Esperando archivo: {e}")
            time.sleep(0.5)

        ulog.warning("OBSConnectionManager", "get_last_record_path", "Timeout buscando archivo de grabación")
        return None

    def _wait_for_file_ready(self, filepath: str, timeout: float = 10.0) -> bool:
        """Espera a que un archivo deje de crecer (escritura finalizada)."""
        path = Path(filepath)
        start = time.time()
        while time.time() - start < timeout:
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