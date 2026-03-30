import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


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


class ConfigManager:
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or self.get_default_config_path()
        self.config: Optional[AppConfig] = None
    
    @staticmethod
    def get_default_config_path() -> str:
        app_data = Path.home() / ".obs_clip_manager"
        app_data.mkdir(exist_ok=True)
        return str(app_data / "config.json")
    
    def load(self) -> AppConfig:
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Validar que cada sección sea un diccionario
                    obs_data = data.get('obs', {})
                    if isinstance(obs_data, dict):
                        obs_config = OBSConfig(**obs_data)
                    else:
                        obs_config = OBSConfig()
                    
                    hotkey_data = data.get('hotkey', {})
                    if isinstance(hotkey_data, dict):
                        hotkey_config = HotkeyConfig(**hotkey_data)
                    else:
                        hotkey_config = HotkeyConfig()
                    
                    clip_data = data.get('clip', {})
                    if isinstance(clip_data, dict):
                        # Soporte para versiones anteriores sin file_timeout
                        if 'file_timeout' not in clip_data:
                            clip_data['file_timeout'] = 15.0
                        clip_config = ClipConfig(**clip_data)
                    else:
                        clip_config = ClipConfig()
                    
                    audio_data = data.get('audio', {})
                    if isinstance(audio_data, dict):
                        audio_config = AudioConfig(**audio_data)
                    else:
                        audio_config = AudioConfig()
                    
                    self.config = AppConfig(
                        obs=obs_config,
                        hotkey=hotkey_config,
                        clip=clip_config,
                        audio=audio_config,
                        version=data.get('version', '1.0.0')
                    )
            else:
                self.config = AppConfig.default()
                self.save()
                
            logger.info("Configuración cargada desde %s", self.config_path)
            return self.config
            
        except Exception as e:
            logger.error(f"Error cargando configuración: {e}")
            self.config = AppConfig.default()
            return self.config
    
    def reload(self) -> AppConfig:
        """
        Recarga la configuración desde el archivo, descartando cambios no guardados.
        Útil para reflejar cambios externos.
        """
        logger.info("Recargando configuración desde disco")
        return self.load()
    
    def save(self) -> bool:
        try:
            if self.config:
                data = asdict(self.config)
                os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
                
                with open(self.config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                logger.debug("Configuración guardada en %s", self.config_path)
                return True
            else:
                logger.error("No hay configuración para guardar")
                return False
        except Exception as e:
            logger.error(f"Error guardando configuración: {e}")
            return False
    
    def update(self, **kwargs) -> bool:
        if not self.config:
            logger.error("No hay configuración cargada para actualizar")
            return False
            
        try:
            # Mapear campos planos a secciones
            section_mapping = {
                'host': ('obs', 'host'),
                'port': ('obs', 'port'),
                'password': ('obs', 'password'),
                'reconnect_interval': ('obs', 'reconnect_interval'),
                'hotkey': ('hotkey', 'key_combination'),
                'hotkey_enabled': ('hotkey', 'enabled'),
                'delay': ('clip', 'delay_seconds'),
                'output_path': ('clip', 'output_path'),
                'naming_template': ('clip', 'naming_template'),
                'max_queue_size': ('clip', 'max_queue_size'),
                'file_timeout': ('clip', 'file_timeout'),
                'audio_enabled': ('audio', 'enabled'),
                'volume': ('audio', 'volume'),
                'sound_path': ('audio', 'sound_path')
            }
            
            cambios = []
            
            for key, value in kwargs.items():
                if key in section_mapping:
                    section, field = section_mapping[key]
                    section_obj = getattr(self.config, section)
                    old_value = getattr(section_obj, field)
                    
                    # Solo actualizar si el valor cambió
                    if old_value != value:
                        setattr(section_obj, field, value)
                        cambios.append(f"{section}.{field}: {old_value} -> {value}")
                        logger.debug(f"Config cambio: {section}.{field} = {value}")
                elif hasattr(self.config, key):
                    old_value = getattr(self.config, key)
                    if old_value != value:
                        setattr(self.config, key, value)
                        cambios.append(f"{key}: {old_value} -> {value}")
                        logger.debug(f"Config cambio: {key} = {value}")
            
            if cambios:
                logger.info(f"Configuración cambiada: {', '.join(cambios)}")
                saved = self.save()
                if saved:
                    logger.info("Configuración guardada exitosamente")
                else:
                    logger.error("Error guardando configuración")
                return saved
            else:
                logger.debug("No hay cambios en la configuración")
                return True
                
        except Exception as e:
            logger.error(f"Error actualizando configuración: {e}")
            return False
    
    def get_config(self) -> AppConfig:
        """Devuelve la configuración actual (puede ser None si no se ha cargado)."""
        if self.config is None:
            return self.load()
        return self.config