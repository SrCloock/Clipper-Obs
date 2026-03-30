"""
Gestor de hotkeys globales del sistema usando pynput (compatible con juegos a pantalla completa)
"""

import threading
import time
from typing import Optional, Callable, Set, Tuple, Union

from pynput import keyboard as pynput_kb

from src.utils.logging_unified import get_logger

ulog = get_logger()


class HotkeyManager:
    """
    Gestor de hotkeys globales del sistema.
    Utiliza pynput para capturar eventos incluso en juegos a pantalla completa.
    """

    def __init__(self):
        self.registered_hotkey = None
        self.callback = None
        self.is_registered = False
        self._lock = threading.Lock()

        # Listener de pynput
        self.listener = None
        self.listener_thread = None

        # Estado actual de teclas presionadas
        self.current_pressed = set()

        # Mapeo de nombres a objetos Key/KeyCode de pynput
        self._key_map = {
            # Modificadores
            'ctrl': pynput_kb.Key.ctrl,
            'control': pynput_kb.Key.ctrl,
            'shift': pynput_kb.Key.shift,
            'alt': pynput_kb.Key.alt,
            'win': pynput_kb.Key.cmd,
            'cmd': pynput_kb.Key.cmd,
            # Teclas especiales
            'f1': pynput_kb.Key.f1,
            'f2': pynput_kb.Key.f2,
            'f3': pynput_kb.Key.f3,
            'f4': pynput_kb.Key.f4,
            'f5': pynput_kb.Key.f5,
            'f6': pynput_kb.Key.f6,
            'f7': pynput_kb.Key.f7,
            'f8': pynput_kb.Key.f8,
            'f9': pynput_kb.Key.f9,
            'f10': pynput_kb.Key.f10,
            'f11': pynput_kb.Key.f11,
            'f12': pynput_kb.Key.f12,
            'space': pynput_kb.Key.space,
            'enter': pynput_kb.Key.enter,
            'esc': pynput_kb.Key.esc,
            'tab': pynput_kb.Key.tab,
            'backspace': pynput_kb.Key.backspace,
            'delete': pynput_kb.Key.delete,
            'insert': pynput_kb.Key.insert,
            'home': pynput_kb.Key.home,
            'end': pynput_kb.Key.end,
            'page_up': pynput_kb.Key.page_up,
            'page_down': pynput_kb.Key.page_down,
            'up': pynput_kb.Key.up,
            'down': pynput_kb.Key.down,
            'left': pynput_kb.Key.left,
            'right': pynput_kb.Key.right,
        }

        # Para teclas alfanuméricas se usa KeyCode.from_char
        self._char_map = {chr(i): pynput_kb.KeyCode.from_char(chr(i)) for i in range(32, 127)}

        self._target_combo: Optional[Set[pynput_kb.Key]] = None
        self._target_modifiers: Set[pynput_kb.Key] = set()

        # Mapeo de modificadores para comprobación rápida
        self._modifier_keys = {
            pynput_kb.Key.ctrl,
            pynput_kb.Key.shift,
            pynput_kb.Key.alt,
            pynput_kb.Key.cmd,
        }

    def _get_key_object(self, key_name: str) -> Union[pynput_kb.Key, pynput_kb.KeyCode]:
        """Convierte un nombre de tecla normalizado al objeto correspondiente de pynput."""
        key_name = key_name.lower()
        if key_name in self._key_map:
            return self._key_map[key_name]
        # Tecla alfanumérica
        if len(key_name) == 1 and key_name in self._char_map:
            return self._char_map[key_name]
        # Tecla numérica
        if key_name.isdigit() and key_name in self._char_map:
            return self._char_map[key_name]
        # Si no se encuentra, lanzar error
        raise ValueError(f"Tecla no soportada: {key_name}")

    def normalize_hotkey(self, hotkey: str) -> str:
        """
        Normalizar formato de hotkey
        """
        if not hotkey:
            return ""

        # Convertir a minúsculas
        normalized = hotkey.lower()

        # Reemplazar variantes comunes
        replacements = {
            'control': 'ctrl',
            'windows': 'win',
            'command': 'cmd',
            'option': 'alt',
        }
        for old, new in replacements.items():
            normalized = normalized.replace(old, new)

        # Eliminar espacios y estandarizar separadores
        normalized = normalized.replace(' ', '').replace('++', '+')

        # Eliminar duplicados
        parts = normalized.split('+')
        unique_parts = []
        for part in parts:
            if part and part not in unique_parts:
                unique_parts.append(part)

        return '+'.join(unique_parts)

    def validate_hotkey(self, hotkey: str) -> tuple[bool, str]:
        """
        Validar que la hotkey sea válida
        """
        if not hotkey:
            return False, "Hotkey no puede estar vacía"

        normalized = self.normalize_hotkey(hotkey)
        parts = normalized.split('+')

        # Validar que haya al menos una tecla regular
        modifiers = ['ctrl', 'shift', 'alt', 'win', 'cmd']
        regular_keys = [p for p in parts if p not in modifiers]

        if not regular_keys:
            return False, "Debe incluir al menos una tecla regular (no modificadora)"

        if len(regular_keys) > 1:
            return False, "Solo puede tener una tecla regular"

        # Verificar que cada parte sea una tecla conocida
        try:
            for part in parts:
                self._get_key_object(part)
        except ValueError as e:
            return False, str(e)

        return True, ""

    def _parse_combo(self, normalized: str) -> Tuple[Set[pynput_kb.Key], Set[pynput_kb.Key]]:
        """
        Parsea una hotkey normalizada en un conjunto de teclas requeridas.
        Retorna (required_keys, modifiers) donde modifiers es un subconjunto.
        """
        parts = normalized.split('+')
        modifiers = {'ctrl', 'shift', 'alt', 'win', 'cmd'}
        required = set()
        mod_set = set()

        for part in parts:
            key = self._get_key_object(part)
            required.add(key)
            if part in modifiers:
                mod_set.add(key)
        return required, mod_set

    def _on_press(self, key):
        """Callback cuando se presiona una tecla."""
        with self._lock:
            self.current_pressed.add(key)
            self._check_match()

    def _on_release(self, key):
        """Callback cuando se suelta una tecla."""
        with self._lock:
            if key in self.current_pressed:
                self.current_pressed.remove(key)

    def _check_match(self):
        """Verifica si la combinación actual coincide con la registrada."""
        if not self.is_registered or not self.callback or not self._target_combo:
            return

        # Para que coincida, el conjunto de teclas presionadas debe contener exactamente
        # las teclas requeridas (sin teclas extra).
        if self.current_pressed == self._target_combo:
            # Invocar callback en un hilo separado para no bloquear el listener
            threading.Thread(
                target=self._safe_callback_wrapper(self.callback),
                daemon=True,
                name="HotkeyCallbackThread"
            ).start()

    def _safe_callback_wrapper(self, callback: Callable) -> Callable:
        """Envuelve el callback en try/except."""
        def wrapper():
            try:
                callback()
            except Exception as e:
                ulog.error("HotkeyManager", "callback", f"Error en callback de hotkey: {e}")
                import traceback
                ulog.debug("HotkeyManager", "callback", f"Traceback: {traceback.format_exc()}")
        return wrapper

    def register(self, hotkey: str, callback: Callable) -> bool:
        """
        Registrar una hotkey global de forma segura.
        """
        with self._lock:
            # Limpiar registro anterior
            if self.is_registered:
                self.unregister()

            try:
                # Normalizar y validar
                normalized = self.normalize_hotkey(hotkey)
                is_valid, error_msg = self.validate_hotkey(normalized)

                if not is_valid:
                    ulog.error("HotkeyManager", "register", f"Hotkey inválida: {error_msg}")
                    return False

                # Parsear combinación
                required_keys, _ = self._parse_combo(normalized)

                # Iniciar el listener si no está corriendo
                if self.listener is None or not self.listener.running:
                    self.listener = pynput_kb.Listener(
                        on_press=self._on_press,
                        on_release=self._on_release
                    )
                    self.listener.daemon = True  # Para que termine con el programa
                    self.listener_thread = threading.Thread(target=self.listener.start, daemon=True)
                    self.listener_thread.start()
                    # Esperar un poco para asegurar que arrancó
                    time.sleep(0.1)

                self.registered_hotkey = normalized
                self.callback = callback
                self.is_registered = True
                self._target_combo = required_keys
                self.current_pressed.clear()  # Limpiar estado por si acaso

                ulog.info("HotkeyManager", "register", f"✅ Hotkey registrada: {normalized}")
                return True

            except Exception as e:
                ulog.error("HotkeyManager", "register", f"Error registrando hotkey '{hotkey}': {e}")
                return False

    def unregister(self) -> bool:
        """
        Desregistrar la hotkey actual.
        """
        with self._lock:
            if not self.is_registered:
                return True

            try:
                self.registered_hotkey = None
                self.callback = None
                self.is_registered = False
                self._target_combo = None
                self.current_pressed.clear()
                ulog.info("HotkeyManager", "unregister", "✅ Hotkey desregistrada")
                return True
            except Exception as e:
                ulog.error("HotkeyManager", "unregister", f"Error desregistrando hotkey: {e}")
                return False

    def cleanup(self):
        """
        Limpieza completa al cerrar la aplicación.
        Detiene el listener si estaba activo.
        """
        self.unregister()
        try:
            if self.listener and self.listener.running:
                self.listener.stop()
                if self.listener_thread and self.listener_thread.is_alive():
                    self.listener_thread.join(timeout=1.0)
            self.listener = None
            ulog.info("HotkeyManager", "cleanup", "✅ Hotkey listener detenido")
        except Exception as e:
            ulog.error("HotkeyManager", "cleanup", f"Error deteniendo listener: {e}")