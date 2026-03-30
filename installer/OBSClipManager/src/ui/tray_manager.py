"""
Gestor de icono en bandeja del sistema
"""
from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction, QPixmap, QColor
from PyQt6.QtCore import QObject, pyqtSignal
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class TrayManager(QObject):
    """
    Maneja el icono de bandeja y sus acciones
    """

    show_window_requested = pyqtSignal()
    hide_window_requested = pyqtSignal()
    quit_requested = pyqtSignal()
    create_clip_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray_icon = None
        self.menu = None
        self.is_visible = False

        self._create_tray_icon()

    def _create_tray_icon(self):
        """Crear icono de bandeja"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("⚠️ Bandeja del sistema no disponible")
            return

        self.tray_icon = QSystemTrayIcon()

        # Cargar icono
        icon = self._load_icon()
        self.tray_icon.setIcon(icon)

        # Crear menú contextual
        self.menu = QMenu()

        show_action = QAction("Mostrar ventana", None)
        show_action.triggered.connect(self.show_window_requested.emit)
        self.menu.addAction(show_action)

        hide_action = QAction("Ocultar ventana", None)
        hide_action.triggered.connect(self.hide_window_requested.emit)
        self.menu.addAction(hide_action)

        self.menu.addSeparator()

        create_clip_action = QAction("Crear clip", None)
        create_clip_action.triggered.connect(self.create_clip_requested.emit)
        self.menu.addAction(create_clip_action)

        self.menu.addSeparator()

        quit_action = QAction("Salir", None)
        quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(quit_action)

        self.tray_icon.setContextMenu(self.menu)

        # Conectar activación (clic y doble clic)
        self.tray_icon.activated.connect(self._on_activated)

        logger.info("✅ Icono de bandeja creado")

    def _load_icon(self) -> QIcon:
        """Cargar icono para la bandeja"""
        icon_paths = [
            Path(__file__).parent.parent.parent / "data" / "icons" / "tray.ico",
            Path(__file__).parent.parent.parent / "data" / "icons" / "app.ico",
            Path(__file__).parent.parent.parent / "logo.ico"
        ]

        for path in icon_paths:
            if path.exists():
                logger.debug(f"Icono de bandeja encontrado: {path}")
                return QIcon(str(path))

        # Crear icono por defecto
        pixmap = QPixmap(32, 32)
        pixmap.fill(QColor("#3b82f6"))
        logger.warning("⚠️ Usando icono de bandeja por defecto")
        return QIcon(pixmap)

    def _on_activated(self, reason):
        """Manejador de activación del icono (clic o doble clic)"""
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_window_requested.emit()

    def show(self):
        """Mostrar icono en bandeja"""
        if self.tray_icon and not self.is_visible:
            self.tray_icon.show()
            self.is_visible = True
            logger.debug("Icono de bandeja mostrado")

    def hide(self):
        """Ocultar icono de bandeja"""
        if self.tray_icon and self.is_visible:
            self.tray_icon.hide()
            self.is_visible = False
            logger.debug("Icono de bandeja ocultado")

    def show_message(self, title: str, message: str, icon=QSystemTrayIcon.MessageIcon.Information, timeout=3000):
        """Mostrar notificación emergente"""
        if self.tray_icon and self.is_visible:
            self.tray_icon.showMessage(title, message, icon, timeout)

    def show_error(self, title: str, message: str, timeout=5000):
        """
        Mostrar notificación de error en la bandeja.
        Usa el ícono de advertencia/error.
        """
        self.show_message(title, message, QSystemTrayIcon.MessageIcon.Critical, timeout)

    def show_info(self, title: str, message: str, timeout=3000):
        """Mostrar notificación informativa."""
        self.show_message(title, message, QSystemTrayIcon.MessageIcon.Information, timeout)

    def set_tooltip(self, tooltip: str):
        """Establecer tooltip del icono"""
        if self.tray_icon:
            self.tray_icon.setToolTip(tooltip)

    def update_status(self, connected: bool, streaming: bool = False):
        """Actualizar icono según estado"""
        if not self.tray_icon:
            return

        pixmap = QPixmap(32, 32)
        if connected and streaming:
            pixmap.fill(QColor("#22c55e"))
            tooltip = "OBS Clip Manager - Conectado - Streaming activo"
        elif connected:
            pixmap.fill(QColor("#eab308"))
            tooltip = "OBS Clip Manager - Conectado - Streaming inactivo"
        else:
            pixmap.fill(QColor("#ef4444"))
            tooltip = "OBS Clip Manager - Desconectado"

        self.tray_icon.setIcon(QIcon(pixmap))
        self.set_tooltip(tooltip)