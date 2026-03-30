"""
Organizador de archivos de clips.
Mueve los clips guardados por OBS a la estructura de carpetas configurada.
"""

import os
import shutil
import time
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
        self._clip_counter = 0
        self._processed_files = set()

        # Contador de sesión para el token {counter}
        self._session_counter = 0

        # Caché de clips recientes
        self._recent_clips_cache = []
        self._recent_clips_cache_time = 0
        self._recent_clips_cache_ttl = 5.0  # segundos

        # Verificar permisos y crear directorio
        self._ensure_output_directory()

        ulog.info("FileOrganizer", "__init__", f"Organizador inicializado. Ruta: {self.output_path}")

    def update_config(self, output_path: Optional[str] = None, naming_template: Optional[str] = None):
        """
        Actualizar configuración en caliente.

        Args:
            output_path: Nueva ruta de salida (opcional)
            naming_template: Nueva plantilla de nombres (opcional)
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
            # Actualizar la configuración original (opcional)
            if hasattr(self.config, 'output_path') and output_path:
                self.config.output_path = str(self.output_path)
            if hasattr(self.config, 'naming_template') and naming_template:
                self.config.naming_template = naming_template

    def _ensure_output_directory(self):
        """Asegurar que existe el directorio de salida con permisos."""
        try:
            # Crear directorio si no existe
            self.output_path.mkdir(parents=True, exist_ok=True)

            # Verificar permisos de escritura
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
        """
        Obtener información para el nombre del clip.
        Incluye todos los tokens soportados.
        """
        now = datetime.now()

        # Incrementar contador de sesión para el token {counter}
        self._session_counter += 1

        # Obtener contador por día (para posible uso futuro, aunque no se usa directamente en tokens)
        date_str = now.strftime("%Y-%m-%d")
        today_dir = self.output_path / date_str
        if today_dir.exists():
            existing_clips = list(today_dir.glob("*.mp4")) + list(today_dir.glob("*.mkv"))
            daily_counter = len(existing_clips) + 1
        else:
            daily_counter = 1

        return {
            # Fecha y hora completas
            'date': date_str,  # YYYY-MM-DD
            'time': now.strftime("%H-%M-%S"),  # HH-MM-SS
            'datetime': now.strftime("%Y-%m-%d_%H-%M-%S"),
            # Componentes individuales
            'year': now.strftime("%Y"),
            'month': now.strftime("%m"),
            'day': now.strftime("%d"),
            'hour': now.strftime("%H"),
            'minute': now.strftime("%M"),
            'second': now.strftime("%S"),
            # Contadores
            'counter': self._session_counter,      # Contador por sesión (se incrementa cada clip)
            'daily_counter': daily_counter,        # Contador por día (no se usa en tokens pero puede ser útil)
            'timestamp': int(now.timestamp()),
        }

    def _generate_filename(self, clip_info: Dict[str, Any], extension: str = ".mp4") -> str:
        """Generar nombre de archivo según plantilla."""
        try:
            filename = self.naming_template.format(**clip_info)

            # Asegurar extensión
            if not filename.lower().endswith(extension.lower()):
                filename += extension

            # Reemplazar caracteres inválidos
            invalid_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
            for char in invalid_chars:
                filename = filename.replace(char, '_')

            return filename

        except Exception as e:
            ulog.error("FileOrganizer", "_generate_filename", f"Error generando nombre: {e}")
            # Nombre por defecto
            return f"{clip_info['datetime']}_{clip_info['counter']}{extension}"

    def _create_daily_folder(self, date_str: str) -> Path:
        """Crear carpeta para el día actual."""
        daily_folder = self.output_path / date_str
        daily_folder.mkdir(exist_ok=True)
        return daily_folder

    def _wait_for_file_ready(self, filepath: str, timeout: float = 10.0) -> bool:
        """
        Esperar a que un archivo esté listo para leer/escribir.

        Args:
            filepath: Ruta del archivo
            timeout: Tiempo máximo en segundos

        Returns:
            True si el archivo está listo
        """
        path = Path(filepath)
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Verificar si el archivo existe
                if not path.exists():
                    time.sleep(0.1)
                    continue

                # Intentar abrir el archivo
                with open(filepath, 'rb') as f:
                    # Intentar leer el final del archivo
                    f.seek(-1, 2)
                    _ = f.read(1)

                # Verificar tamaño estable
                current_size = path.stat().st_size
                time.sleep(0.1)  # Esperar un poco
                new_size = path.stat().st_size

                if current_size == new_size and current_size > 0:
                    return True

            except (IOError, OSError, PermissionError):
                time.sleep(0.1)
                continue
            except Exception:
                time.sleep(0.1)
                continue

        return False

    def _ensure_unique_filename(self, filepath: Path) -> Path:
        """
        Asegurar nombre de archivo único.
        Si el archivo ya existe, añade _1, _2, etc.
        """
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

        Args:
            source_path: Ruta del clip original (donde OBS lo guardó)

        Returns:
            Información del clip organizado o None si hay error.
        """
        source = Path(source_path)
        if not source.exists():
            ulog.error("FileOrganizer", "organize_clip", f"Archivo fuente no existe: {source_path}")
            return None

        try:
            # Esperar a que el archivo esté completamente escrito (por si acaso)
            if not self._wait_for_file_ready(str(source), timeout=10):
                ulog.warning("FileOrganizer", "organize_clip", f"Timeout esperando archivo: {source_path}")

            # Obtener información para el nombre
            clip_info = self._get_clip_info()

            # Crear carpeta del día
            daily_folder = self._create_daily_folder(clip_info['date'])

            # Determinar extensión
            source_ext = source.suffix.lower()
            if not source_ext:
                source_ext = ".mp4"

            # Generar nombre final
            filename = self._generate_filename(clip_info, source_ext)
            destination_path = daily_folder / filename

            # Evitar colisiones
            destination_path = self._ensure_unique_filename(destination_path)

            ulog.info("FileOrganizer", "organize_clip",
                      f"Moviendo {source} -> {destination_path}")

            # Si la ruta de origen ya está en la carpeta de destino, no mover (solo renombrar si es necesario)
            if source.parent == destination_path.parent:
                # Está en la misma carpeta, solo renombrar si el nombre cambió
                if source.name != destination_path.name:
                    ulog.info("FileOrganizer", "organize_clip",
                              f"Renombrando: {source.name} -> {destination_path.name}")
                    source.rename(destination_path)
                else:
                    ulog.info("FileOrganizer", "organize_clip",
                              f"Archivo ya está en lugar correcto: {destination_path}")
            else:
                # Mover archivo
                shutil.move(str(source), str(destination_path))

            # Verificar que se movió correctamente
            if not destination_path.exists():
                ulog.error("FileOrganizer", "organize_clip", f"Error moviendo archivo a {destination_path}")
                return None

            # Obtener información adicional
            file_size = destination_path.stat().st_size
            file_mtime = destination_path.stat().st_mtime

            # Actualizar información del clip
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

            # Emitir señal
            self.clip_saved.emit(clip_info)

            # Invalidar caché de clips recientes (para que se actualice en la próxima consulta)
            self._invalidate_recent_cache()

            ulog.info("FileOrganizer", "organize_clip",
                      f"Clip organizado: {destination_path.name} ({clip_info['size_mb']:.2f} MB)")

            return clip_info

        except PermissionError as e:
            error_info = {
                'source_path': source_path,
                'error': f"Permiso denegado: {str(e)}",
                'timestamp': time.time()
            }
            ulog.error("FileOrganizer", "organize_clip", f"Error de permisos: {e}")
            self.clip_error.emit(error_info)
            return None

        except Exception as e:
            error_info = {
                'source_path': source_path,
                'error': str(e),
                'timestamp': time.time()
            }
            ulog.error("FileOrganizer", "organize_clip", f"Error organizando clip: {e}")
            self.clip_error.emit(error_info)
            return None

    def _invalidate_recent_cache(self):
        """Invalidar la caché de clips recientes."""
        self._recent_clips_cache = []
        self._recent_clips_cache_time = 0

    def get_recent_clips(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Obtener lista de clips recientes con caché.

        Args:
            limit: Número máximo de clips a devolver

        Returns:
            Lista de diccionarios con información de los clips.
        """
        # Si la caché es válida, devolverla
        current_time = time.time()
        if (self._recent_clips_cache and
            (current_time - self._recent_clips_cache_time) < self._recent_clips_cache_ttl):
            return self._recent_clips_cache[:limit]

        # Si no, reconstruir caché
        clips = []

        try:
            # Recorrer carpetas por fecha (más recientes primero)
            date_folders = sorted(
                [d for d in self.output_path.iterdir() if d.is_dir() and d.name.count('-') == 2],
                key=lambda x: x.name,
                reverse=True
            )

            for date_folder in date_folders:
                # Buscar archivos de video
                video_extensions = ['.mp4', '.mkv', '.mov', '.avi', '.flv']
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

            # Guardar en caché
            self._recent_clips_cache = clips
            self._recent_clips_cache_time = current_time

            return clips[:limit]

        except Exception as e:
            ulog.error("FileOrganizer", "get_recent_clips", f"Error obteniendo clips: {e}")
            return []

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
                # Invalidar caché porque los clips eliminados ya no están
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
            ulog.error("FileOrganizer", "get_storage_info", f"Error obteniendo info: {e}")
            return {
                'total_clips': 0,
                'total_size_bytes': 0,
                'total_size_mb': 0,
                'total_size_gb': 0,
                'output_path': str(self.output_path)
            }