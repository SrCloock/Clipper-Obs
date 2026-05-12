"""
Gestor de audio para feedback de clips.
Proporciona sonido de confirmación al pulsar la hotkey, con soporte para sonidos personalizados.
"""

import threading
import os
from pathlib import Path
from typing import Optional

from src.utils.logging_unified import get_logger

ulog = get_logger()


class AudioFeedbackManager:
    """
    Maneja la reproducción de sonidos de feedback.
    Utiliza pygame.mixer para reproducción no bloqueante.
    """

    def __init__(self, config):
        """
        Args:
            config: AudioConfig con atributos enabled, volume, sound_path
        """
        self.config = config
        self.volume = config.volume
        self.sound_path = config.sound_path
        self.enabled = config.enabled

        self.is_initialized = False
        self.has_sound = False
        self.current_sound = None

        self._safe_initialize()

        ulog.info("AudioFeedbackManager", "__init__",
                  f"Audio inicializado (habilitado: {self.enabled}, volumen: {self.volume:.2f})")

    def _safe_initialize(self):
        """Inicializa pygame.mixer y carga el sonido (por defecto o personalizado)."""
        try:
            import pygame
            pygame.mixer.init(
                frequency=22050,
                size=-16,
                channels=2,
                buffer=512
            )
            self.is_initialized = True
            ulog.debug("AudioFeedbackManager", "_safe_initialize", "pygame.mixer inicializado correctamente")

            if self.enabled:
                self._load_sound_file()
            else:
                self.has_sound = False

        except Exception as e:
            ulog.warning("AudioFeedbackManager", "_safe_initialize",
                         f"No se pudo inicializar audio: {e}")
            self.is_initialized = False
            self.has_sound = False

    def _load_sound_file(self):
        """Carga el archivo de sonido personalizado o crea uno por defecto."""
        if not self.is_initialized:
            return

        # Intentar cargar sonido personalizado si la ruta existe
        if self.sound_path and os.path.exists(self.sound_path):
            if self._load_custom_sound(self.sound_path):
                return
            else:
                ulog.warning("AudioFeedbackManager", "_load_sound_file",
                             f"Error cargando sonido personalizado: {self.sound_path}. Usando sonido por defecto.")
        else:
            if self.sound_path:
                ulog.warning("AudioFeedbackManager", "_load_sound_file",
                             f"Ruta de sonido no existe: {self.sound_path}. Usando sonido por defecto.")

        # Crear sonido por defecto si no hay personalizado o falló
        self._create_default_sound()

    def _load_custom_sound(self, sound_path: str) -> bool:
        """Intenta cargar un archivo de sonido específico. Retorna True si éxito."""
        try:
            import pygame
            # Verificar extensión soportada
            ext = Path(sound_path).suffix.lower()
            if ext not in ['.wav', '.mp3', '.ogg']:
                ulog.warning("AudioFeedbackManager", "_load_custom_sound",
                             f"Formato no soportado: {ext}. Use .wav, .mp3 o .ogg")
                return False

            new_sound = pygame.mixer.Sound(sound_path)
            new_sound.set_volume(self.volume)
            self.current_sound = new_sound
            self.has_sound = True
            self.sound_path = sound_path
            ulog.info("AudioFeedbackManager", "_load_custom_sound",
                      f"Sonido personalizado cargado: {sound_path}")
            return True
        except Exception as e:
            ulog.error("AudioFeedbackManager", "_load_custom_sound",
                       f"Error cargando {sound_path}: {e}")
            return False

    def _create_default_sound(self):
        """Crea un sonido por defecto (beep cuadrado) si no hay sonido válido."""
        try:
            import pygame
            import array

            sample_rate = 22050
            duration = 0.1  # segundos
            frequency = 800  # Hz

            n_samples = int(sample_rate * duration)
            buf = array.array('h')  # signed short

            for i in range(n_samples):
                # Onda cuadrada simple
                if (i * frequency // sample_rate) % 2 == 0:
                    value = int(3000 * self.volume)
                else:
                    value = int(-3000 * self.volume)
                buf.append(value)

            self.current_sound = pygame.mixer.Sound(buffer=bytes(buf))
            self.current_sound.set_volume(self.volume)
            self.has_sound = True
            ulog.info("AudioFeedbackManager", "_create_default_sound",
                      "Sonido por defecto creado correctamente")

        except Exception as e:
            ulog.warning("AudioFeedbackManager", "_create_default_sound",
                         f"No se pudo crear sonido por defecto: {e}")
            self.has_sound = False

    def play_feedback(self):
        """Reproduce el sonido de feedback de forma no bloqueante (en hilo separado)."""
        if not self.enabled or not self.has_sound or not self.current_sound:
            return

        try:
            import pygame
            # pygame.mixer.find_channel() devuelve un canal disponible o None
            channel = pygame.mixer.find_channel()
            if channel:
                channel.play(self.current_sound)
            else:
                # Fallback: reproducir directamente (puede bloquear si todos los canales están ocupados)
                self.current_sound.play()
        except Exception as e:
            ulog.error("AudioFeedbackManager", "play_feedback",
                       f"Error reproduciendo sonido: {e}")

    def set_volume(self, volume: float):
        """Ajusta el volumen global (0.0 a 1.0)."""
        self.volume = max(0.0, min(1.0, volume))
        if self.current_sound:
            try:
                self.current_sound.set_volume(self.volume)
            except:
                pass
        ulog.info("AudioFeedbackManager", "set_volume", f"Volumen establecido a {self.volume:.2f}")

    def set_enabled(self, enabled: bool):
        """Habilita o deshabilita el sonido de feedback."""
        self.enabled = enabled
        if enabled and not self.is_initialized:
            self._safe_initialize()
        elif enabled and self.is_initialized and not self.has_sound:
            self._load_sound_file()
        ulog.info("AudioFeedbackManager", "set_enabled",
                  f"Audio {'habilitado' if enabled else 'deshabilitado'}")

    def load_custom_sound(self, sound_path: str) -> bool:
        """
        Carga un archivo de sonido personalizado.
        Retorna True si se cargó correctamente, False en caso contrario.
        """
        if not self.is_initialized:
            # Intentar inicializar si no lo estaba
            self._safe_initialize()
            if not self.is_initialized:
                return False

        if not os.path.exists(sound_path):
            ulog.warning("AudioFeedbackManager", "load_custom_sound",
                         f"Archivo no existe: {sound_path}")
            return False

        success = self._load_custom_sound(sound_path)
        if success:
            self.sound_path = sound_path
            # Guardar ruta en configuración (se hará desde el controlador, pero actualizamos local)
            if hasattr(self.config, 'sound_path'):
                self.config.sound_path = sound_path
        else:
            # Si falla, recargar sonido por defecto para no quedar sin sonido
            self._create_default_sound()
        return success

    def test_sound(self):
        """Prueba el sonido actual (reproducción directa)."""
        if self.enabled and self.has_sound:
            ulog.info("AudioFeedbackManager", "test_sound", "Probando sonido...")
            self.play_feedback()
        else:
            ulog.warning("AudioFeedbackManager", "test_sound",
                         "No se puede probar el sonido: audio deshabilitado o sin sonido cargado")

    def cleanup(self):
        """Limpia los recursos de pygame.mixer."""
        try:
            if self.is_initialized:
                import pygame
                pygame.mixer.quit()
                self.is_initialized = False
                self.has_sound = False
                self.current_sound = None
                ulog.info("AudioFeedbackManager", "cleanup", "Audio liberado correctamente")
        except Exception as e:
            ulog.warning("AudioFeedbackManager", "cleanup", f"Error al liberar audio: {e}")