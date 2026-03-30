STYLESHEET = """
QMainWindow {
    background-color: #1e1e2e;
}

QWidget {
    color: #cdd6f4;
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 11px;
}

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

QLabel {
    color: #cdd6f4;
}

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

QStatusBar {
    background-color: #313244;
    color: #a6adc8;
    border-top: 1px solid #45475a;
}

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