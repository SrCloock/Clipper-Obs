import os
import sys
import shutil
import subprocess
from pathlib import Path

# ============================================================================
# CONFIGURACIÓN DE LA APLICACIÓN (adaptada para OBS Clip Manager)
# ============================================================================
APP_VERSION = "1.0.0"
APP_NAME = "OBSClipManager"               # Nombre del ejecutable (sin espacios)
APP_DISPLAY_NAME = "OBS Clip Manager"     # Nombre para mostrar en el instalador
COMPANY_NAME = "StreamTools"              # Opcional, para el desinstalador

# ============================================================================
# FUNCIONES DE CONSTRUCCIÓN
# ============================================================================

def clean_build_folders():
    """Limpiar carpetas de builds anteriores"""
    folders_to_clean = ['build', 'dist', '__pycache__']
    for folder in folders_to_clean:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"✓ Carpeta {folder} eliminada")

def create_spec_file():
    """Crear archivo spec para PyInstaller"""
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Archivos adicionales (recursos, iconos, etc.)
added_files = [
    ('logo.ico', '.'),
    ('requirements.txt', '.'),
    ('src', 'src'),
    ('data', 'data'),          # si existe, contiene iconos, sonidos, etc.
]

# Crear carpetas de recursos si no existen (por si acaso)
import os
for folder in ['data', 'data/icons']:
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)
        print(f"Creada carpeta {{folder}}")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        # Qt
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        # Dependencias propias
        'obsws_python',
        'pynput',
        'pygame',
        'PIL',                     # pillow
        # Utilidades
        'json',
        'os',
        'sys',
        'pathlib',
        'traceback',
        'mimetypes',
        'fnmatch',
        'time',
        'functools',
        'threading',
        'queue',
        'dataclasses',
        'enum',
        'logging',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,                # Sin ventana de consola
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='logo.ico',
)

# Para Windows: crear un único ejecutable (COLLECT no es necesario con --onefile)
# Pero se deja COLLECT por si se quisiera en modo carpeta en el futuro.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{APP_NAME}',
)
'''
    with open(f'{APP_NAME}.spec', 'w', encoding='utf-8') as f:
        f.write(spec_content)
    print(f"✓ Archivo {APP_NAME}.spec creado")

def build_with_pyinstaller():
    """Compilar con PyInstaller"""
    print("\n🚀 Compilando con PyInstaller...")

    try:
        import PyInstaller
    except ImportError:
        print("❌ PyInstaller no está instalado. Instalando...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # Verificar archivos obligatorios
    required_files = ['main.py', 'logo.ico']
    for file in required_files:
        if not os.path.exists(file):
            print(f"❌ Error: No se encuentra {file}")
            return False

    # Crear carpetas de recursos si no existen (para que PyInstaller las incluya)
    for folder in ['data', 'data/icons']:
        os.makedirs(folder, exist_ok=True)

    create_spec_file()

    # Comando PyInstaller (versión simplificada, usando --onefile)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--clean",
        "--noconfirm",
        "--onefile",
        "--windowed",
        f"--icon=logo.ico",
        f"--name={APP_NAME}",
        f"--add-data=src;src",
        f"--add-data=data;data",
        f"--add-data=logo.ico;.",
        f"--add-data=requirements.txt;.",
        f"--hidden-import=PyQt6",
        f"--hidden-import=obsws_python",
        f"--hidden-import=pynput",
        f"--hidden-import=pygame",
        "main.py"
    ]

    print(f"\n📦 Ejecutando: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print("\n✅ Compilación exitosa!")
        exe_path = f"dist/{APP_NAME}.exe"
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print(f"📏 Tamaño del ejecutable: {size_mb:.2f} MB")

        # Crear carpeta installer si no existe
        installer_dir = "installer"
        if not os.path.exists(installer_dir):
            os.makedirs(installer_dir)
            print(f"✓ Carpeta {installer_dir} creada")
        return True
    else:
        print("\n❌ Error en la compilación:")
        print(result.stderr)
        return False

def create_installer_package():
    """Crear paquete para el instalador (copia los archivos necesarios)"""
    print("\n📦 Preparando paquete para el instalador...")

    package_dir = f"installer/{APP_NAME}"
    if os.path.exists(package_dir):
        shutil.rmtree(package_dir)
    os.makedirs(package_dir)

    # Copiar ejecutable
    shutil.copy2(f"dist/{APP_NAME}.exe", package_dir)
    print("✓ Ejecutable copiado")

    # Copiar archivos adicionales
    files_to_copy = [("logo.ico", package_dir), ("requirements.txt", package_dir)]
    for file, dest in files_to_copy:
        if os.path.exists(file):
            shutil.copy2(file, dest)
            print(f"✓ {file} copiado")

    # Copiar carpetas src y data completas
    for folder in ["src", "data"]:
        if os.path.exists(folder):
            shutil.copytree(folder, os.path.join(package_dir, folder))
            print(f"✓ Carpeta {folder} copiada")

    # Crear un README.txt con información básica
    readme_content = f"""{APP_DISPLAY_NAME}
Versión {APP_VERSION}

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
2. Ejecuta {APP_NAME}.exe
3. Configura la hotkey y el resto de opciones en las pestañas.
4. Cuando estés en streaming, pulsa la hotkey para guardar un clip.

Requisitos del sistema:
- Windows 7 o superior (probado en Windows 10/11)
- OBS Studio con WebSocket activado (plugin integrado en versiones recientes)

Desarrollado con Python y PyQt6
"""
    with open(os.path.join(package_dir, "README.txt"), "w", encoding="utf-8") as f:
        f.write(readme_content)

    print("\n✅ Paquete para instalador creado en:", package_dir)
    shutil.make_archive(f"installer/{APP_NAME}_Package", 'zip', package_dir)
    print("✓ Archivo ZIP creado: installer/{}_Package.zip".format(APP_NAME))
    return package_dir

def create_nsis_installer(package_dir):
    """Genera un instalador NSIS a partir del paquete preparado."""
    print("\n🛠️  Creando instalador NSIS...")

    nsis_path = shutil.which("makensis")
    if not nsis_path:
        print("❌ NSIS no está instalado o no se encuentra 'makensis' en el PATH.")
        print("   Puedes descargarlo desde: https://nsis.sourceforge.io/Download")
        return False

    installer_output = f"dist/{APP_NAME}_Setup.exe"
    nsi_script = "installer/installer_script.nsi"

    # --- Ruta absoluta con barras invertidas para NSIS ---
    abs_package_dir = os.path.abspath(package_dir)
    package_dir_nsis = abs_package_dir.replace('/', '\\') + '\\*.*'

    project_root = os.path.abspath('.')
    icon_abs_path = os.path.join(project_root, 'logo.ico').replace('\\', '/')
    readme_abs_path = os.path.join(project_root, package_dir, 'README.txt').replace('\\', '/')

    # Verificar que el README existe
    if os.path.exists(readme_abs_path):
        license_page = f'!insertmacro MUI_PAGE_LICENSE "{readme_abs_path}"'
    else:
        print("⚠️  No se encontró README.txt en el paquete. Se omitirá la página de licencia.")
        license_page = "; !insertmacro MUI_PAGE_LICENSE"

    nsi_content = f"""; Script NSIS para {APP_DISPLAY_NAME}
; Generado automáticamente por build.py

!include "MUI2.nsh"
!include "FileFunc.nsh"

;--------------------------------
; Configuración general
Name "{APP_DISPLAY_NAME}"
OutFile "{os.path.abspath(installer_output)}"
InstallDir "$PROGRAMFILES\\{APP_NAME}"
InstallDirRegKey HKCU "Software\\{APP_NAME}" ""
RequestExecutionLevel admin

;--------------------------------
; Variables
Var StartMenuFolder

;--------------------------------
; Interfaz
!define MUI_ICON "{icon_abs_path}"
!define MUI_UNICON "{icon_abs_path}"
; !define MUI_WELCOMEFINISHPAGE_BITMAP "logo.bmp"
; !define MUI_HEADERIMAGE
; !define MUI_HEADERIMAGE_BITMAP "logo.bmp"

;--------------------------------
; Páginas
!insertmacro MUI_PAGE_WELCOME
{license_page}
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

;--------------------------------
; Idiomas
!insertmacro MUI_LANGUAGE "Spanish"

;--------------------------------
; Secciones
Section "Archivos de programa" SecProgram
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "{package_dir_nsis}"
  
  ; Crear desinstalador
  WriteUninstaller "$INSTDIR\\Uninstall.exe"
  
  ; Registrar en Add/Remove Programs
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "DisplayName" "{APP_DISPLAY_NAME}"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "UninstallString" '"$INSTDIR\\Uninstall.exe"'
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "DisplayIcon" "$INSTDIR\\{APP_NAME}.exe"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "Publisher" "{COMPANY_NAME}"
  WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "DisplayVersion" "{APP_VERSION}"
  WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "NoModify" 1
  WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "NoRepair" 1
SectionEnd

Section "Acceso directo en Inicio" SecStartMenu
  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
    CreateDirectory "$SMPROGRAMS\\$StartMenuFolder"
    CreateShortCut "$SMPROGRAMS\\$StartMenuFolder\\{APP_DISPLAY_NAME}.lnk" "$INSTDIR\\{APP_NAME}.exe" "" "$INSTDIR\\logo.ico"
    CreateShortCut "$SMPROGRAMS\\$StartMenuFolder\\Desinstalar.lnk" "$INSTDIR\\Uninstall.exe"
  !insertmacro MUI_STARTMENU_WRITE_END
SectionEnd

Section "Acceso directo en Escritorio" SecDesktop
  CreateShortCut "$DESKTOP\\{APP_DISPLAY_NAME}.lnk" "$INSTDIR\\{APP_NAME}.exe" "" "$INSTDIR\\logo.ico"
SectionEnd

;--------------------------------
; Descripciones de las secciones
LangString DESC_SecProgram 30818 "Archivos necesarios para ejecutar {APP_DISPLAY_NAME}."
LangString DESC_SecStartMenu 30818 "Crea un acceso directo en el menú Inicio."
LangString DESC_SecDesktop 30818 "Crea un acceso directo en el escritorio."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${{SecProgram}} $(DESC_SecProgram)
  !insertmacro MUI_DESCRIPTION_TEXT ${{SecStartMenu}} $(DESC_SecStartMenu)
  !insertmacro MUI_DESCRIPTION_TEXT ${{SecDesktop}} $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; Sección de desinstalación
Section "Uninstall"
  ; Eliminar archivos
  RMDir /r "$INSTDIR"
  
  ; Eliminar accesos directos
  !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
  RMDir /r "$SMPROGRAMS\\$StartMenuFolder"
  Delete "$DESKTOP\\{APP_DISPLAY_NAME}.lnk"
  
  ; Eliminar entradas de registro
  DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}"
  DeleteRegKey HKCU "Software\\{APP_NAME}"
SectionEnd
"""

    # Escribir el script NSIS
    with open(nsi_script, 'w', encoding='utf-8') as f:
        f.write(nsi_content)
    print(f"✓ Script NSIS generado: {nsi_script}")

    # Ejecutar makensis
    print("⚙️  Compilando instalador...")
    result = subprocess.run([nsis_path, nsi_script], capture_output=True, text=True)

    if result.returncode == 0:
        print(f"✅ Instalador creado: {installer_output}")
        if os.path.exists(installer_output):
            size_mb = os.path.getsize(installer_output) / (1024 * 1024)
            print(f"📏 Tamaño del instalador: {size_mb:.2f} MB")
        return True
    else:
        print("❌ Error al compilar el instalador:")
        print(result.stderr)
        return False

def main():
    print("=" * 50)
    print(f"🔨 CONSTRUCTOR DE {APP_DISPLAY_NAME}")
    print("=" * 50)

    # Paso 1: Limpiar builds anteriores
    print("\n1️⃣  Limpiando builds anteriores...")
    clean_build_folders()

    # Paso 2: Compilar con PyInstaller
    print("\n2️⃣  Compilando aplicación...")
    if not build_with_pyinstaller():
        print("❌ La compilación falló. Revisa los errores.")
        return

    # Paso 3: Crear paquete para instalador
    print("\n3️⃣  Creando paquete de instalación...")
    package_dir = create_installer_package()

    # Paso 4: Generar instalador NSIS
    print("\n4️⃣  Generando instalador NSIS...")
    if not create_nsis_installer(package_dir):
        print("⚠️  No se pudo crear el instalador NSIS. Puedes generarlo manualmente con el script en installer/installer_script.nsi")

    print("\n" + "=" * 50)
    print("✅ PROCESO COMPLETADO")
    print("=" * 50)
    print("\n📁 Archivos generados:")
    print(f"  • dist/{APP_NAME}.exe (Ejecutable portable)")
    print(f"  • {package_dir}/ (Carpeta para instalador)")
    print(f"  • installer/{APP_NAME}_Package.zip (Paquete ZIP)")
    print(f"  • dist/{APP_NAME}_Setup.exe (Instalador NSIS)")
    print("\n🎯 Ya puedes distribuir el instalador.")

if __name__ == "__main__":
    main()