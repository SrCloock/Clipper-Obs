"""
Gestor de reintentos con backoff exponencial y jitter.
Reintenta tanto si la función lanza excepción como si devuelve un valor falsy (False/None).
"""

import time
import random
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class RetryManager:
    """
    Gestor de reintentos con backoff exponencial y jitter.
    
    Útil para operaciones que pueden fallar transitoriamente, como conexiones de red.
    """

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        """
        Args:
            max_retries: Número máximo de reintentos (sin contar el primer intento)
            base_delay: Retardo base en segundos
            max_delay: Retardo máximo en segundos
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.retry_count = 0

    def should_retry(self) -> bool:
        """Determina si aún se puede reintentar."""
        return self.retry_count < self.max_retries

    def get_next_delay(self) -> float:
        """
        Calcula el próximo retardo con backoff exponencial y jitter.
        """
        if self.retry_count == 0:
            delay = self.base_delay
        else:
            delay = self.base_delay * (2 ** (self.retry_count - 1))

        # Añadir jitter aleatorio (±10%)
        jitter = random.uniform(0.9, 1.1)
        delay = delay * jitter

        # Limitar al máximo
        delay = min(delay, self.max_delay)

        self.retry_count += 1
        return delay

    def wait(self) -> bool:
        """
        Espera el tiempo calculado y devuelve True si aún hay reintentos,
        False si ya no quedan.
        """
        if self.should_retry():
            delay = self.get_next_delay()
            logger.info(f"Reintento {self.retry_count}/{self.max_retries} en {delay:.2f}s")
            time.sleep(delay)
            return True
        return False

    def reset(self) -> None:
        """Reinicia el contador de reintentos."""
        self.retry_count = 0
        logger.debug("Contador de reintentos reiniciado")

    def execute_with_retry(self, func: Callable, *args, **kwargs) -> Any:
        """
        Ejecuta una función con reintentos automáticos.
        
        Considera éxito si la función devuelve un valor truthy (True, objeto, etc.).
        Considera fallo si la función:
          - Lanza una excepción, o
          - Devuelve un valor falsy (False, None, 0, "", []...)

        Args:
            func: Función a ejecutar
            *args, **kwargs: Argumentos para la función

        Returns:
            El valor devuelto por la función (que será truthy)

        Raises:
            La última excepción capturada, o una excepción genérica si
            todos los reintentos fallaron sin excepción.
        """
        self.reset()
        last_exception = None

        while self.should_retry():
            try:
                result = func(*args, **kwargs)
                # Éxito si el resultado es truthy
                if result:
                    logger.info(f"Función ejecutada exitosamente en el intento {self.retry_count + 1}")
                    return result
                else:
                    logger.warning(f"Intento {self.retry_count + 1} devolvió {result}, reintentando...")
                    last_exception = Exception(f"Función devolvió {result}")
            except Exception as e:
                logger.warning(f"Intento {self.retry_count + 1} falló con excepción: {e}")
                last_exception = e

            if not self.wait():
                break

        # Si llegamos aquí, todos los reintentos fallaron
        if last_exception:
            logger.error(f"Todos los reintentos fallaron para {func.__name__}. Último error: {last_exception}")
            raise last_exception
        else:
            error_msg = f"Número máximo de reintentos alcanzado sin éxito para {func.__name__}"
            logger.error(error_msg)
            raise Exception(error_msg)