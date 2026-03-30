import threading
import os
from pathlib import Path
from typing import Optional, Tuple

from src.utils.logging_unified import get_logger

ulog = get_logger()


class AudioFeedbackManager:
    def __init__(self, config):
        self.config = config
        self.volume = config.volume
        self.sound_path = config.sound_path
        self.enabled = config.enabled

        self.is_initialized = False
        self.has_sound = False
        self.current_sound = None

        self._safe_initialize()

        ulog.info("AudioFeedbackManager", "__init__", f"Audio inicializado (habilitado: {self.enabled})")

    def _safe_initialize(self):
        try:
            import pygame
            pygame.mixer.init(
                frequency=22050,
                size=-16,
                channels=2,
                buffer=512
            )
            self.is_initialized = True

            if self.enabled:
                self._load_sound_file()

        except Exception as e:
            ulog.warning("AudioFeedbackManager", "_safe_initialize", f"No se pudo inicializar audio: {e}")
            self.is_initialized = False
            self.has_sound = False

    def _load_sound_file(self):
        """Cargar archivo de sonido o crear por defecto"""
        if not self.is_initialized:
            return

        try:
            import pygame

            # Si hay ruta de archivo, intentar cargarlo
            if self.sound_path and os.path.exists(self.sound_path):
                try:
                    self.current_sound = pygame.mixer.Sound(self.sound_path)
                    self.current_sound.set_volume(self.volume)
                    self.has_sound = True
                    ulog.info("AudioFeedbackManager", "_load_sound_file", f"Sonido cargado desde: {self.sound_path}")
                    return
                except Exception as e:
                    ulog.warning("AudioFeedbackManager", "_load_sound_file", f"Error cargando sonido personalizado: {e}")

            # Crear sonido por defecto
            self._create_default_sound()

        except Exception as e:
            ulog.warning("AudioFeedbackManager", "_load_sound_file", f"Error cargando sonido: {e}")
            self.enabled = False
            self.has_sound = False

    def _create_default_sound(self):
        """Crear sonido por defecto"""
        try:
            import pygame
            import array

            sample_rate = 22050
            duration = 0.1
            frequency = 800

            n_samples = int(sample_rate * duration)
            buf = array.array('h')

            for i in range(n_samples):
                if (i * frequency // sample_rate) % 2 == 0:
                    value = int(3000 * self.volume)
                else:
                    value = int(-3000 * self.volume)
                buf.append(value)

            self.current_sound = pygame.mixer.Sound(buffer=bytes(buf))
            self.current_sound.set_volume(self.volume)
            self.has_sound = True

            ulog.info("AudioFeedbackManager", "_create_default_sound", "Sonido por defecto creado")

        except Exception as e:
            ulog.warning("AudioFeedbackManager", "_create_default_sound", f"No se pudo crear sonido por defecto: {e}")
            self.has_sound = False

    def play_feedback(self):
        """Reproduce el sonido de feedback de forma no bloqueante."""
        if not self.enabled or not self.has_sound or not self.current_sound:
            return

        try:
            import pygame
            channel = pygame.mixer.find_channel()
            if channel:
                channel.play(self.current_sound)
        except Exception as e:
            ulog.error("AudioFeedbackManager", "play_feedback", f"Error reproduciendo sonido: {e}")

    def set_volume(self, volume: float):
        self.volume = max(0.0, min(1.0, volume))

        if self.current_sound:
            try:
                self.current_sound.set_volume(self.volume)
            except:
                pass

        ulog.info("AudioFeedbackManager", "set_volume", f"Volumen establecido a {self.volume:.2f}")

    def set_enabled(self, enabled: bool):
        self.enabled = enabled

        if enabled and not self.is_initialized:
            self._safe_initialize()

        ulog.info("AudioFeedbackManager", "set_enabled", f"Audio {'habilitado' if enabled else 'deshabilitado'}")

    def load_custom_sound(self, sound_path: str):
        """Cargar un archivo de sonido personalizado"""
        if not self.is_initialized:
            return False

        try:
            import pygame
            if os.path.exists(sound_path):
                self.current_sound = pygame.mixer.Sound(sound_path)
                self.current_sound.set_volume(self.volume)
                self.has_sound = True
                self.sound_path = sound_path
                ulog.info("AudioFeedbackManager", "load_custom_sound", f"Sonido personalizado cargado: {sound_path}")
                return True
        except Exception as e:
            ulog.error("AudioFeedbackManager", "load_custom_sound", f"Error cargando sonido personalizado: {e}")

        return False

    def test_sound(self):
        """Prueba el sonido actual (reproducción directa)."""
        if self.enabled and self.has_sound:
            ulog.info("AudioFeedbackManager", "test_sound", "Probando sonido...")
            self.play_feedback()

    def cleanup(self):
        try:
            if self.is_initialized:
                import pygame
                pygame.mixer.quit()
                self.is_initialized = False
        except:
            pass