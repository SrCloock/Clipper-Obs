"""
Validadores de datos para la aplicación
"""
import os
import re
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class Validators:
    """Clase de validación de datos"""

    # Conjunto de teclas soportadas por pynput (para validación de hotkey)
    VALID_KEYS = {
        # Modificadores
        'ctrl', 'control', 'shift', 'alt', 'win', 'cmd',
        # Teclas de función
        'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12',
        # Teclas especiales
        'space', 'enter', 'esc', 'tab', 'backspace', 'delete', 'insert',
        'home', 'end', 'page_up', 'page_down', 'up', 'down', 'left', 'right',
        # Teclas alfanuméricas (letras y números)
        *[chr(i) for i in range(ord('a'), ord('z')+1)],
        *[str(i) for i in range(10)],
        # Símbolos comunes (pynput también los soporta)
        '`', '-', '=', '[', ']', '\\', ';', "'", ',', '.', '/'
    }

    @staticmethod
    def validate_obs_credentials(host: str, port: int, password: str = "") -> Tuple[bool, str]:
        """
        Validar credenciales de OBS

        Args:
            host: Host de OBS
            port: Puerto
            password: Contraseña (opcional)

        Returns:
            Tuple (válido, mensaje_error)
        """
        if not host or not host.strip():
            return False, "El host no puede estar vacío"

        if port < 1 or port > 65535:
            return False, "El puerto debe estar entre 1 y 65535"

        return True, ""

    @staticmethod
    def validate_output_path(path: str) -> Tuple[bool, str]:
        """
        Validar ruta de salida

        Args:
            path: Ruta a validar

        Returns:
            Tuple (válido, mensaje_error)
        """
        if not path or not path.strip():
            return False, "La ruta de salida no puede estar vacía"

        try:
            path_obj = Path(path)

            # Convertir a ruta absoluta si es relativa
            if not path_obj.is_absolute():
                path_obj = Path.cwd() / path_obj

            # Verificar si el directorio padre existe
            parent = path_obj.parent
            if not parent.exists():
                return False, f"El directorio padre no existe: {parent}"

            # Verificar permisos de escritura
            if not os.access(parent, os.W_OK):
                return False, f"Sin permisos de escritura en: {parent}"

            # Advertencia: longitud de ruta (Windows tiene límite de 260 caracteres,
            # pero con UNC puede ser mayor. Se lanza warning pero no se bloquea)
            if os.name == 'nt':  # Windows
                if len(str(path_obj)) > 260:
                    logger.warning(f"La ruta de salida supera los 260 caracteres: {path_obj}")

            return True, ""

        except Exception as e:
            return False, f"Ruta inválida: {str(e)}"

    @staticmethod
    def validate_hotkey(hotkey: str) -> Tuple[bool, str]:
        """
        Validar combinación de teclas para hotkey.
        Soporta teclas comunes y modificadores.

        Args:
            hotkey: Combinación a validar (ej. "ctrl+shift+c", "alt+f1", "space")

        Returns:
            Tuple (válido, mensaje_error)
        """
        if not hotkey or not hotkey.strip():
            return False, "La hotkey no puede estar vacía"

        normalized = hotkey.lower().replace(' ', '')

        # Dividir por '+'
        parts = normalized.split('+')

        # Validar que no haya partes vacías
        if not all(parts):
            return False, "Formato inválido (partes vacías)"

        # Verificar que cada parte sea una tecla conocida
        for part in parts:
            if part not in Validators.VALID_KEYS:
                return False, f"Tecla no soportada: '{part}'"

        # Verificar que haya al menos una tecla regular (no modificador)
        modifiers = {'ctrl', 'control', 'shift', 'alt', 'win', 'cmd'}
        regular_keys = [p for p in parts if p not in modifiers]

        if not regular_keys:
            return False, "Debe incluir al menos una tecla regular (no modificadora)"

        if len(regular_keys) > 1:
            return False, "Solo puede tener una tecla regular"

        return True, ""

    @staticmethod
    def validate_delay(delay: float) -> Tuple[bool, str]:
        """
        Validar delay en segundos

        Args:
            delay: Tiempo en segundos

        Returns:
            Tuple (válido, mensaje_error)
        """
        if delay < 0:
            return False, "El delay no puede ser negativo"

        if delay > 3600:  # 1 hora
            return False, "El delay no puede ser mayor a 1 hora"

        return True, ""

    @staticmethod
    def validate_volume(volume: float) -> Tuple[bool, str]:
        """
        Validar volumen

        Args:
            volume: Nivel de volumen (0.0 a 1.0)

        Returns:
            Tuple (válido, mensaje_error)
        """
        if volume < 0.0 or volume > 1.0:
            return False, "El volumen debe estar entre 0.0 y 1.0"

        return True, ""

    @staticmethod
    def validate_naming_template(template: str) -> Tuple[bool, str]:
        """
        Validar plantilla de nombres.
        Permite texto fijo y placeholders entre llaves.

        Args:
            template: Plantilla a validar

        Returns:
            Tuple (válido, mensaje_error)
        """
        if not template or not template.strip():
            return False, "La plantilla no puede estar vacía"

        # Caracteres prohibidos en nombres de archivo (Windows y Unix)
        forbidden_chars = ['<', '>', ':', '"', '|', '?', '*', '\\', '/']
        for char in forbidden_chars:
            if char in template:
                return False, f"La plantilla contiene caracteres inválidos: {char}"

        # Verificar que no tenga espacios al inicio o final (puede causar problemas)
        if template != template.strip():
            return False, "La plantilla no debe tener espacios al inicio o final"

        # Verificar que no termine con punto (algunos sistemas lo interpretan mal)
        if template.endswith('.'):
            return False, "La plantilla no puede terminar con punto"

        # Tokens válidos (los que soportará el organizador)
        valid_tokens = {
            'date', 'time', 'datetime', 'counter',
            'year', 'month', 'day', 'hour', 'minute', 'second',
            'timestamp'
        }

        # Buscar placeholders {token} y verificar que sean válidos
        import re
        pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}'
        matches = re.findall(pattern, template)
        for token in matches:
            if token not in valid_tokens:
                return False, f"Token inválido: {{{token}}}. Tokens válidos: {', '.join(sorted(valid_tokens))}"

        return True, ""

    @staticmethod
    def validate_sound_file(path: str) -> Tuple[bool, str]:
        """
        Validar que el archivo de sonido existe y es legible

        Args:
            path: Ruta al archivo de sonido

        Returns:
            Tuple (válido, mensaje_error)
        """
        if not path:
            return True, ""  # Opcional, puede estar vacío

        sound_path = Path(path)
        if not sound_path.exists():
            return False, "El archivo de sonido no existe"

        if not os.access(sound_path, os.R_OK):
            return False, "No se puede leer el archivo de sonido (permisos)"

        # Verificar extensión
        if sound_path.suffix.lower() not in ['.wav', '.mp3', '.ogg']:
            return False, "Formato de sonido no soportado (use .wav, .mp3 o .ogg)"

        return True, ""

    @staticmethod
    def validate_all_config(data: dict) -> Tuple[bool, list]:
        """
        Validar toda la configuración a la vez

        Args:
            data: Diccionario con claves de configuración

        Returns:
            (válido, lista_de_errores)
        """
        errors = []

        # OBS
        if 'host' in data or 'port' in data:
            host = data.get('host', 'localhost')
            port = data.get('port', 4455)
            valid, err = Validators.validate_obs_credentials(host, port)
            if not valid:
                errors.append(f"OBS: {err}")

        # Hotkey
        if 'hotkey' in data and data.get('hotkey_enabled', True):
            valid, err = Validators.validate_hotkey(data['hotkey'])
            if not valid:
                errors.append(f"Hotkey: {err}")

        # Clip
        if 'delay' in data:
            valid, err = Validators.validate_delay(data['delay'])
            if not valid:
                errors.append(f"Delay: {err}")
        if 'output_path' in data:
            valid, err = Validators.validate_output_path(data['output_path'])
            if not valid:
                errors.append(f"Carpeta de salida: {err}")
        if 'naming_template' in data:
            valid, err = Validators.validate_naming_template(data['naming_template'])
            if not valid:
                errors.append(f"Plantilla: {err}")

        # Audio
        if 'volume' in data:
            valid, err = Validators.validate_volume(data['volume'])
            if not valid:
                errors.append(f"Volumen: {err}")
        if 'sound_path' in data:
            valid, err = Validators.validate_sound_file(data['sound_path'])
            if not valid:
                errors.append(f"Sonido: {err}")

        return len(errors) == 0, errors