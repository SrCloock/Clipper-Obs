"""
Gestor de configuración con persistencia robusta, migraciones y seguridad ante escrituras concurrentes.
"""

import json
import os
import threading
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, Dict, Any

from src.utils.logging_unified import get_logger

logger = get_logger()  # Uso del logger unificado


# ============================================================================
# Modelos de configuración (dataclasses)
# ============================================================================

@dataclass
class OBSConfig:
    host: str = "localhost"
    port: int = 4455
    password: str = ""
    reconnect_interval: int = 5


@dataclass
class HotkeyConfig:
    key_combination: str = "ctrl+shift+c"
    enabled: bool = True


@dataclass
class ClipConfig:
    delay_seconds: float = 5.0
    output_path: str = str(Path.home() / "Videos" / "OBS Clips")
    naming_template: str = "{date}_{time}_{counter}"
    max_queue_size: int = 10
    file_timeout: float = 15.0  # Tiempo máximo de espera para que el archivo esté listo (segundos)


@dataclass
class AudioConfig:
    enabled: bool = True
    volume: float = 0.7
    sound_path: str = ""  # Ruta al archivo de sonido personalizado


@dataclass
class AppConfig:
    obs: OBSConfig
    hotkey: HotkeyConfig
    clip: ClipConfig
    audio: AudioConfig
    version: str = "1.0.0"

    @classmethod
    def default(cls):
        return cls(
            obs=OBSConfig(),
            hotkey=HotkeyConfig(),
            clip=ClipConfig(),
            audio=AudioConfig()
        )


# ============================================================================
# Gestor de configuración con bloqueo de escritura y migraciones
# ============================================================================

class ConfigManager:
    """
    Gestor de configuración thread-safe con:
    - Validación de escritura en disco.
    - Migración automática de configuraciones antiguas.
    - Caché en memoria para evitar recargas innecesarias.
    - Bloqueo para escrituras concurrentes.
    """

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else Path(self.get_default_config_path())
        self.config: Optional[AppConfig] = None
        self._lock = threading.RLock()
        self._dirty = False  # Indica si hay cambios en memoria no guardados

        # Asegurar que el directorio de configuración existe
        self.config_path.parent.mkdir(parents=True, exist_ok=True)

        # Cargar configuración inicial
        self.load()

    @staticmethod
    def get_default_config_path() -> str:
        """Ruta por defecto: ~/.obs_clip_manager/config.json"""
        app_data = Path.home() / ".obs_clip_manager"
        app_data.mkdir(exist_ok=True)
        return str(app_data / "config.json")

    # ------------------------------------------------------------------------
    # Carga y persistencia
    # ------------------------------------------------------------------------

    def load(self) -> AppConfig:
        """Carga la configuración desde disco, aplicando migraciones si es necesario."""
        with self._lock:
            try:
                if self.config_path.exists():
                    with open(self.config_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.config = self._dict_to_config(data)
                    logger.info("ConfigManager", "load", f"Configuración cargada desde {self.config_path}")
                    # Actualizar versión guardada (útil para futuras migraciones)
                    if hasattr(self.config, 'version'):
                        self.config.version = data.get('version', '1.0.0')
                else:
                    self.config = AppConfig.default()
                    self._dirty = True
                    self._save_unsafe()  # Guardar inmediatamente el default
                    logger.info("ConfigManager", "load", "Creada configuración por defecto")

                self._dirty = False
                return self.config

            except json.JSONDecodeError as e:
                logger.error("ConfigManager", "load", f"Error decodificando JSON: {e}. Usando default.")
                self.config = AppConfig.default()
                self._dirty = True
                return self.config
            except Exception as e:
                logger.error("ConfigManager", "load", f"Error inesperado cargando configuración: {e}")
                self.config = AppConfig.default()
                self._dirty = True
                return self.config

    def _dict_to_config(self, data: Dict[str, Any]) -> AppConfig:
        """Convierte un diccionario (posiblemente incompleto) en un AppConfig aplicando migraciones."""
        # Obtener secciones con valores por defecto si faltan
        obs_data = data.get('obs', {})
        if isinstance(obs_data, dict):
            obs = OBSConfig(**obs_data)
        else:
            obs = OBSConfig()

        hotkey_data = data.get('hotkey', {})
        if isinstance(hotkey_data, dict):
            hotkey = HotkeyConfig(**hotkey_data)
        else:
            hotkey = HotkeyConfig()

        clip_data = data.get('clip', {})
        if isinstance(clip_data, dict):
            # Migración: si falta 'file_timeout', establecer valor por defecto
            if 'file_timeout' not in clip_data:
                clip_data['file_timeout'] = 15.0
            clip = ClipConfig(**clip_data)
        else:
            clip = ClipConfig()

        audio_data = data.get('audio', {})
        if isinstance(audio_data, dict):
            audio = AudioConfig(**audio_data)
        else:
            audio = AudioConfig()

        version = data.get('version', '1.0.0')

        return AppConfig(obs=obs, hotkey=hotkey, clip=clip, audio=audio, version=version)

    def save(self) -> bool:
        """Guarda la configuración actual en disco de forma segura (thread-safe)."""
        with self._lock:
            if not self.config:
                logger.error("ConfigManager", "save", "No hay configuración para guardar")
                return False
            if not self._dirty:
                logger.debug("ConfigManager", "save", "Sin cambios, no se guarda")
                return True
            return self._save_unsafe()

    def _save_unsafe(self) -> bool:
        """
        Guarda la configuración sin bloqueo (asume que se llama con lock adquirido).
        Realiza escritura atómica (temp file + rename) para evitar corrupción.
        """
        try:
            # Convertir a dict
            data = asdict(self.config)

            # Escribir primero en un archivo temporal
            temp_path = self.config_path.with_suffix('.tmp')
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # Verificar que se escribió algo
            if temp_path.stat().st_size == 0:
                raise IOError("Archivo temporal vacío")

            # Renombrar (operación atómica en la mayoría de sistemas)
            temp_path.replace(self.config_path)

            self._dirty = False
            logger.info("ConfigManager", "save", f"Configuración guardada en {self.config_path}")
            return True

        except PermissionError as e:
            logger.error("ConfigManager", "save", f"Permiso denegado al guardar: {e}")
            return False
        except Exception as e:
            logger.error("ConfigManager", "save", f"Error guardando configuración: {e}")
            # Intentar limpiar el temporal si existe
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except:
                    pass
            return False

    # ------------------------------------------------------------------------
    # Actualización y helpers
    # ------------------------------------------------------------------------

    def update(self, **kwargs) -> bool:
        """
        Actualiza uno o más campos de configuración.
        Los kwargs pueden ser nombres planos (ej. 'delay') que se mapean a las secciones correspondientes.
        Retorna True si se guardó correctamente.
        """
        with self._lock:
            if not self.config:
                logger.error("ConfigManager", "update", "No hay configuración cargada")
                return False

            # Mapeo de claves planas a (sección, atributo)
            mapping = {
                # OBS
                'host': ('obs', 'host'),
                'port': ('obs', 'port'),
                'password': ('obs', 'password'),
                'reconnect_interval': ('obs', 'reconnect_interval'),
                # Hotkey
                'hotkey': ('hotkey', 'key_combination'),
                'hotkey_enabled': ('hotkey', 'enabled'),
                # Clip
                'delay': ('clip', 'delay_seconds'),
                'output_path': ('clip', 'output_path'),
                'naming_template': ('clip', 'naming_template'),
                'max_queue_size': ('clip', 'max_queue_size'),
                'file_timeout': ('clip', 'file_timeout'),
                # Audio
                'audio_enabled': ('audio', 'enabled'),
                'volume': ('audio', 'volume'),
                'sound_path': ('audio', 'sound_path'),
            }

            cambios = False
            for key, value in kwargs.items():
                if key in mapping:
                    section, field = mapping[key]
                    section_obj = getattr(self.config, section)
                    old_val = getattr(section_obj, field)
                    if old_val != value:
                        setattr(section_obj, field, value)
                        cambios = True
                        logger.debug("ConfigManager", "update", f"{section}.{field}: {old_val} -> {value}")
                elif hasattr(self.config, key):
                    old_val = getattr(self.config, key)
                    if old_val != value:
                        setattr(self.config, key, value)
                        cambios = True
                        logger.debug("ConfigManager", "update", f"{key}: {old_val} -> {value}")
                else:
                    logger.warning("ConfigManager", "update", f"Clave desconocida: {key}")

            if cambios:
                self._dirty = True
                return self._save_unsafe()
            else:
                logger.debug("ConfigManager", "update", "No hubo cambios reales")
                return True

    def reload(self) -> AppConfig:
        """Recarga la configuración desde disco, descartando cambios no guardados."""
        with self._lock:
            logger.info("ConfigManager", "reload", "Recargando configuración desde disco")
            return self.load()

    def get_config(self) -> AppConfig:
        """Devuelve la configuración actual (cargada en memoria)."""
        with self._lock:
            if self.config is None:
                return self.load()
            return self.config

    def is_dirty(self) -> bool:
        """Indica si hay cambios en memoria no guardados."""
        with self._lock:
            return self._dirty

    # ------------------------------------------------------------------------
    # Utilidades para migración futura (opcional)
    # ------------------------------------------------------------------------
    def _migrate_v1_to_v2(self, data: Dict) -> Dict:
        """Ejemplo de migración: si se añaden nuevos campos en el futuro."""
        # Aquí se podrían aplicar transformaciones.
        # Por ahora no se necesita.
        return data