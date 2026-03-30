OBS Clip Manager
Versión 1.0.0

Esta aplicación permite guardar clips del Replay Buffer de OBS Studio mediante una hotkey global, con retardo configurable y organización automática de archivos.

Características:
- Hotkey global que funciona incluso en juegos a pantalla completa (usando pynput)
- Cola de tareas con retardo personalizable
- Organización de clips en carpetas por fecha
- Plantilla de nombres con tokens (fecha, hora, contador, etc.)
- Feedback sonoro opcional
- Bandeja del sistema con notificaciones

Para usar la aplicación:
1. Asegúrate de tener OBS Studio abierto con el WebSocket activado (puerto 4455 por defecto).
2. Ejecuta OBSClipManager.exe
3. Configura la hotkey y el resto de opciones en las pestañas.
4. Cuando estés en streaming, pulsa la hotkey para guardar un clip.

Requisitos del sistema:
- Windows 7 o superior (probado en Windows 10/11)
- OBS Studio con WebSocket activado (plugin integrado en versiones recientes)

Desarrollado con Python y PyQt6
