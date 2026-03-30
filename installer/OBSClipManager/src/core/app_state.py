"""
Estados de la aplicación
"""
from enum import Enum, auto

class AppState(Enum):
    """Estados posibles de la aplicación"""
    INIT = auto()               # Inicializando
    CONNECTING_TO_OBS = auto()  # Conectando a OBS
    CONNECTED = auto()          # Conectado y listo
    DISCONNECTED = auto()       # Desconectado de OBS
    ERROR = auto()              # Error crítico
    SAVING_CLIP = auto()        # Guardando clip
    PROCESSING_QUEUE = auto()   # Procesando cola