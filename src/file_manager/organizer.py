"""
Organizador de archivos de clips.
Mueve los clips guardados por OBS a la estructura de carpetas configurada.
Con caché thread-safe y manejo robusto de archivos.
"""

import os
import shutil
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List
import logging

from PyQt6.QtCore import QObject, pyqtSignal

from src.utils.logging_unified import get_logger

logger = logging.getLogger(__name__)
ulog = get_logger()


class FileOrganizer(QObject):
    """
    Organiza y gestiona archivos de clips.
    """

    # Señales
    clip_saved = pyqtSignal(dict)  # clip_info
    clip_error = pyqtSignal(dict)  # error_info

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.output_path = Path(config.output_path)
        self.naming_template = config.naming_template

        self._observer = None
        self._file_handler = None
        self._processed_files = set()

        # Contador de sesión para el token {counter}
        self._session_counter = 0
        self._counter_lock = threading.Lock()

        # Caché de clips recientes (protegida con lock)
        self._recent_clips_cache = []
        self._recent_clips_cache_time = 0
        self._recent_clips_cache_ttl = 5.0  # segundos
        self._cache_lock = threading.RLock()

        # Verificar permisos y crear directorio
        self._ensure_output_directory()

        ulog.info("FileOrganizer", "__init__", f"Organizador inicializado. Ruta: {self.output_path}")

    def update_config(self, output_path: Optional[str] = None, naming_template: Optional[str] = None):
        """
        Actualizar configuración en caliente.
        """
        changes = []

        if output_path is not None and output_path != str(self.output_path):
            new_path = Path(output_path)
            try:
                new_path.mkdir(parents=True, exist_ok=True)
                # Verificar permisos de escritura
                test_file = new_path / ".write_test"
                test_file.touch()
                test_file.unlink()
                self.output_path = new_path
                changes.append(f"output_path: {output_path}")
                ulog.info("FileOrganizer", "update_config", f"Ruta de salida actualizada a {output_path}")
            except Exception as e:
                ulog.error("FileOrganizer", "update_config", f"Error cambiando ruta de salida: {e}")
                raise

        if naming_template is not None and naming_template != self.naming_template:
            self.naming_template = naming_template
            changes.append(f"naming_template: {naming_template}")
            ulog.info("FileOrganizer", "update_config", f"Plantilla de nombres actualizada a {naming_template}")

        if changes:
            if hasattr(self.config, 'output_path') and output_path:
                self.config.output_path = str(self.output_path)
            if hasattr(self.config, 'naming_template') and naming_template:
                self.config.naming_template = naming_template
            # Invalidar caché porque la ruta de salida cambió
            self._invalidate_recent_cache()

    def _ensure_output_directory(self):
        """Asegurar que existe el directorio de salida con permisos."""
        try:
            self.output_path.mkdir(parents=True, exist_ok=True)
            test_file = self.output_path / ".write_test"
            test_file.touch()
            test_file.unlink()
            ulog.info("FileOrganizer", "ensure_output_directory", f"Directorio verificado: {self.output_path}")
        except PermissionError as e:
            ulog.error("FileOrganizer", "ensure_output_directory", f"Permiso denegado para {self.output_path}: {e}")
            # Fallback a directorio temporal
            fallback_path = Path.home() / "Downloads" / "OBS_Clips"
            fallback_path.mkdir(parents=True, exist_ok=True)
            self.output_path = fallback_path
            ulog.info("FileOrganizer", "ensure_output_directory", f"Usando directorio fallback: {fallback_path}")
            raise
        except Exception as e:
            ulog.error("FileOrganizer", "ensure_output_directory", f"Error configurando directorio: {e}")
            raise

    def _get_clip_info(self) -> Dict[str, Any]:
        """Obtener información para el nombre del clip."""
        now = datetime.now()
        with self._counter_lock:
            self._session_counter += 1
            session_counter = self._session_counter

        date_str = now.strftime("%Y-%m-%d")
        today_dir = self.output_path / date_str
        if today_dir.exists():
            existing_clips = list(today_dir.glob("*.mp4")) + list(today_dir.glob("*.mkv"))
            daily_counter = len(existing_clips) + 1
        else:
            daily_counter = 1

        return {
            'date': date_str,
            'time': now.strftime("%H-%M-%S"),
            'datetime': now.strftime("%Y-%m-%d_%H-%M-%S"),
            'year': now.strftime("%Y"),
            'month': now.strftime("%m"),
            'day': now.strftime("%d"),
            'hour': now.strftime("%H"),
            'minute': now.strftime("%M"),
            'second': now.strftime("%S"),
            'counter': session_counter,
            'daily_counter': daily_counter,
            'timestamp': int(now.timestamp()),
        }

    def _generate_filename(self, clip_info: Dict[str, Any], extension: str = ".mp4") -> str:
        """Generar nombre de archivo según plantilla."""
        try:
            filename = self.naming_template.format(**clip_info)
            if not filename.lower().endswith(extension.lower()):
                filename += extension
            # Reemplazar caracteres inválidos
            invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
            for char in invalid_chars:
                filename = filename.replace(char, '_')
            return filename
        except Exception as e:
            ulog.error("FileOrganizer", "_generate_filename", f"Error: {e}")
            return f"{clip_info['datetime']}_{clip_info['counter']}{extension}"

    def _create_daily_folder(self, date_str: str) -> Path:
        """Crear carpeta para el día actual."""
        daily_folder = self.output_path / date_str
        daily_folder.mkdir(exist_ok=True)
        return daily_folder

    def _wait_for_file_ready(self, filepath: str, timeout: float = 10.0) -> bool:
        """Espera a que un archivo esté listo para leer (tamaño estable y accesible)."""
        path = Path(filepath)
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                if not path.exists():
                    time.sleep(0.1)
                    continue
                # Intentar abrir en modo lectura
                with open(filepath, 'rb') as f:
                    f.seek(-1, 2)
                    f.read(1)
                size1 = path.stat().st_size
                time.sleep(0.1)
                size2 = path.stat().st_size
                if size1 == size2 and size1 > 0:
                    return True
            except (IOError, OSError, PermissionError):
                time.sleep(0.1)
                continue
            except Exception:
                time.sleep(0.1)
                continue
        return False

    def _ensure_unique_filename(self, filepath: Path) -> Path:
        """Asegurar nombre de archivo único añadiendo _1, _2, etc. si ya existe."""
        if not filepath.exists():
            return filepath
        counter = 1
        base = filepath.stem
        suffix = filepath.suffix
        parent = filepath.parent
        while True:
            new_name = f"{base}_{counter}{suffix}"
            new_path = parent / new_name
            if not new_path.exists():
                return new_path
            counter += 1

    def organize_clip(self, source_path: str) -> Optional[Dict[str, Any]]:
        """
        Organizar un clip moviéndolo a la ubicación final.
        """
        source = Path(source_path)
        if not source.exists():
            ulog.error("FileOrganizer", "organize_clip", f"Archivo fuente no existe: {source_path}")
            return None

        try:
            # Esperar a que el archivo esté completo
            if not self._wait_for_file_ready(str(source), timeout=10):
                ulog.warning("FileOrganizer", "organize_clip", f"Timeout esperando archivo: {source_path}")

            clip_info = self._get_clip_info()
            daily_folder = self._create_daily_folder(clip_info['date'])
            source_ext = source.suffix.lower() or ".mp4"
            filename = self._generate_filename(clip_info, source_ext)
            destination_path = daily_folder / filename
            destination_path = self._ensure_unique_filename(destination_path)

            ulog.info("FileOrganizer", "organize_clip", f"Moviendo {source} -> {destination_path}")

            if source.parent == destination_path.parent:
                if source.name != destination_path.name:
                    source.rename(destination_path)
            else:
                shutil.move(str(source), str(destination_path))

            if not destination_path.exists():
                raise IOError(f"No se pudo mover el archivo a {destination_path}")

            file_size = destination_path.stat().st_size
            file_mtime = destination_path.stat().st_mtime

            clip_info.update({
                'source_path': source_path,
                'destination_path': str(destination_path),
                'filename': destination_path.name,
                'folder': str(daily_folder),
                'size_bytes': file_size,
                'size_mb': file_size / (1024 * 1024),
                'modified_time': file_mtime,
                'success': True
            })

            self.clip_saved.emit(clip_info)
            self._invalidate_recent_cache()

            ulog.info("FileOrganizer", "organize_clip", f"Clip organizado: {destination_path.name} ({clip_info['size_mb']:.2f} MB)")
            return clip_info

        except PermissionError as e:
            error_info = {'source_path': source_path, 'error': f"Permiso denegado: {e}", 'timestamp': time.time()}
            ulog.error("FileOrganizer", "organize_clip", f"Error de permisos: {e}")
            self.clip_error.emit(error_info)
            return None
        except Exception as e:
            error_info = {'source_path': source_path, 'error': str(e), 'timestamp': time.time()}
            ulog.error("FileOrganizer", "organize_clip", f"Error organizando clip: {e}")
            self.clip_error.emit(error_info)
            return None

    def _invalidate_recent_cache(self):
        """Invalidar la caché de clips recientes (thread-safe)."""
        with self._cache_lock:
            self._recent_clips_cache = []
            self._recent_clips_cache_time = 0

    def get_recent_clips(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obtener lista de clips recientes con caché thread-safe.
        """
        current_time = time.time()
        with self._cache_lock:
            if self._recent_clips_cache and (current_time - self._recent_clips_cache_time) < self._recent_clips_cache_ttl:
                return self._recent_clips_cache[:limit]

        # Reconstruir caché (sin mantener el lock mientras se escanea el disco)
        clips = []
        try:
            date_folders = sorted(
                [d for d in self.output_path.iterdir() if d.is_dir() and d.name.count('-') == 2],
                key=lambda x: x.name,
                reverse=True
            )
            video_extensions = ['.mp4', '.mkv', '.mov', '.avi', '.flv']
            for date_folder in date_folders:
                for ext in video_extensions:
                    for clip_file in sorted(date_folder.glob(f"*{ext}"), key=lambda x: x.stat().st_mtime, reverse=True):
                        stat = clip_file.stat()
                        clips.append({
                            'path': str(clip_file),
                            'name': clip_file.name,
                            'date': date_folder.name,
                            'size_bytes': stat.st_size,
                            'size_mb': stat.st_size / (1024 * 1024),
                            'modified': stat.st_mtime,
                            'created': stat.st_ctime
                        })
                        if len(clips) >= limit:
                            break
                    if len(clips) >= limit:
                        break
                if len(clips) >= limit:
                    break
        except Exception as e:
            ulog.error("FileOrganizer", "get_recent_clips", f"Error escaneando clips: {e}")
            return []

        with self._cache_lock:
            self._recent_clips_cache = clips
            self._recent_clips_cache_time = current_time
        return clips[:limit]

    def cleanup_old_clips(self, days_to_keep: int = 30):
        """Eliminar clips más antiguos que days_to_keep días."""
        try:
            cutoff_time = time.time() - (days_to_keep * 24 * 3600)
            deleted_count = 0
            for date_folder in self.output_path.iterdir():
                if date_folder.is_dir() and date_folder.name.count('-') == 2:
                    try:
                        folder_time = datetime.strptime(date_folder.name, "%Y-%m-%d").timestamp()
                        if folder_time < cutoff_time:
                            ulog.info("FileOrganizer", "cleanup_old_clips", f"Eliminando carpeta: {date_folder}")
                            shutil.rmtree(date_folder)
                            deleted_count += 1
                    except ValueError:
                        continue
            if deleted_count > 0:
                ulog.info("FileOrganizer", "cleanup_old_clips", f"Eliminadas {deleted_count} carpetas antiguas")
                self._invalidate_recent_cache()
        except Exception as e:
            ulog.error("FileOrganizer", "cleanup_old_clips", f"Error limpiando clips: {e}")

    def get_storage_info(self) -> Dict[str, Any]:
        """Obtener información de almacenamiento."""
        try:
            total_size = 0
            total_files = 0
            for date_folder in self.output_path.iterdir():
                if date_folder.is_dir():
                    for video_file in date_folder.glob("*.*"):
                        if video_file.suffix.lower() in ['.mp4', '.mkv', '.mov', '.avi', '.flv']:
                            total_size += video_file.stat().st_size
                            total_files += 1
            return {
                'total_clips': total_files,
                'total_size_bytes': total_size,
                'total_size_mb': total_size / (1024 * 1024),
                'total_size_gb': total_size / (1024 * 1024 * 1024),
                'output_path': str(self.output_path)
            }
        except Exception as e:
            ulog.error("FileOrganizer", "get_storage_info", f"Error: {e}")
            return {
                'total_clips': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'total_size_gb': 0,
                'output_path': str(self.output_path)
            }