#!/usr/bin/env python3
"""
OBS Clip Manager - Aplicación principal (VERSIÓN FINAL CON MEJORAS)
"""

import sys
import signal
import traceback
import threading
from pathlib import Path

# Agregar src al path
src_path = Path(__file__).parent / 'src'
sys.path.insert(0, str(src_path))

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon

# Importar logger unificado
from src.utils.logging_unified import get_logger

# ============================================================================
# MANEJADORES DE EXCEPCIONES GLOBALES
# ============================================================================

def thread_exception_handler(args):
    """Manejador de excepciones en hilos"""
    logger = get_logger()
    
    # Extraer información del traceback
    if hasattr(args, 'exc_type'):
        exc_type = args.exc_type
        exc_value = args.exc_value
        exc_traceback = args.exc_traceback
    else:
        exc_type = type(args.exc_value)
        exc_value = args.exc_value
        exc_traceback = args.exc_value.__traceback__
    
    tb_info = traceback.extract_tb(exc_traceback)
    if tb_info:
        last_frame = tb_info[-1]
        module = Path(last_frame.filename).name
        line = last_frame.lineno
        trigger = f"thread_line_{line}"
    else:
        module = "unknown_thread"
        trigger = "unhandled_thread_exception"
    
    # Registrar el error
    logger.error(module, trigger, f"Excepción en hilo", exc_value)
    
    print(f"\n❌ ERROR EN HILO:", file=sys.stderr)
    print(f"   Módulo: {module}", file=sys.stderr)
    print(f"   Trigger: {trigger}", file=sys.stderr)
    print(f"   Error: {exc_type.__name__}: {exc_value}", file=sys.stderr)
    
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)

# Configurar handler para excepciones en hilos
threading.excepthook = thread_exception_handler

def global_exception_handler(exc_type, exc_value, exc_traceback):
    """Captura TODAS las excepciones no capturadas"""
    logger = get_logger()
    
    # Extraer información del traceback
    tb_info = traceback.extract_tb(exc_traceback)
    if tb_info:
        last_frame = tb_info[-1]
        module = Path(last_frame.filename).name
        line = last_frame.lineno
        trigger = f"linea_{line}"
    else:
        module = "unknown"
        trigger = "unhandled_exception"
    
    # Registrar el error
    logger.error(module, trigger, f"Excepción no capturada", exc_value)
    
    # También mostrar en consola
    print(f"\n❌ ERROR NO CAPTURADO:", file=sys.stderr)
    print(f"   Módulo: {module}", file=sys.stderr)
    print(f"   Trigger: {trigger}", file=sys.stderr)
    print(f"   Error: {exc_type.__name__}: {exc_value}", file=sys.stderr)
    
    # Mostrar traceback completo
    traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
    
    # Llamar al handler por defecto
    sys.__excepthook__(exc_type, exc_value, exc_traceback)

# Configurar el handler global
sys.excepthook = global_exception_handler

def signal_handler(signum, frame):
    """Manejador para Ctrl+C"""
    print("\nCtrl+C detectado. Cerrando aplicación...")
    QApplication.quit()

def create_default_icon():
    """Crear un icono por defecto si no existe logo.ico"""
    try:
        from PIL import Image, ImageDraw
        
        icon_path = Path(__file__).parent / "logo.ico"
        if not icon_path.exists():
            # Crear un icono simple con PIL
            img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # Dibujar un círculo rojo (grabación)
            draw.ellipse([50, 50, 206, 206], fill=(255, 0, 0, 255))
            draw.ellipse([70, 70, 186, 186], fill=(0, 0, 0, 0))
            
            # Guardar como .ico
            img.save('logo.ico', format='ICO', sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
            print("Icono por defecto creado: logo.ico")
    except ImportError:
        print("PIL no disponible, usando icono por defecto de Qt")
    except Exception as e:
        print(f"No se pudo crear icono: {e}")

def check_dependencies():
    """Verificar dependencias críticas"""
    dependencies = [
        ("PyQt6", "PyQt6"),
        ("obsws_python", "obsws_python"),
        ("pynput", "pynput"),          # Reemplaza a keyboard
        ("pygame", "pygame"),
        ("PIL", "PIL"),                 # Pillow para el icono
    ]
    
    missing = []
    for name, module in dependencies:
        try:
            __import__(module)
            print(f"✓ {name}")
        except ImportError:
            print(f"✗ {name} - NO INSTALADO")
            missing.append(name)
    
    if missing:
        error_msg = f"Dependencias faltantes: {', '.join(missing)}"
        
        # Intentar mostrar ventana de error
        try:
            app = QApplication.instance() or QApplication(sys.argv)
            QMessageBox.critical(
                None,
                "Dependencias faltantes",
                f"Faltan las siguientes dependencias:\n\n" +
                "\n".join(f"• {name}" for name in missing) +
                f"\n\nInstala con:\npip install {' '.join(missing)}"
            )
        except:
            pass
            
        return False
    
    return True

def check_admin_windows():
    """En Windows, verificar si se ejecuta como administrador (opcional, solo advertencia)."""
    if sys.platform == 'win32':
        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
            if not is_admin:
                print("\n⚠️ ADVERTENCIA: No se ejecuta como administrador.")
                print("   La hotkey global puede no funcionar en juegos a pantalla completa.")
                print("   Se recomienda ejecutar la aplicación como administrador.\n")
                return False
        except:
            pass
    return True

def main():
    """Punto de entrada de la aplicación - VERSIÓN FINAL"""
    try:
        # Crear icono por defecto si no existe
        create_default_icon()
        
        # INICIALIZAR LOGGER UNIFICADO
        logger = get_logger()
        print("=" * 60)
        print("✓ Logger unificado inicializado")
        print(f"📄 Log de sesión: {logger.get_session_log_path()}")
        print(f"📄 Log de errores: {logger.get_error_log_path()}")
        print("=" * 60)
        
        # VERIFICAR DEPENDENCIAS
        print("\n🔍 Verificando dependencias...")
        if not check_dependencies():
            print("\n❌ Instala las dependencias faltantes y vuelve a intentar")
            input("Presiona Enter para salir...")
            sys.exit(1)
        print("✓ Todas las dependencias están instaladas\n")
        
        # ADVERTENCIA DE ADMINISTRADOR (Windows)
        check_admin_windows()
        
        # Configurar Ctrl+C
        signal.signal(signal.SIGINT, signal_handler)
        
        # Crear aplicación Qt
        app = QApplication(sys.argv)
        app.setApplicationName("OBS Clip Manager")
        app.setOrganizationName("StreamTools")
        
        # No cerrar cuando se cierra la ventana principal
        app.setQuitOnLastWindowClosed(False)
        
        # Aplicar estilos
        try:
            from src.ui.styles import STYLESHEET
            app.setStyleSheet(STYLESHEET)
            print("✓ Estilos aplicados")
        except Exception as e:
            print(f"⚠ No se pudieron aplicar estilos: {e}")
        
        # Cargar icono
        try:
            icon_paths = [
                Path(__file__).parent / "logo.ico",
                Path(__file__).parent / "data" / "icons" / "app.ico",
                Path(__file__).parent / "data" / "icons" / "logo.ico",
            ]
            
            icon_loaded = False
            for icon_path in icon_paths:
                if icon_path.exists():
                    app.setWindowIcon(QIcon(str(icon_path)))
                    icon_loaded = True
                    print(f"✓ Icono cargado: {icon_path}")
                    break
            
            if not icon_loaded:
                print("⚠ No se encontró icono, usando icono por defecto")
        except Exception as e:
            print(f"⚠ No se pudo cargar el icono: {e}")
        
        # Timer para permitir que Qt procese eventos (para Ctrl+C)
        timer = QTimer()
        timer.start(500)
        timer.timeout.connect(lambda: None)
        
        # Importar controlador después de crear QApplication
        from src.core.app_controller import ApplicationController
        
        # Crear controlador principal
        controller = ApplicationController()
        
        # Iniciar aplicación
        controller.initialize()
        
        # Ejecutar loop principal
        sys.exit(app.exec())
        
    except Exception as e:
        # Registrar error crítico de inicio
        try:
            logger = get_logger()
            logger.error("main.py", "app_startup", f"Error crítico al iniciar", e)
        except:
            pass
        
        # Mostrar mensaje de error detallado
        error_msg = f"""Error crítico al iniciar la aplicación:

{str(e)}

Posibles causas:
1. Faltan dependencias (pip install PyQt6 obsws-python pynput pygame pillow)
2. Configuración corrupta
3. Permisos insuficientes

Revisa el archivo de errores en:
{Path.home() / ".obs_clip_manager" / "logs" / "errors.log"}"""
        
        print(error_msg)
        
        # Intentar mostrar ventana de error
        try:
            # Crear QApplication si no existe
            if QApplication.instance() is None:
                error_app = QApplication(sys.argv)
            
            # Mostrar mensaje de error
            QMessageBox.critical(None, "Error de Inicio", error_msg)
            
            # Si hay QApplication, ejecutarla
            if QApplication.instance():
                sys.exit(1)
        except:
            pass
        
        input("\nPresiona Enter para salir...")
        sys.exit(1)

if __name__ == "__main__":
    main()