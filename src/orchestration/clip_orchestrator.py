"""
Lógica de orquestación de clips.
Coordina el proceso completo de guardado de clips con delay y cola.
"""

import threading
import queue
import time
import logging
from typing import Optional
from dataclasses import dataclass

# Importar logger unificado
from src.utils.logging_unified import get_logger, log_function

logger = logging.getLogger(__name__)


@dataclass
class ClipTask:
    """Representa una tarea de guardado de clip en la cola."""
    timestamp: float
    delay: float
    status: str = "pending"  # pending, delayed, saving, done, error
    task_id: str = ""
    file_path: Optional[str] = None  # Ruta del archivo guardado (se llenará después)


class ClipOrchestrator:
    """
    Orquesta el proceso de guardado de clips:
    - Recibe solicitudes (trigger)
    - Las encola con un delay configurable
    - Ejecuta el guardado del replay buffer de OBS
    - Obtiene la ruta del clip guardado y lo mueve a la carpeta final
    """

    def __init__(self, config, obs_manager, audio_manager, file_manager):
        """
        Args:
            config: ClipConfig (src.config.manager.ClipConfig)
            obs_manager: Instancia de OBSConnectionManager
            audio_manager: Instancia de AudioFeedbackManager
            file_manager: Instancia de FileOrganizer
        """
        self.config = config
        self.obs = obs_manager
        self.audio = audio_manager
        self.file_manager = file_manager

        # Cola de tareas (FIFO)
        self.task_queue = queue.Queue(maxsize=config.max_queue_size)
        self.current_task: Optional[ClipTask] = None
        self.timer: Optional[threading.Timer] = None

        # Eventos para control de hilos
        self.stop_worker = threading.Event()

        # Contador de tareas para IDs
        self.task_counter = 0

        # Logger unificado
        self.ulog = get_logger()
        self.ulog.info("ClipOrchestrator", "__init__",
                       f"Orquestador inicializado. Cola máxima: {config.max_queue_size}, Delay: {config.delay_seconds}s")

        # Iniciar worker de procesamiento de cola
        self.worker_thread = threading.Thread(
            target=self._process_queue,
            daemon=True,
            name="ClipQueueWorker"
        )
        self.worker_thread.start()

        logger.info("Orquestador de clips inicializado")

    @log_function("trigger_clip")
    def trigger_clip(self) -> bool:
        """
        Dispara el proceso de guardado de un clip.

        Returns:
            True si la tarea se encoló correctamente, False en caso contrario.
        """
        # Verificaciones previas
        if not self.obs.is_connected():
            self.ulog.error("ClipOrchestrator", "trigger_clip", "OBS no conectado")
            return False

        if not self.obs.status.replay_buffer_active:
            self.ulog.error("ClipOrchestrator", "trigger_clip", "Replay Buffer inactivo")
            return False

        try:
            # Crear tarea con ID único
            self.task_counter += 1
            task_id = f"clip_{self.task_counter:04d}_{int(time.time())}"

            task = ClipTask(
                timestamp=time.time(),
                delay=self.config.delay_seconds,
                task_id=task_id
            )

            # Intentar encolar (non-blocking)
            self.task_queue.put_nowait(task)

            # Feedback sonoro inmediato
            self.audio.play_feedback()

            self.ulog.clip_flow("queued", {"task_id": task_id, "delay": task.delay},
                                self.task_queue.qsize(), module="ClipOrchestrator")

            return True

        except queue.Full:
            self.ulog.error("ClipOrchestrator", "trigger_clip",
                            f"Cola llena (máx {self.config.max_queue_size})")
            return False
        except Exception as e:
            self.ulog.error("ClipOrchestrator", "trigger_clip", f"Error inesperado: {e}")
            return False

    def _process_queue(self):
        """
        Worker que procesa las tareas de la cola una por una.
        Se ejecuta en un hilo separado.
        """
        self.ulog.info("ClipOrchestrator", "_process_queue", "Worker de cola iniciado")

        while not self.stop_worker.is_set():
            try:
                # Esperar tarea (timeout para poder salir limpiamente)
                task = self.task_queue.get(timeout=0.5)
                self.current_task = task

                # 1. Fase de delay
                task.status = "delayed"
                self.ulog.clip_flow("delay_start", {"task_id": task.task_id, "delay": task.delay},
                                    self.task_queue.qsize(), module="ClipOrchestrator")

                # Espera con chequeo periódico de stop
                start_time = time.time()
                while time.time() - start_time < task.delay and not self.stop_worker.is_set():
                    time.sleep(0.1)

                if self.stop_worker.is_set():
                    self.ulog.warning("ClipOrchestrator", "_process_queue",
                                      f"Tarea {task.task_id} interrumpida por cierre")
                    self.task_queue.task_done()
                    break

                # 2. Guardar replay buffer
                task.status = "saving"
                self.ulog.clip_flow("saving", {"task_id": task.task_id},
                                    self.task_queue.qsize(), module="ClipOrchestrator")

                if not self.obs.save_replay_buffer():
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"Error guardando replay buffer para tarea {task.task_id}")
                    self.task_queue.task_done()
                    self.current_task = None
                    continue

                self.ulog.info("ClipOrchestrator", "_process_queue",
                               f"Replay buffer guardado para tarea {task.task_id}")

                # 3. Obtener la ruta del archivo guardado con timeout configurable
                # Pequeña pausa para que OBS comience a escribir el archivo
                time.sleep(0.5)

                # Timeout para esperar el archivo (por defecto 15s, puede venir de config)
                file_timeout = getattr(self.config, 'file_timeout', 15.0)
                self.ulog.info("ClipOrchestrator", "_process_queue",
                               f"Esperando archivo con timeout de {file_timeout}s")

                # Intentar obtener la ruta con reintentos
                file_path = self.obs.get_last_replay_path(wait=True, timeout=file_timeout)

                if not file_path:
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"No se pudo obtener la ruta del archivo para tarea {task.task_id}")
                    self.task_queue.task_done()
                    self.current_task = None
                    continue

                # 4. Esperar a que el archivo esté completamente escrito
                ready_path = self.obs.wait_for_file(timeout=file_timeout)
                if not ready_path:
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"Archivo no listo después de timeout: {file_path}")
                    self.task_queue.task_done()
                    self.current_task = None
                    continue

                # 5. Organizar el clip (mover/renombrar)
                self.ulog.info("ClipOrchestrator", "_process_queue",
                               f"Organizando clip desde {ready_path}")
                clip_info = self.file_manager.organize_clip(ready_path)

                if clip_info and clip_info.get('success'):
                    task.status = "done"
                    task.file_path = clip_info.get('destination_path', ready_path)
                    self.ulog.clip_flow("organized", {
                        "task_id": task.task_id,
                        "source": ready_path,
                        "destination": task.file_path
                    }, self.task_queue.qsize(), module="ClipOrchestrator")
                else:
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"Error organizando clip para tarea {task.task_id}")

                self.task_queue.task_done()
                self.current_task = None

            except queue.Empty:
                continue
            except Exception as e:
                self.ulog.error("ClipOrchestrator", "_process_queue", f"Error en worker: {e}")
                if self.current_task:
                    self.current_task.status = "error"
                self.task_queue.task_done()
                self.current_task = None

        self.ulog.info("ClipOrchestrator", "_process_queue", "Worker de cola finalizado")

    def get_queue_size(self) -> int:
        """Devuelve el número de tareas pendientes en la cola."""
        return self.task_queue.qsize()

    def update_config(self, delay: Optional[float] = None, max_queue_size: Optional[int] = None,
                      file_timeout: Optional[float] = None):
        """
        Actualizar la configuración en caliente.

        Args:
            delay: Nuevo delay en segundos (opcional)
            max_queue_size: Nuevo tamaño máximo de cola (opcional)
            file_timeout: Nuevo timeout para esperar archivo (opcional)
        """
        if delay is not None:
            self.config.delay_seconds = delay
            self.ulog.info("ClipOrchestrator", "update_config",
                           f"Delay actualizado a {delay}s")
        if max_queue_size is not None:
            # Nota: cambiar el tamaño máximo de la cola en tiempo real puede tener efectos
            # colaterales; la cola mantiene su capacidad actual, pero nuevas inserciones
            # respetarán el nuevo límite.
            self.config.max_queue_size = max_queue_size
            self.ulog.info("ClipOrchestrator", "update_config",
                           f"Tamaño máximo de cola actualizado a {max_queue_size}")
        if file_timeout is not None:
            self.config.file_timeout = file_timeout
            self.ulog.info("ClipOrchestrator", "update_config",
                           f"Timeout de archivo actualizado a {file_timeout}s")

    def stop(self):
        """
        Detiene el orquestador de forma ordenada:
        - Señaliza al worker que termine
        - Vacía la cola de tareas pendientes
        """
        self.ulog.info("ClipOrchestrator", "stop", "Deteniendo orquestador...")

        self.stop_worker.set()

        # Vaciar cola (opcional, pero evita que queden tareas colgadas)
        cleared = 0
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
                cleared += 1
            except queue.Empty:
                break
        if cleared > 0:
            self.ulog.info("ClipOrchestrator", "stop", f"Se descartaron {cleared} tareas pendientes")

        # Esperar a que el worker termine (con timeout)
        self.worker_thread.join(timeout=2.0)
        if self.worker_thread.is_alive():
            self.ulog.warning("ClipOrchestrator", "stop", "Worker no terminó, continuando cierre")

        self.ulog.info("ClipOrchestrator", "stop", "Orquestador detenido")