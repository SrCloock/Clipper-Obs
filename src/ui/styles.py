"""
Hoja de estilos global para la aplicación OBS Clip Manager.
Define la apariencia visual de todos los widgets.
"""

STYLESHEET = """
/* Ventana principal */
QMainWindow {
    background-color: #1e1e2e;
}

/* Widget base */
QWidget {
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 11px;
}

/* Grupos de formulario */
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 15px;
    background-color: #313244;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 8px;
    color: #89b4fa;
}

/* Etiquetas */
QLabel {
    color: #cdd6f4;
}

/* Campos de entrada */
QLineEdit, QSpinBox, QDoubleSpinBox {
    background-color: #45475a;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 5px 8px;
    color: #cdd6f4;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
    border: 1px solid #89b4fa;
}

/* Botones */
QPushButton {
    background-color: #89b4fa;
    color: #1e1e2e;
    border: none;
    border-radius: 5px;
    padding: 6px 12px;
    font-weight: 500;
}

QPushButton:hover {
    background-color: #b4befe;
}

QPushButton:pressed {
    background-color: #74c7ec;
}

QPushButton:disabled {
    background-color: #585b70;
    color: #6c7086;
}

/* Checkboxes */
QCheckBox {
    spacing: 6px;
    color: #cdd6f4;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border-radius: 3px;
    border: 1px solid #585b70;
    background-color: #45475a;
}

QCheckBox::indicator:checked {
    background-color: #89b4fa;
    border-color: #89b4fa;
    image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTAiIGhlaWdodD0iMTAiIHZpZXdCb3g9IjAgMCAxMCAxMCIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cGF0aCBkPSJNOC41IDNMMy43NSA4TDEuNSA1LjUiIHN0cm9rZT0iIzFlMWUyZSIgc3Ryb2tlLXdpZHRoPSIxLjUiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPjwvc3ZnPg==);
}

/* Pestañas */
QTabWidget::pane {
    border: 1px solid #45475a;
    border-radius: 6px;
    background-color: #313244;
    margin-top: 4px;
}

QTabBar::tab {
    background-color: #45475a;
    color: #cdd6f4;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #313244;
    color: #89b4fa;
    border-bottom: 2px solid #89b4fa;
}

QTabBar::tab:hover:!selected {
    background-color: #585b70;
}

/* Lista de clips recientes (corregido: fondo oscuro y texto claro) */
QListWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    outline: none;
    selection-background-color: #89b4fa;
    selection-color: #1e1e2e;
}

QListWidget::item {
    padding: 6px;
    border-bottom: 1px solid #313244;
}

QListWidget::item:selected {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QListWidget::item:hover {
    background-color: #45475a;
}

/* Barra de estado */
QStatusBar {
    background-color: #313244;
    color: #a6adc8;
    border-top: 1px solid #45475a;
}

/* Barra de progreso (utilizada en StatusFrame) */
QProgressBar {
    border: 1px solid #45475a;
    border-radius: 4px;
    background-color: #313244;
    text-align: center;
    color: #cdd6f4;
}

QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 3px;
}

/* Slider de volumen */
QSlider::groove:horizontal {
    height: 6px;
    background: #45475a;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background: #89b4fa;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 8px;
}

QSlider::handle:horizontal:hover {
    background: #b4befe;
}
"""