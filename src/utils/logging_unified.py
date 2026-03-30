"""
Sistema de logging unificado - Combina session_logger y error_logger
"""
import os
import sys
import logging
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import json
import logging.handlers


class UnifiedLogger:
    """
    Logger único para toda la aplicación:
    - Un archivo de sesión (session_YYYYMMDD_HHMMSS.log) con todos los logs
    - Un archivo de errores persistente (errors.log) con solo errores (con rotación)
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # Directorio de logs
        self.log_dir = Path.home() / ".obs_clip_manager" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Archivos de log
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.session_log = self.log_dir / f"session_{timestamp}.log"
        self.error_log = self.log_dir / "errors.log"

        # Configurar logging estándar de Python
        self._setup_standard_logging()

        # Lock para escritura thread-safe
        self._write_lock = threading.Lock()

        # Escribir cabecera de sesión
        self._write_session_header()

        self._initialized = True

    def _setup_standard_logging(self):
        """Configurar logging estándar de Python con rotación para errores."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        # Formato
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Handler para archivo de sesión (todos los niveles) - se sobrescribe cada sesión
        session_handler = logging.FileHandler(
            self.session_log, encoding='utf-8', mode='w'
        )
        session_handler.setLevel(logging.DEBUG)
        session_handler.setFormatter(formatter)
        root_logger.addHandler(session_handler)

        # Handler para archivo de errores (solo ERROR y CRITICAL) con rotación
        error_handler = logging.handlers.RotatingFileHandler(
            self.error_log,
            maxBytes=2 * 1024 * 1024,  # 2 MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)
        root_logger.addHandler(error_handler)

        # Handler para consola (INFO y superior)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    def _write_session_header(self):
        """Escribir cabecera en el archivo de sesión."""
        header = f"""
{'='*60}
SESIÓN INICIADA: {datetime.now()}
PID: {os.getpid()}
Directorio: {Path.cwd()}
{'='*60}
"""
        with self._write_lock:
            with open(self.session_log, 'a', encoding='utf-8') as f:
                f.write(header)

    # Métodos de logging específicos de la aplicación

    def trigger_start(self, trigger: str, message: str, module: str = "APP", extra: Optional[Dict] = None):
        """Registrar inicio de un trigger."""
        self._log("TRIGGER_START", module, trigger, message, extra)

    def trigger_end(self, trigger: str, message: str, module: str = "APP", extra: Optional[Dict] = None):
        """Registrar fin exitoso de un trigger."""
        self._log("TRIGGER_END", module, trigger, message, extra)

    def trigger_error(self, trigger: str, message: str, error: Exception, module: str = "APP", extra: Optional[Dict] = None):
        """Registrar error en un trigger."""
        error_str = f"{type(error).__name__}: {str(error)}"
        extra = extra or {}
        extra['error'] = error_str
        extra['traceback'] = traceback.format_exc()
        self._log("TRIGGER_ERROR", module, trigger, message, extra)

    def button_click(self, button: str, state_before: Dict, state_after: Dict, module: str = "UI"):
        """Registrar clic de botón."""
        extra = {
            'button': button,
            'state_before': state_before,
            'state_after': state_after
        }
        self._log("BUTTON_CLICK", module, button, "Botón presionado", extra)

    def obs_command(self, command: str, params: Dict, result: Any, duration_ms: float, module: str = "OBS"):
        """Registrar comando OBS."""
        extra = {
            'command': command,
            'params': params,
            'result': str(result),
            'duration_ms': duration_ms
        }
        self._log("OBS_CMD", module, command, "Comando OBS ejecutado", extra)

    def clip_flow(self, step: str, clip_info: Dict, queue_size: int, module: str = "CLIP"):
        """Registrar flujo de clip."""
        extra = {
            'step': step,
            'clip_info': clip_info,
            'queue_size': queue_size
        }
        self._log("CLIP_FLOW", module, step, f"Paso de clip: {step}", extra)

    def error(self, module: str, trigger: str, message: str, error: Optional[Exception] = None, extra: Optional[Dict] = None):
        """Registrar error."""
        if error:
            error_str = f"{type(error).__name__}: {str(error)}"
            extra = extra or {}
            extra['error'] = error_str
            extra['traceback'] = traceback.format_exc()
        self._log("ERROR", module, trigger, message, extra)

    def warning(self, module: str, trigger: str, message: str, extra: Optional[Dict] = None):
        """Registrar advertencia."""
        self._log("WARNING", module, trigger, message, extra)

    def info(self, module: str, trigger: str, message: str, extra: Optional[Dict] = None):
        """Registrar información."""
        self._log("INFO", module, trigger, message, extra)

    def debug(self, module: str, trigger: str, message: str, extra: Optional[Dict] = None):
        """Registrar debug."""
        self._log("DEBUG", module, trigger, message, extra)

    def _log(self, level: str, module: str, trigger: str, message: str, extra: Optional[Dict] = None):
        """Método interno de logging."""
        timestamp = datetime.now().isoformat(timespec='milliseconds')

        log_line = f"[{timestamp}] [{level}] [{module}] [{trigger}] {message}"

        if extra:
            log_line += f" | {json.dumps(extra, ensure_ascii=False)}"

        # Escribir directamente al archivo de sesión (además del logging estándar)
        with self._write_lock:
            try:
                with open(self.session_log, 'a', encoding='utf-8') as f:
                    f.write(log_line + '\n')
            except Exception as e:
                print(f"Error escribiendo log: {e}", file=sys.stderr)

        # También usar logging estándar para que aparezca en consola y error.log
        logger = logging.getLogger(module)
        if level == "ERROR":
            logger.error(f"[{trigger}] {message}")
        elif level == "WARNING":
            logger.warning(f"[{trigger}] {message}")
        elif level == "INFO":
            logger.info(f"[{trigger}] {message}")
        elif level == "DEBUG":
            logger.debug(f"[{trigger}] {message}")
        else:
            logger.info(f"[{level}] [{trigger}] {message}")

    def get_session_log_path(self) -> Path:
        """Obtener ruta del archivo de sesión actual."""
        return self.session_log

    def get_error_log_path(self) -> Path:
        """Obtener ruta del archivo de errores persistente."""
        return self.error_log

    def shutdown(self):
        """Cerrar logger."""
        self._log("SYSTEM", "LOGGER", "shutdown", "Logger cerrado")


# Instancia global
_logger = None


def get_logger() -> UnifiedLogger:
    """Obtener instancia única del logger."""
    global _logger
    if _logger is None:
        _logger = UnifiedLogger()
    return _logger


# Decorador para logging de funciones
def log_function(trigger_name: str = None):
    """
    Decorador para loguear entrada y salida de funciones.
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            logger = get_logger()
            module = func.__module__.split('.')[-1]
            trigger = trigger_name or func.__name__

            logger.trigger_start(trigger, f"Llamando a {func.__name__}", module)
            start = datetime.now()

            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start).total_seconds() * 1000
                logger.trigger_end(trigger, f"Función {func.__name__} completada", module,
                                  extra={'duration_ms': duration})
                return result
            except Exception as e:
                duration = (datetime.now() - start).total_seconds() * 1000
                logger.trigger_error(trigger, f"Error en {func.__name__}", e, module,
                                    extra={'duration_ms': duration})
                raise
        return wrapper
    return decorator