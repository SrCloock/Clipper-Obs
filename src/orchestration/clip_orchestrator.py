"""
Lógica de orquestación de clips (pasado + futuro).
Coordina el guardado de replay buffer, grabación hacia adelante y combinación con FFmpeg.
Incluye señales de progreso para la UI y manejo robusto de errores.
"""

import threading
import queue
import time
import subprocess
import os
import shutil
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from PyQt6.QtCore import QObject, pyqtSignal

from src.utils.logging_unified import get_logger, log_function

ulog = get_logger()


@dataclass
class ClipTask:
    """Representa una tarea de guardado de clip en la cola."""
    timestamp: float
    delay: float
    status: str = "pending"          # pending, capturing_replay, recording, combining, done, error, partial
    task_id: str = ""
    replay_path: Optional[str] = None
    record_path: Optional[str] = None
    final_path: Optional[str] = None
    error_message: Optional[str] = None


class ClipOrchestrator(QObject):
    """
    Orquesta el proceso de guardado de clips:
    - Recibe solicitudes (trigger)
    - Las encola con un delay configurable (tiempo hacia atrás y hacia adelante)
    - Guarda inmediatamente el replay buffer (parte "hacia atrás")
    - Inicia una grabación normal para capturar los siguientes 'delay' segundos
    - Combina ambos archivos en un solo clip
    - Organiza el clip final en la carpeta de destino
    """

    # Señales para comunicar progreso y errores a la UI
    progress_signal = pyqtSignal(str, int)      # (mensaje, porcentaje)
    task_status_signal = pyqtSignal(str, str)   # (task_id, status)
    error_signal = pyqtSignal(str)              # mensaje de error
    clip_completed = pyqtSignal(dict)           # información del clip final

    def __init__(self, config, obs_manager, audio_manager, file_manager):
        """
        Args:
            config: ClipConfig (src.config.manager.ClipConfig)
            obs_manager: Instancia de OBSConnectionManager
            audio_manager: Instancia de AudioFeedbackManager
            file_manager: Instancia de FileOrganizer
        """
        super().__init__()
        self.config = config
        self.obs = obs_manager
        self.audio = audio_manager
        self.file_manager = file_manager

        # Cola de tareas (FIFO) - thread-safe
        self.task_queue = queue.Queue(maxsize=config.max_queue_size)
        self.current_task: Optional[ClipTask] = None

        # Eventos para control de hilos
        self.stop_worker = threading.Event()

        # Contador de tareas para IDs
        self.task_counter = 0
        self._task_counter_lock = threading.Lock()

        # Logger unificado
        self.ulog = get_logger()

        # Verificar disponibilidad de FFmpeg al inicio
        self.ffmpeg_available = self._check_ffmpeg()

        # Obtener límite del replay buffer de OBS (para validación)
        self.max_allowed_delay: Optional[int] = None
        self._update_max_allowed_delay()

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

        self.ulog.info("ClipOrchestrator", "__init__",
                       f"Orquestador inicializado. Cola máxima: {config.max_queue_size}, Delay: {config.delay_seconds}s, FFmpeg disponible: {self.ffmpeg_available}")

    # ------------------------------------------------------------------------
    # Verificación de FFmpeg
    # ------------------------------------------------------------------------

    def _check_ffmpeg(self) -> bool:
        """Verifica si FFmpeg está instalado y accesible en el PATH."""
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
                text=True
            )
            if result.returncode == 0:
                # Extraer versión para log
                first_line = result.stdout.splitlines()[0] if result.stdout else "desconocida"
                self.ulog.info("ClipOrchestrator", "_check_ffmpeg", f"FFmpeg disponible: {first_line[:50]}")
                return True
            else:
                self.ulog.error("ClipOrchestrator", "_check_ffmpeg", "FFmpeg no responde correctamente")
                return False
        except FileNotFoundError:
            self.ulog.error("ClipOrchestrator", "_check_ffmpeg",
                            "FFmpeg no encontrado. Instálalo desde https://ffmpeg.org y asegúrate de que esté en el PATH.")
            return False
        except Exception as e:
            self.ulog.error("ClipOrchestrator", "_check_ffmpeg", f"Error verificando FFmpeg: {e}")
            return False

    def _update_max_allowed_delay(self):
        """Actualiza el límite máximo de delay desde OBS."""
        if self.obs and self.obs.is_connected():
            self.max_allowed_delay = self.obs.get_replay_buffer_duration()
            if self.max_allowed_delay is None:
                self.ulog.warning("ClipOrchestrator", "_update_max_allowed_delay",
                                  "No se pudo obtener la duración del replay buffer. Asumiendo 60s por defecto.")
                self.max_allowed_delay = 60  # Valor por defecto cuerdo
        else:
            self.max_allowed_delay = None

    # ------------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------------

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
            self.error_signal.emit("No se puede crear clip: OBS no está conectado")
            return False

        if not self.obs.status.replay_buffer_active:
            self.ulog.error("ClipOrchestrator", "trigger_clip", "Replay Buffer inactivo")
            self.error_signal.emit("No se puede crear clip: El Replay Buffer de OBS no está activo. Actívalo en Ajustes → Salida → Replay Buffer")
            return False

        if not self.ffmpeg_available:
            self.ulog.error("ClipOrchestrator", "trigger_clip", "FFmpeg no disponible")
            self.error_signal.emit("FFmpeg no está instalado. No se pueden combinar los videos. Descárgalo de ffmpeg.org")
            return False

        # Verificar límite de delay
        delay = self.config.delay_seconds
        if self.max_allowed_delay and delay > self.max_allowed_delay:
            self.ulog.warning("ClipOrchestrator", "trigger_clip",
                              f"Delay solicitado ({delay}s) supera el máximo permitido ({self.max_allowed_delay}s). Usando {self.max_allowed_delay}s")
            delay = self.max_allowed_delay

        try:
            # Crear tarea con ID único
            with self._task_counter_lock:
                self.task_counter += 1
                task_id = f"clip_{self.task_counter:04d}_{int(time.time())}"

            task = ClipTask(
                timestamp=time.time(),
                delay=delay,
                task_id=task_id,
                status="pending"
            )

            # Intentar encolar (non-blocking)
            self.task_queue.put_nowait(task)

            # Feedback sonoro inmediato
            self.audio.play_feedback()

            self.ulog.clip_flow("queued", {"task_id": task_id, "delay": task.delay},
                                self.task_queue.qsize(), module="ClipOrchestrator")

            # Emitir señal de progreso
            self.progress_signal.emit(f"Clip #{task.task_counter} encolado", 0)
            self.task_status_signal.emit(task_id, "queued")

            return True

        except queue.Full:
            self.ulog.error("ClipOrchestrator", "trigger_clip",
                            f"Cola llena (máx {self.config.max_queue_size})")
            self.error_signal.emit(f"Cola de clips llena ({self.config.max_queue_size} tareas). Espera a que se complete alguna.")
            return False
        except Exception as e:
            self.ulog.error("ClipOrchestrator", "trigger_clip", f"Error inesperado: {e}")
            self.error_signal.emit(f"Error interno al crear clip: {e}")
            return False

    def get_queue_size(self) -> int:
        """Devuelve el número de tareas pendientes en la cola."""
        return self.task_queue.qsize()

    def get_max_allowed_delay(self) -> Optional[int]:
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
            self.ulog.info("ClipOrchestrator", "update_config", f"Delay actualizado a {delay}s")

        if max_queue_size is not None:
            # Nota: no podemos cambiar la cola existente dinámicamente, solo guardamos el valor para futuras tareas
            self.config.max_queue_size = max_queue_size
            self.ulog.info("ClipOrchestrator", "update_config", f"Tamaño máximo de cola actualizado a {max_queue_size}")

        if file_timeout is not None:
            self.config.file_timeout = file_timeout
            self.ulog.info("ClipOrchestrator", "update_config", f"Timeout de archivo actualizado a {file_timeout}s")

    def stop(self):
        """
        Detiene el orquestador de forma ordenada.
        """
        self.ulog.info("ClipOrchestrator", "stop", "Deteniendo orquestador...")
        self.stop_worker.set()

        # Vaciar cola (opcional, para no dejar tareas pendientes)
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
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=3.0)
            if self.worker_thread.is_alive():
                self.ulog.warning("ClipOrchestrator", "stop", "Worker no terminó, continuando cierre")
        self.ulog.info("ClipOrchestrator", "stop", "Orquestador detenido")

    # ------------------------------------------------------------------------
    # Procesamiento de cola (hilo worker)
    # ------------------------------------------------------------------------

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
                self.task_status_signal.emit(task.task_id, "processing")

                # --- Ejecutar flujo del clip ---
                self._execute_clip_task(task)

                # Marcar como completada
                self.task_queue.task_done()
                self.current_task = None

            except queue.Empty:
                continue
            except Exception as e:
                self.ulog.error("ClipOrchestrator", "_process_queue", f"Error en worker: {e}")
                import traceback
                self.ulog.debug("ClipOrchestrator", "_process_queue", traceback.format_exc())
                self.error_signal.emit(f"Error interno en el procesamiento de clips: {e}")
                if self.current_task:
                    self.current_task.status = "error"
                    self.current_task.error_message = str(e)
                    self.task_status_signal.emit(self.current_task.task_id, "error")
                self.task_queue.task_done()
                self.current_task = None

        self.ulog.info("ClipOrchestrator", "_process_queue", "Worker de cola finalizado")

    def _execute_clip_task(self, task: ClipTask):
        """
        Ejecuta los pasos de una tarea de clip.
        Emite señales de progreso y actualiza el estado.
        """
        try:
            # -----------------------------------------------------------------
            # PASO 1: Guardar Replay Buffer (parte "hacia atrás")
            # -----------------------------------------------------------------
            self.progress_signal.emit("Capturando replay buffer (pasado)...", 10)
            task.status = "capturing_replay"
            self.task_status_signal.emit(task.task_id, "capturing_replay")
            self.ulog.clip_flow("capturing_replay", {"task_id": task.task_id},
                                self.task_queue.qsize(), module="ClipOrchestrator")

            if not self.obs.save_replay_buffer():
                raise Exception("Error al guardar el replay buffer (comando OBS falló)")

            # Esperar y obtener ruta del replay
            self.progress_signal.emit("Esperando archivo de replay...", 20)
            replay_path = self.obs.wait_for_file(timeout=self.config.file_timeout)
            if not replay_path:
                raise Exception("No se pudo obtener el archivo de replay buffer dentro del timeout")

            task.replay_path = replay_path
            self.ulog.info("ClipOrchestrator", "_execute_clip_task", f"Replay guardado: {replay_path}")

            # -----------------------------------------------------------------
            # PASO 2: Iniciar grabación normal (parte "hacia adelante")
            # -----------------------------------------------------------------
            self.progress_signal.emit(f"Iniciando grabación futura ({task.delay} segundos)...", 40)
            task.status = "recording"
            self.task_status_signal.emit(task.task_id, "recording")
            self.ulog.clip_flow("recording_start", {"task_id": task.task_id, "duration": task.delay},
                                self.task_queue.qsize(), module="ClipOrchestrator")

            if not self.obs.start_record():
                raise Exception("No se pudo iniciar la grabación normal en OBS")

            # Esperar el delay configurado (con chequeo de stop)
            self._wait_with_stop_check(task.delay)

            if self.stop_worker.is_set():
                self.obs.stop_record()
                raise Exception("Proceso de clip interrumpido por cierre de la aplicación")

            # Detener grabación
            self.progress_signal.emit("Finalizando grabación futura...", 70)
            if not self.obs.stop_record():
                self.ulog.warning("ClipOrchestrator", "_execute_clip_task",
                                  "Advertencia: posible error al detener la grabación, pero se intentará recuperar el archivo")

            # Obtener archivo de grabación
            record_path = self.obs.get_last_record_path(timeout=self.config.file_timeout)
            if not record_path:
                raise Exception("No se pudo obtener el archivo de grabación futura dentro del timeout")

            task.record_path = record_path
            self.ulog.info("ClipOrchestrator", "_execute_clip_task", f"Grabación finalizada: {record_path}")

            # -----------------------------------------------------------------
            # PASO 3: Combinar videos con FFmpeg
            # -----------------------------------------------------------------
            self.progress_signal.emit("Combinando vídeos (pasado + futuro)...", 85)
            task.status = "combining"
            self.task_status_signal.emit(task.task_id, "combining")
            self.ulog.clip_flow("combining", {"task_id": task.task_id},
                                self.task_queue.qsize(), module="ClipOrchestrator")

            combined_path = self._combine_videos(replay_path, record_path, task.task_id)
            if not combined_path:
                raise Exception("Error al combinar los vídeos con FFmpeg. Revisa que FFmpeg esté instalado correctamente.")

            # -----------------------------------------------------------------
            # PASO 4: Organizar clip final
            # -----------------------------------------------------------------
            self.progress_signal.emit("Organizando clip final...", 95)
            self.ulog.info("ClipOrchestrator", "_execute_clip_task",
                           f"Organizando clip combinado: {combined_path}")

            clip_info = self.file_manager.organize_clip(combined_path)

            if clip_info and clip_info.get('success'):
                task.status = "done"
                task.final_path = clip_info.get('destination_path', combined_path)
                self.progress_signal.emit(f"Clip completado: {Path(task.final_path).name}", 100)
                self.task_status_signal.emit(task.task_id, "done")
                self.ulog.clip_flow("organized", {
                    "task_id": task.task_id,
                    "source": combined_path,
                    "destination": task.final_path
                }, self.task_queue.qsize(), module="ClipOrchestrator")
                self.clip_completed.emit(clip_info)
            else:
                raise Exception("Error al organizar el clip en la carpeta de destino")

            # Limpiar archivos temporales (replay y grabación originales)
            self._cleanup_temp_files(replay_path, record_path, combined_path)

        except Exception as e:
            # Manejo de errores: registrar y marcar tarea como error/partial
            self.ulog.error("ClipOrchestrator", "_execute_clip_task", f"Error en tarea {task.task_id}: {e}")
            task.status = "error"
            task.error_message = str(e)
            self.task_status_signal.emit(task.task_id, "error")
            self.error_signal.emit(f"Error en clip {task.task_id}: {e}")

            # Intentar salvar al menos el replay si está disponible
            if task.replay_path and Path(task.replay_path).exists():
                self._handle_partial_clip(task, task.replay_path)
            elif task.record_path and Path(task.record_path).exists():
                self._handle_partial_clip(task, task.record_path)

    # ------------------------------------------------------------------------
    # Métodos auxiliares
    # ------------------------------------------------------------------------

    def _wait_with_stop_check(self, duration: float):
        """Espera una duración con chequeo periódico de stop_worker."""
        start_time = time.time()
        while time.time() - start_time < duration and not self.stop_worker.is_set():
            # Emitir progreso durante la espera (opcional)
            elapsed = time.time() - start_time
            percent = 40 + int((elapsed / duration) * 30)  # de 40% a 70%
            self.progress_signal.emit(f"Grabando futuro... {int(duration - elapsed)}s restantes", percent)
            time.sleep(0.2)

    def _combine_videos(self, replay_path: str, record_path: str, task_id: str) -> Optional[str]:
        """
        Combina dos archivos de video usando FFmpeg (concat demuxer).
        Retorna la ruta del archivo combinado o None si falla.
        """
        try:
            temp_dir = Path(replay_path).parent
            list_file = temp_dir / f"concat_{task_id}.txt"
            output_file = temp_dir / f"combined_{task_id}.mp4"

            # Preparar rutas escapando comillas simples (para el archivo de lista)
            # Usamos Path.as_posix() para evitar problemas con backslashes en Windows
            replay_escaped = Path(replay_path).as_posix().replace("'", "'\\''")
            record_escaped = Path(record_path).as_posix().replace("'", "'\\''")

            with open(list_file, 'w', encoding='utf-8') as f:
                f.write(f"file '{replay_escaped}'\n")
                f.write(f"file '{record_escaped}'\n")

            # Comando FFmpeg
            cmd = [
                'ffmpeg', '-y',           # Sobrescribir salida
                '-f', 'concat',
                '-safe', '0',
                '-i', str(list_file),
                '-c', 'copy',             # Copiar codecs sin re-encodificar (rápido y sin pérdida)
                str(output_file)
            ]

            self.ulog.info("ClipOrchestrator", "_combine_videos", f"Ejecutando: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120   # 2 minutos máximo para combinar
            )

            # Limpiar archivo de lista
            try:
                list_file.unlink()
            except:
                pass

            if result.returncode != 0:
                self.ulog.error("ClipOrchestrator", "_combine_videos",
                                f"FFmpeg error (código {result.returncode}): {result.stderr[:500]}")
                return None

            if output_file.exists() and output_file.stat().st_size > 0:
                self.ulog.info("ClipOrchestrator", "_combine_videos",
                               f"Video combinado creado: {output_file} ({output_file.stat().st_size} bytes)")
                return str(output_file)
            else:
                self.ulog.error("ClipOrchestrator", "_combine_videos", "Archivo de salida vacío o no creado")
                return None

        except subprocess.TimeoutExpired:
            self.ulog.error("ClipOrchestrator", "_combine_videos", "Timeout en FFmpeg (más de 120 segundos)")
            return None
        except FileNotFoundError:
            self.ulog.error("ClipOrchestrator", "_combine_videos", "FFmpeg no encontrado en el sistema")
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
            self.task_status_signal.emit(task.task_id, "partial")
            self.clip_completed.emit(clip_info)
        else:
            task.status = "error"
            self.task_status_signal.emit(task.task_id, "error")

    def _cleanup_temp_files(self, replay_path: str, record_path: str, combined_path: str):
        """Elimina los archivos temporales originales después de combinar."""
        # Solo eliminar si existe el combinado
        if combined_path and Path(combined_path).exists():
            for path in (replay_path, record_path):
                if path and Path(path).exists() and path != combined_path:
                    try:
                        os.remove(path)
                        self.ulog.debug("ClipOrchestrator", "_cleanup_temp_files", f"Eliminado: {path}")
                    except Exception as e:
                        self.ulog.warning("ClipOrchestrator", "_cleanup_temp_files", f"No se pudo eliminar {path}: {e}")