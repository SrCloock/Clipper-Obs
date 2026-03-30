"""
Gestor de reintentos con backoff exponencial
"""
import time
import random
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class RetryManager:
    """Gestor de reintentos con backoff exponencial y jitter."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        """
        Args:
            max_retries: Número máximo de reintentos
            base_delay: Retardo base en segundos
            max_delay: Retardo máximo en segundos
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retry_count = 0

    def should_retry(self) -> bool:
        """Determinar si se debe reintentar."""
        return self.retry_count < self.max_retries

    def get_next_delay(self) -> float:
        """
        Calcular el próximo retardo con backoff exponencial y jitter.
        Si es el primer reintento, usa base_delay.
        """
        if self.retry_count == 0:
            delay = self.base_delay
        else:
            # Backoff exponencial: base_delay * 2^(retry_count-1)
            delay = self.base_delay * (2 ** (self.retry_count - 1))

        # Agregar jitter aleatorio (±10%)
        jitter = random.uniform(0.9, 1.1)
        delay = delay * jitter

        # Limitar al máximo
        delay = min(delay, self.max_delay)

        self.retry_count += 1
        return delay

    def wait(self) -> bool:
        """
        Esperar el tiempo calculado y devolver True si aún hay reintentos,
        False si ya no quedan.
        """
        if self.should_retry():
            delay = self.get_next_delay()
            logger.info(f"Reintento {self.retry_count}/{self.max_retries} en {delay:.2f}s")
            time.sleep(delay)
            return True
        return False

    def reset(self) -> None:
        """Reiniciar contador de reintentos."""
        self.retry_count = 0
        logger.debug("Contador de reintentos reiniciado")

    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Optional[Any]:
        """
        Ejecutar función con reintentos automáticos.

        Args:
            func: Función a ejecutar (debe devolver True/False o levantar excepción para indicar fallo)
            *args: Argumentos posicionales
            **kwargs: Argumentos clave

        Returns:
            Resultado de la función si tiene éxito, None si todos los reintentos fallan.
        """
        self.reset()

        while self.should_retry():
            try:
                result = func(*args, **kwargs)
                logger.info(f"Función ejecutada exitosamente en el intento {self.retry_count + 1}")
                return result
            except Exception as e:
                logger.warning(f"Intento {self.retry_count + 1} falló: {e}")
                if not self.wait():
                    logger.error(f"Todos los reintentos fallaron para {func.__name__}")
                    raise
        return None