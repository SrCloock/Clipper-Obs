"""
Lógica de orquestación de clips.
Coordina el proceso completo de guardado de clips con grabación hacia adelante.
"""

import threading
import queue
import time
import logging
import subprocess
import os
from pathlib import Path
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
    status: str = "pending"  # pending, capturing_replay, recording, combining, done, error
    task_id: str = ""
    replay_path: Optional[str] = None
    record_path: Optional[str] = None
    final_path: Optional[str] = None


class ClipOrchestrator:
    """
    Orquesta el proceso de guardado de clips:
    - Recibe solicitudes (trigger)
    - Las encola con un delay configurable (tiempo hacia atrás y hacia adelante)
    - Guarda inmediatamente el replay buffer (parte "hacia atrás")
    - Inicia una grabación normal para capturar los siguientes 'delay' segundos
    - Combina ambos archivos en un solo clip
    - Organiza el clip final en la carpeta de destino
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

        # Eventos para control de hilos
        self.stop_worker = threading.Event()

        # Contador de tareas para IDs
        self.task_counter = 0

        # Logger unificado
        self.ulog = get_logger()
        self.ulog.info("ClipOrchestrator", "__init__",
                       f"Orquestador inicializado. Cola máxima: {config.max_queue_size}, Delay: {config.delay_seconds}s")

        # Obtener límite del replay buffer de OBS (para validación)
        self.max_allowed_delay = self._get_replay_buffer_limit()

        # Validar delay configurado contra límite
        if self.max_allowed_delay and self.config.delay_seconds > self.max_allowed_delay:
            self.ulog.warning("ClipOrchestrator", "__init__",
                              f"Delay configurado ({self.config.delay_seconds}s) excede el límite del replay buffer ({self.max_allowed_delay}s). Se ajustará a {self.max_allowed_delay}s")
            self.config.delay_seconds = self.max_allowed_delay

        # Iniciar worker de procesamiento de cola
        self.worker_thread = threading.Thread(
            target=self._process_queue,
            daemon=True,
            name="ClipQueueWorker"
        )
        self.worker_thread.start()

        logger.info("Orquestador de clips inicializado")

    def _get_replay_buffer_limit(self) -> Optional[int]:
        """Consulta a OBS la duración del replay buffer y la retorna."""
        if self.obs and self.obs.is_connected():
            return self.obs.get_replay_buffer_duration()
        return None

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

        # Verificar límite de delay
        delay = self.config.delay_seconds
        if self.max_allowed_delay and delay > self.max_allowed_delay:
            self.ulog.warning("ClipOrchestrator", "trigger_clip",
                              f"Delay solicitado ({delay}s) supera el máximo permitido ({self.max_allowed_delay}s). Usando {self.max_allowed_delay}s")
            delay = self.max_allowed_delay

        try:
            # Crear tarea con ID único
            self.task_counter += 1
            task_id = f"clip_{self.task_counter:04d}_{int(time.time())}"

            task = ClipTask(
                timestamp=time.time(),
                delay=delay,
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

                # -----------------------------------------------------------------
                # PASO 1: Guardar Replay Buffer (parte "hacia atrás")
                # -----------------------------------------------------------------
                task.status = "capturing_replay"
                self.ulog.clip_flow("capturing_replay", {"task_id": task.task_id},
                                    self.task_queue.qsize(), module="ClipOrchestrator")

                if not self.obs.save_replay_buffer():
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"Error guardando replay buffer para tarea {task.task_id}")
                    self.task_queue.task_done()
                    self.current_task = None
                    continue

                # Esperar y obtener ruta del replay
                replay_path = self.obs.wait_for_file(timeout=self.config.file_timeout)
                if not replay_path:
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"No se pudo obtener archivo de replay para tarea {task.task_id}")
                    self.task_queue.task_done()
                    self.current_task = None
                    continue

                task.replay_path = replay_path
                self.ulog.info("ClipOrchestrator", "_process_queue",
                               f"Replay guardado: {replay_path}")

                # -----------------------------------------------------------------
                # PASO 2: Iniciar grabación normal (parte "hacia adelante")
                # -----------------------------------------------------------------
                task.status = "recording"
                self.ulog.clip_flow("recording_start", {"task_id": task.task_id, "duration": task.delay},
                                    self.task_queue.qsize(), module="ClipOrchestrator")

                if not self.obs.start_record():
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"Error iniciando grabación para tarea {task.task_id}")
                    # Aún tenemos el replay, podemos intentar salvar algo
                    self._handle_partial_clip(task, replay_path)
                    self.task_queue.task_done()
                    self.current_task = None
                    continue

                # Esperar el delay configurado (con chequeo de stop)
                self._wait_with_stop_check(task.delay)

                if self.stop_worker.is_set():
                    # Intentar detener grabación antes de salir
                    self.obs.stop_record()
                    self.ulog.warning("ClipOrchestrator", "_process_queue",
                                      f"Tarea {task.task_id} interrumpida por cierre")
                    self.task_queue.task_done()
                    break

                # Detener grabación
                if not self.obs.stop_record():
                    self.ulog.warning("ClipOrchestrator", "_process_queue",
                                      f"Posible error al detener grabación para tarea {task.task_id}")

                # Obtener archivo de grabación
                record_path = self.obs.get_last_record_path(timeout=self.config.file_timeout)
                if not record_path:
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"No se pudo obtener archivo de grabación para tarea {task.task_id}")
                    # Intentar salvar al menos el replay
                    self._handle_partial_clip(task, replay_path)
                    self.task_queue.task_done()
                    self.current_task = None
                    continue

                task.record_path = record_path
                self.ulog.info("ClipOrchestrator", "_process_queue",
                               f"Grabación finalizada: {record_path}")

                # -----------------------------------------------------------------
                # PASO 3: Combinar videos
                # -----------------------------------------------------------------
                task.status = "combining"
                self.ulog.clip_flow("combining", {"task_id": task.task_id},
                                    self.task_queue.qsize(), module="ClipOrchestrator")

                combined_path = self._combine_videos(replay_path, record_path, task.task_id)
                if not combined_path:
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"Error combinando videos para tarea {task.task_id}")
                    # Intentar organizar al menos uno de los archivos
                    fallback_path = replay_path or record_path
                    if fallback_path:
                        self._handle_partial_clip(task, fallback_path)
                    self.task_queue.task_done()
                    self.current_task = None
                    continue

                # -----------------------------------------------------------------
                # PASO 4: Organizar clip final
                # -----------------------------------------------------------------
                self.ulog.info("ClipOrchestrator", "_process_queue",
                               f"Organizando clip combinado: {combined_path}")

                clip_info = self.file_manager.organize_clip(combined_path)

                if clip_info and clip_info.get('success'):
                    task.status = "done"
                    task.final_path = clip_info.get('destination_path', combined_path)
                    self.ulog.clip_flow("organized", {
                        "task_id": task.task_id,
                        "source": combined_path,
                        "destination": task.final_path
                    }, self.task_queue.qsize(), module="ClipOrchestrator")
                else:
                    task.status = "error"
                    self.ulog.error("ClipOrchestrator", "_process_queue",
                                    f"Error organizando clip para tarea {task.task_id}")

                # Limpiar archivos temporales (el replay y el record originales)
                self._cleanup_temp_files(replay_path, record_path, combined_path)

                self.task_queue.task_done()
                self.current_task = None

            except queue.Empty:
                continue
            except Exception as e:
                self.ulog.error("ClipOrchestrator", "_process_queue", f"Error en worker: {e}")
                import traceback
                self.ulog.debug("ClipOrchestrator", "_process_queue", traceback.format_exc())
                if self.current_task:
                    self.current_task.status = "error"
                self.task_queue.task_done()
                self.current_task = None

        self.ulog.info("ClipOrchestrator", "_process_queue", "Worker de cola finalizado")

    def _wait_with_stop_check(self, duration: float):
        """Espera una duración con chequeo periódico de stop_worker."""
        start_time = time.time()
        while time.time() - start_time < duration and not self.stop_worker.is_set():
            time.sleep(0.1)

    def _combine_videos(self, replay_path: str, record_path: str, task_id: str) -> Optional[str]:
        """
        Combina dos archivos de video usando FFmpeg (concat demuxer).
        Retorna la ruta del archivo combinado o None si falla.
        """
        try:
            # Crear archivo temporal de lista para concat
            temp_dir = Path(replay_path).parent
            list_file = temp_dir / f"concat_{task_id}.txt"
            output_file = temp_dir / f"combined_{task_id}.mp4"

            # Preparar rutas escapando comillas simples (sin backslashes problemáticos)
            escaped_replay = replay_path.replace("'", "'\\''")
            escaped_record = record_path.replace("'", "'\\''")

            with open(list_file, 'w', encoding='utf-8') as f:
                f.write(f"file '{escaped_replay}'\n")
                f.write(f"file '{escaped_record}'\n")

            # Comando FFmpeg
            cmd = [
                'ffmpeg', '-y',  # Sobrescribir output
                '-f', 'concat',
                '-safe', '0',
                '-i', str(list_file),
                '-c', 'copy',   # Copiar codecs sin re-encodificar (rápido)
                str(output_file)
            ]

            self.ulog.info("ClipOrchestrator", "_combine_videos", f"Ejecutando: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120  # Timeout de 2 minutos máximo
            )

            if result.returncode != 0:
                self.ulog.error("ClipOrchestrator", "_combine_videos",
                                f"FFmpeg error: {result.stderr}")
                return None

            # Limpiar archivo de lista
            try:
                list_file.unlink()
            except:
                pass

            if output_file.exists() and output_file.stat().st_size > 0:
                self.ulog.info("ClipOrchestrator", "_combine_videos",
                               f"Video combinado creado: {output_file} ({output_file.stat().st_size} bytes)")
                return str(output_file)
            else:
                self.ulog.error("ClipOrchestrator", "_combine_videos", "Archivo de salida vacío o no creado")
                return None

        except subprocess.TimeoutExpired:
            self.ulog.error("ClipOrchestrator", "_combine_videos", "Timeout en FFmpeg")
            return None
        except Exception as e:
            self.ulog.error("ClipOrchestrator", "_combine_videos", f"Error inesperado: {e}")
            return None

    def _handle_partial_clip(self, task: ClipTask, available_path: str):
        """
        Maneja el caso de que solo tengamos una parte del clip (replay o grabación).
        Intenta organizar ese archivo único como respaldo.
        """
        self.ulog.warning("ClipOrchestrator", "_handle_partial_clip",
                          f"Guardando clip parcial para tarea {task.task_id}")
        clip_info = self.file_manager.organize_clip(available_path)
        if clip_info and clip_info.get('success'):
            task.status = "partial"
            task.final_path = clip_info.get('destination_path', available_path)
        else:
            task.status = "error"

    def _cleanup_temp_files(self, replay_path: str, record_path: str, combined_path: str):
        """Elimina los archivos temporales originales después de combinar."""
        # Solo eliminar si existe el combinado
        if combined_path and Path(combined_path).exists():
            for path in (replay_path, record_path):
                if path and Path(path).exists():
                    try:
                        # No eliminar si es el mismo que el combinado
                        if path != combined_path:
                            os.remove(path)
                            self.ulog.debug("ClipOrchestrator", "_cleanup_temp_files", f"Eliminado: {path}")
                    except Exception as e:
                        self.ulog.warning("ClipOrchestrator", "_cleanup_temp_files", f"No se pudo eliminar {path}: {e}")

    def get_queue_size(self) -> int:
        """Devuelve el número de tareas pendientes en la cola."""
        return self.task_queue.qsize()

    def get_max_allowed_delay(self) -> Optional[int]:
        """Retorna el límite máximo de delay según el replay buffer de OBS."""
        return self.max_allowed_delay

    def update_config(self, delay: Optional[float] = None, max_queue_size: Optional[int] = None,
                      file_timeout: Optional[float] = None):
        """
        Actualizar la configuración en caliente.
        """
        if delay is not None:
            # Validar contra límite
            if self.max_allowed_delay and delay > self.max_allowed_delay:
                self.ulog.warning("ClipOrchestrator", "update_config",
                                  f"Delay solicitado ({delay}s) excede el máximo ({self.max_allowed_delay}s). Se usará {self.max_allowed_delay}s")
                delay = self.max_allowed_delay
            self.config.delay_seconds = delay
            self.ulog.info("ClipOrchestrator", "update_config",
                           f"Delay actualizado a {delay}s")

        if max_queue_size is not None:
            self.config.max_queue_size = max_queue_size
            self.ulog.info("ClipOrchestrator", "update_config",
                           f"Tamaño máximo de cola actualizado a {max_queue_size}")

        if file_timeout is not None:
            self.config.file_timeout = file_timeout
            self.ulog.info("ClipOrchestrator", "update_config",
                           f"Timeout de archivo actualizado a {file_timeout}s")

    def stop(self):
        """
        Detiene el orquestador de forma ordenada.
        """
        self.ulog.info("ClipOrchestrator", "stop", "Deteniendo orquestador...")

        self.stop_worker.set()

        # Vaciar cola
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

        # Esperar a que el worker termine
        self.worker_thread.join(timeout=3.0)
        if self.worker_thread.is_alive():
            self.ulog.warning("ClipOrchestrator", "stop", "Worker no terminó, continuando cierre")

        self.ulog.info("ClipOrchestrator", "stop", "Orquestador detenido")