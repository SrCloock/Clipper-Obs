"""
Componentes UI reutilizables para la ventana principal de OBS Clip Manager.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QLineEdit, QSpinBox, QDoubleSpinBox,
    QCheckBox, QSlider, QFormLayout, QFileDialog, QKeySequenceEdit,
    QMessageBox, QListWidget, QListWidgetItem, QApplication, QDialog,
    QDialogButtonBox, QTextEdit
)
from PyQt6.QtCore import Qt, pyqtSignal, QUrl
from PyQt6.QtGui import QKeySequence, QDesktopServices
import logging
from pathlib import Path
from typing import Dict, Any, List

from src.utils.validators import Validators

logger = logging.getLogger(__name__)


class StatusFrame(QGroupBox):
    """Panel de estado de la aplicación y OBS."""

    def __init__(self):
        super().__init__("Estado")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Estado de la aplicación
        self.app_state_label = QLabel("Estado de la aplicación: Inicializando...")
        self.app_state_label.setStyleSheet("color: orange; font-weight: bold;")
        layout.addWidget(self.app_state_label)

        # Estados específicos de OBS
        status_row = QHBoxLayout()
        self.obs_status_label = QLabel("OBS: Desconectado")
        self.obs_status_label.setStyleSheet("color: #ef4444;")
        status_row.addWidget(self.obs_status_label)

        self.replay_status_label = QLabel("Replay: Inactivo")
        self.replay_status_label.setStyleSheet("color: #ef4444;")
        status_row.addWidget(self.replay_status_label)

        self.stream_status_label = QLabel("Streaming: Inactivo")
        self.stream_status_label.setStyleSheet("color: #ef4444;")
        status_row.addWidget(self.stream_status_label)

        layout.addLayout(status_row)

        # Cola de clips
        queue_row = QHBoxLayout()
        queue_row.addWidget(QLabel("Clips en cola:"))
        self.queue_size_label = QLabel("0")
        self.queue_size_label.setStyleSheet("font-weight: bold;")
        queue_row.addWidget(self.queue_size_label)
        queue_row.addStretch()
        layout.addLayout(queue_row)

        self.setLayout(layout)

    def update_app_state(self, state_name: str):
        """Actualiza el estado general de la aplicación."""
        self.app_state_label.setText(f"Estado de la aplicación: {state_name}")
        if state_name == "CONNECTED":
            self.app_state_label.setStyleSheet("color: #22c55e; font-weight: bold;")
        elif state_name in ("ERROR", "DISCONNECTED"):
            self.app_state_label.setStyleSheet("color: #ef4444; font-weight: bold;")
        else:
            self.app_state_label.setStyleSheet("color: #eab308; font-weight: bold;")

    def update_obs_status(self, status: dict):
        """
        Actualiza los indicadores de OBS.

        Args:
            status: Diccionario con claves 'connected', 'is_streaming', 'replay_active'.
        """
        connected = status.get('connected', False)
        streaming = status.get('is_streaming', False)
        replay = status.get('replay_active', False)

        if connected:
            self.obs_status_label.setText("OBS: Conectado")
            self.obs_status_label.setStyleSheet("color: #22c55e;")
        else:
            self.obs_status_label.setText("OBS: Desconectado")
            self.obs_status_label.setStyleSheet("color: #ef4444;")

        if streaming:
            self.stream_status_label.setText("Streaming: Activo")
            self.stream_status_label.setStyleSheet("color: #22c55e;")
        else:
            self.stream_status_label.setText("Streaming: Inactivo")
            self.stream_status_label.setStyleSheet("color: #ef4444;")

        if replay:
            self.replay_status_label.setText("Replay: Activo")
            self.replay_status_label.setStyleSheet("color: #22c55e;")
        else:
            self.replay_status_label.setText("Replay: Inactivo")
            self.replay_status_label.setStyleSheet("color: #ef4444;")

    def update_queue_status(self, queue_size: int):
        """Actualiza el tamaño de la cola de clips."""
        self.queue_size_label.setText(str(queue_size))


class OBSConfigTab(QWidget):
    """Pestaña de configuración de conexión OBS."""

    config_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.connect_signals()
        self._current_values = {}  # Almacenar valores para revertir si falla validación

    def setup_ui(self):
        layout = QFormLayout()

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("localhost")
        layout.addRow("Host:", self.host_edit)

        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(4455)
        layout.addRow("Puerto:", self.port_spin)

        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_edit.setPlaceholderText("(opcional)")
        layout.addRow("Contraseña:", self.password_edit)

        self.reconnect_spin = QSpinBox()
        self.reconnect_spin.setRange(1, 60)
        self.reconnect_spin.setSuffix(" seg")
        self.reconnect_spin.setValue(5)
        layout.addRow("Reconectar cada:", self.reconnect_spin)

        self.setLayout(layout)

    def connect_signals(self):
        self.host_edit.editingFinished.connect(self._on_change)
        self.port_spin.valueChanged.connect(self._on_change)
        self.password_edit.editingFinished.connect(self._on_change)
        self.reconnect_spin.valueChanged.connect(self._on_change)

    def _validate(self) -> tuple[bool, str]:
        """Valida los datos actuales del formulario."""
        host = self.host_edit.text().strip()
        port = self.port_spin.value()
        password = self.password_edit.text()

        is_valid, error = Validators.validate_obs_credentials(host, port, password)
        if not is_valid:
            return False, error
        return True, ""

    def _on_change(self):
        # Validar antes de emitir
        valid, error = self._validate()
        if not valid:
            # Mostrar tooltip temporal en el campo correspondiente
            self.host_edit.setToolTip(error)
            self.host_edit.setStyleSheet("border: 1px solid #ef4444;")
            # No emitir señal si es inválido
            return
        else:
            self.host_edit.setToolTip("")
            self.host_edit.setStyleSheet("")
            self.port_spin.setStyleSheet("")
        self.config_changed.emit(self.get_config_data())

    def get_config_data(self) -> dict:
        return {
            'host': self.host_edit.text().strip() or "localhost",
            'port': self.port_spin.value(),
            'password': self.password_edit.text(),
            'reconnect_interval': self.reconnect_spin.value()
        }

    def load_config(self, obs_config):
        self.host_edit.setText(obs_config.host)
        self.port_spin.setValue(obs_config.port)
        self.password_edit.setText(obs_config.password)
        self.reconnect_spin.setValue(obs_config.reconnect_interval)


class HotkeyConfigTab(QWidget):
    """Pestaña de configuración de la hotkey con botón de grabación."""

    config_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QVBoxLayout()

        self.enable_check = QCheckBox("Habilitar hotkey")
        layout.addWidget(self.enable_check)

        hotkey_group = QGroupBox("Combinación de teclas")
        h_layout = QHBoxLayout()

        # Campo de texto que muestra la combinación actual (solo lectura)
        self.hotkey_display = QLineEdit()
        self.hotkey_display.setReadOnly(True)
        self.hotkey_display.setPlaceholderText("No configurada")
        h_layout.addWidget(self.hotkey_display)

        # Botón para grabar nueva combinación
        self.record_button = QPushButton("Grabar hotkey")
        self.record_button.setToolTip("Haz clic y luego presiona la combinación de teclas deseada")
        h_layout.addWidget(self.record_button)

        hotkey_group.setLayout(h_layout)
        layout.addWidget(hotkey_group)

        layout.addStretch()
        self.setLayout(layout)

    def connect_signals(self):
        self.enable_check.toggled.connect(self._on_change)
        self.record_button.clicked.connect(self._record_hotkey)

    def _record_hotkey(self):
        """Abre un diálogo modal para capturar una combinación de teclas."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Grabar hotkey")
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        label = QLabel("Presiona la combinación de teclas que deseas usar...\n(Presiona la combinación, luego haz clic en Aceptar)")
        label.setWordWrap(True)
        layout.addWidget(label)

        # QKeySequenceEdit temporal
        key_edit = QKeySequenceEdit()
        key_edit.setKeySequence(QKeySequence(self.hotkey_display.text()))
        layout.addWidget(key_edit)

        # Botones
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)

        # Enfoque inicial en el editor de teclas
        key_edit.setFocus()

        if dialog.exec() == QDialog.DialogCode.Accepted:
            seq = key_edit.keySequence().toString(QKeySequence.SequenceFormat.NativeText)
            if seq:
                # Validar la combinación
                is_valid, error = Validators.validate_hotkey(seq.lower())
                if is_valid:
                    self.hotkey_display.setText(seq)
                    self._on_change()
                else:
                    QMessageBox.warning(self, "Hotkey inválida", error)
            else:
                QMessageBox.warning(self, "Hotkey inválida", "No se ha especificado ninguna combinación")

    def _validate(self) -> tuple[bool, str]:
        """Valida la combinación de teclas."""
        if not self.enable_check.isChecked():
            return True, ""  # No es necesario validar si está deshabilitado
        seq = self.hotkey_display.text().strip()
        if not seq:
            return False, "No se ha especificado ninguna combinación"
        is_valid, error = Validators.validate_hotkey(seq.lower())
        return is_valid, error

    def _on_change(self):
        valid, error = self._validate()
        if not valid:
            self.hotkey_display.setToolTip(error)
            self.hotkey_display.setStyleSheet("border: 1px solid #ef4444;")
            # No emitir
            return
        else:
            self.hotkey_display.setToolTip("")
            self.hotkey_display.setStyleSheet("")
        self.config_changed.emit(self.get_config_data())

    def get_config_data(self) -> dict:
        seq = self.hotkey_display.text().strip()
        return {
            'hotkey': seq,
            'hotkey_enabled': self.enable_check.isChecked()
        }

    def load_config(self, hotkey_config):
        self.enable_check.setChecked(hotkey_config.enabled)
        if hotkey_config.key_combination:
            self.hotkey_display.setText(hotkey_config.key_combination)
        else:
            self.hotkey_display.setText("")


class HelpDialog(QDialog):
    """Diálogo de ayuda con los tokens disponibles para la plantilla de nombres."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ayuda: Tokens para nombres de clips")
        self.setMinimumSize(400, 300)
        layout = QVBoxLayout(self)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setPlainText("""
Los siguientes tokens pueden usarse en la plantilla de nombres:

{date}       → Fecha completa: AAAA-MM-DD (ej. 2026-03-29)
{time}       → Hora-minuto-segundo: HH-MM-SS (ej. 14-30-45)
{datetime}   → Combinación: AAAA-MM-DD_HH-MM-SS
{year}       → Año (ej. 2026)
{month}      → Mes (ej. 03)
{day}        → Día del mes (ej. 29)
{hour}       → Hora (ej. 14)
{minute}     → Minuto (ej. 30)
{second}     → Segundo (ej. 45)
{counter}    → Contador por sesión (se incrementa cada clip)

Además, puedes incluir texto fijo y separadores. Ejemplos:
- "Stream_{date}_{time}" → Stream_2026-03-29_14-30-45.mp4
- "Clip_{counter}" → Clip_1.mp4, Clip_2.mp4, ...
- "{year}-{month}-{day}_{hour}{minute}" → 2026-03-29_1430.mp4

Si dos clips generan el mismo nombre, se añadirá automáticamente _1, _2, etc.
        """.strip())
        layout.addWidget(text)

        btn = QPushButton("Cerrar")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn)


class ClipConfigTab(QWidget):
    """Pestaña de configuración de los clips con plantilla personalizable y timeout."""

    config_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QFormLayout()

        # Delay
        self.delay_spin = QDoubleSpinBox()
        self.delay_spin.setRange(0.0, 3600.0)
        self.delay_spin.setSuffix(" seg")
        self.delay_spin.setValue(5.0)
        layout.addRow("Delay:", self.delay_spin)

        # Timeout de archivo (nuevo)
        self.file_timeout_spin = QDoubleSpinBox()
        self.file_timeout_spin.setRange(5.0, 60.0)
        self.file_timeout_spin.setSuffix(" seg")
        self.file_timeout_spin.setValue(15.0)
        self.file_timeout_spin.setToolTip("Tiempo máximo para esperar que el archivo del clip esté listo después de guardarlo")
        layout.addRow("Timeout de archivo:", self.file_timeout_spin)

        # Carpeta de salida
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(str(Path.home() / "Videos" / "OBS Clips"))
        path_layout.addWidget(self.path_edit)
        self.browse_button = QPushButton("Examinar...")
        path_layout.addWidget(self.browse_button)
        layout.addRow("Carpeta de salida:", path_layout)

        # Plantilla de nombres con botón de ayuda
        template_layout = QHBoxLayout()
        self.template_edit = QLineEdit()
        self.template_edit.setPlaceholderText("{date}_{time}_{counter}")
        template_layout.addWidget(self.template_edit)
        self.help_button = QPushButton("?")
        self.help_button.setFixedSize(24, 24)
        self.help_button.setToolTip("Ayuda sobre tokens")
        template_layout.addWidget(self.help_button)
        layout.addRow("Plantilla:", template_layout)

        # Tamaño de cola
        self.queue_spin = QSpinBox()
        self.queue_spin.setRange(1, 100)
        self.queue_spin.setSuffix(" clips")
        self.queue_spin.setValue(10)
        layout.addRow("Cola máxima:", self.queue_spin)

        self.setLayout(layout)

    def connect_signals(self):
        self.delay_spin.valueChanged.connect(self._on_change)
        self.file_timeout_spin.valueChanged.connect(self._on_change)
        self.path_edit.editingFinished.connect(self._on_change)
        self.browse_button.clicked.connect(self._browse_folder)
        self.template_edit.editingFinished.connect(self._on_change)
        self.help_button.clicked.connect(self._show_help)
        self.queue_spin.valueChanged.connect(self._on_change)

    def _validate(self) -> tuple[bool, str]:
        """Valida todos los campos."""
        # Validar delay
        delay = self.delay_spin.value()
        valid, error = Validators.validate_delay(delay)
        if not valid:
            return False, error

        # Validar ruta de salida
        path = self.path_edit.text().strip()
        valid, error = Validators.validate_output_path(path)
        if not valid:
            return False, error

        # Validar plantilla
        template = self.template_edit.text().strip()
        valid, error = Validators.validate_naming_template(template)
        if not valid:
            return False, error

        return True, ""

    def _on_change(self):
        valid, error = self._validate()
        if not valid:
            # Marcar el campo correspondiente (opcional)
            if "delay" in error.lower():
                self.delay_spin.setStyleSheet("border: 1px solid #ef4444;")
            else:
                self.delay_spin.setStyleSheet("")
            if "ruta" in error.lower():
                self.path_edit.setStyleSheet("border: 1px solid #ef4444;")
            else:
                self.path_edit.setStyleSheet("")
            if "plantilla" in error.lower():
                self.template_edit.setStyleSheet("border: 1px solid #ef4444;")
            else:
                self.template_edit.setStyleSheet("")
            # Mostrar tooltip (podría ser un label, pero simplificamos)
            self.setToolTip(error)
            return
        else:
            self.delay_spin.setStyleSheet("")
            self.path_edit.setStyleSheet("")
            self.template_edit.setStyleSheet("")
            self.setToolTip("")

        self.config_changed.emit(self.get_config_data())

    def _browse_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida")
        if folder:
            self.path_edit.setText(folder)
            self._on_change()

    def _show_help(self):
        """Muestra el diálogo de ayuda con los tokens."""
        dlg = HelpDialog(self)
        dlg.exec()

    def get_config_data(self) -> dict:
        return {
            'delay': self.delay_spin.value(),
            'file_timeout': self.file_timeout_spin.value(),
            'output_path': self.path_edit.text() or str(Path.home() / "Videos" / "OBS Clips"),
            'naming_template': self.template_edit.text() or "{date}_{time}_{counter}",
            'max_queue_size': self.queue_spin.value()
        }

    def load_config(self, clip_config):
        self.delay_spin.setValue(clip_config.delay_seconds)
        self.file_timeout_spin.setValue(getattr(clip_config, 'file_timeout', 15.0))
        self.path_edit.setText(clip_config.output_path)
        self.template_edit.setText(clip_config.naming_template)
        self.queue_spin.setValue(clip_config.max_queue_size)


class AudioConfigTab(QWidget):
    """Pestaña de configuración del audio de feedback."""

    config_changed = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.connect_signals()

    def setup_ui(self):
        layout = QFormLayout()

        self.enable_check = QCheckBox("Habilitar sonido de feedback")
        layout.addRow(self.enable_check)

        volume_layout = QHBoxLayout()
        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(70)
        self.volume_label = QLabel("70%")
        volume_layout.addWidget(self.volume_slider)
        volume_layout.addWidget(self.volume_label)
        layout.addRow("Volumen:", volume_layout)

        sound_layout = QHBoxLayout()
        self.sound_path_edit = QLineEdit()
        self.sound_path_edit.setPlaceholderText("(usar sonido por defecto)")
        sound_layout.addWidget(self.sound_path_edit)
        self.sound_browse_button = QPushButton("Examinar...")
        sound_layout.addWidget(self.sound_browse_button)
        layout.addRow("Archivo de sonido:", sound_layout)

        self.setLayout(layout)

    def connect_signals(self):
        self.enable_check.toggled.connect(self._on_change)
        self.volume_slider.valueChanged.connect(self._on_volume_change)
        self.sound_path_edit.editingFinished.connect(self._on_change)
        self.sound_browse_button.clicked.connect(self._browse_sound)

    def _validate(self) -> tuple[bool, str]:
        """Valida volumen (y opcionalmente ruta de archivo si existe)."""
        volume = self.volume_slider.value() / 100.0
        valid, error = Validators.validate_volume(volume)
        if not valid:
            return False, error
        # Si se especificó un archivo, comprobar que existe (opcional)
        sound_path = self.sound_path_edit.text().strip()
        if sound_path:
            from pathlib import Path
            if not Path(sound_path).exists():
                return False, "El archivo de sonido no existe"
        return True, ""

    def _on_change(self):
        valid, error = self._validate()
        if not valid:
            # Mostrar error en el slider o campo
            self.volume_slider.setToolTip(error)
            self.sound_path_edit.setToolTip(error)
            self.sound_path_edit.setStyleSheet("border: 1px solid #ef4444;")
            return
        else:
            self.volume_slider.setToolTip("")
            self.sound_path_edit.setToolTip("")
            self.sound_path_edit.setStyleSheet("")
        self.config_changed.emit(self.get_config_data())

    def _on_volume_change(self, value):
        self.volume_label.setText(f"{value}%")
        self._on_change()

    def _browse_sound(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar archivo de sonido",
            str(Path.home()),
            "Archivos de audio (*.wav *.mp3 *.ogg)"
        )
        if file_path:
            self.sound_path_edit.setText(file_path)
            self._on_change()

    def get_config_data(self) -> dict:
        return {
            'audio_enabled': self.enable_check.isChecked(),
            'volume': self.volume_slider.value() / 100.0,
            'sound_path': self.sound_path_edit.text()
        }

    def load_config(self, audio_config):
        self.enable_check.setChecked(audio_config.enabled)
        self.volume_slider.setValue(int(audio_config.volume * 100))
        self.volume_label.setText(f"{int(audio_config.volume * 100)}%")
        self.sound_path_edit.setText(audio_config.sound_path)


class ActionButtons(QWidget):
    """Botones de acción global en la parte inferior de la ventana."""

    create_clip_clicked = pyqtSignal()
    test_sound_clicked = pyqtSignal()
    hide_to_tray_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setup_ui()

    def setup_ui(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 5, 0, 5)

        self.create_button = QPushButton("🎬 Crear clip ahora")
        self.create_button.setEnabled(False)
        layout.addWidget(self.create_button)

        self.test_sound_button = QPushButton("🔊 Probar sonido")
        layout.addWidget(self.test_sound_button)

        layout.addStretch()

        self.hide_button = QPushButton("🗕 Ocultar a bandeja")
        layout.addWidget(self.hide_button)

        self.setLayout(layout)

        self.create_button.clicked.connect(self.create_clip_clicked.emit)
        self.test_sound_button.clicked.connect(self.test_sound_clicked.emit)
        self.hide_button.clicked.connect(self.hide_to_tray_clicked.emit)

    def set_create_clip_enabled(self, enabled: bool):
        self.create_button.setEnabled(enabled)


# ============================================================================
# PESTAÑA: CLIPS RECIENTES
# ============================================================================

class RecentClipsTab(QWidget):
    """
    Pestaña que muestra los clips recientemente guardados.
    Permite abrir la carpeta que contiene el clip y ver detalles.
    """
    refresh_requested = pyqtSignal()  # Señal para pedir actualización de la lista

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.clips_data = []  # Almacenar los datos para poder abrir carpetas

    def setup_ui(self):
        layout = QVBoxLayout()

        # Botón de refrescar
        refresh_layout = QHBoxLayout()
        self.refresh_button = QPushButton("🔄 Refrescar")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        refresh_layout.addWidget(self.refresh_button)
        refresh_layout.addStretch()
        layout.addLayout(refresh_layout)

        # Lista de clips
        self.clip_list = QListWidget()
        self.clip_list.setAlternatingRowColors(True)
        self.clip_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.clip_list)

        # Botón para abrir carpeta del clip seleccionado
        button_layout = QHBoxLayout()
        self.open_folder_button = QPushButton("📂 Abrir carpeta del clip")
        self.open_folder_button.clicked.connect(self._open_selected_folder)
        button_layout.addWidget(self.open_folder_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)

        self.setLayout(layout)

    def update_recent_clips(self, clips: List[Dict[str, Any]]):
        """
        Actualiza la lista con los clips recibidos.
        Cada diccionario debe contener al menos:
            - 'name': nombre del archivo
            - 'path': ruta completa
            - 'size_mb': tamaño en MB
            - 'date': fecha (YYYY-MM-DD)
            - 'modified': timestamp de modificación (opcional)
        """
        self.clips_data = clips
        self.clip_list.clear()

        for clip in clips:
            name = clip.get('name', 'desconocido')
            size = clip.get('size_mb', 0)
            date = clip.get('date', '')
            modified = clip.get('modified', 0)

            # Formatear fecha legible
            from datetime import datetime
            if modified:
                date_str = datetime.fromtimestamp(modified).strftime("%Y-%m-%d %H:%M")
            else:
                date_str = date

            text = f"{name}  |  {size:.1f} MB  |  {date_str}"
            item = QListWidgetItem(text)
            # Guardar la ruta completa como data del item
            item.setData(Qt.ItemDataRole.UserRole, clip.get('path', ''))
            self.clip_list.addItem(item)

        if clips:
            self.clip_list.setCurrentRow(0)

    def _on_item_double_clicked(self, item):
        """Abrir el clip cuando se hace doble clic (abrir con el programa asociado)."""
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            QMessageBox.warning(self, "No se puede abrir", "El archivo ya no existe o la ruta no es válida.")

    def _open_selected_folder(self):
        """Abrir la carpeta que contiene el clip seleccionado."""
        current_item = self.clip_list.currentItem()
        if not current_item:
            QMessageBox.information(self, "Ningún clip seleccionado", "Selecciona un clip de la lista.")
            return

        path = current_item.data(Qt.ItemDataRole.UserRole)
        if path and Path(path).exists():
            folder = str(Path(path).parent)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        else:
            QMessageBox.warning(self, "Carpeta no encontrada", "La carpeta del clip no existe.")