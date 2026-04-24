"""
Script de construcción profesional para OBS Clip Manager
- Compila con Nuitka (modo standalone, un solo archivo)
- Genera instalador NSIS con todos los recursos necesarios
"""

import os
import sys
import shutil
import subprocess
import time
import itertools
from pathlib import Path

# ================= CONFIGURACIÓN =================
APP_NAME = "OBS Clip Manager"
APP_EXE_NAME = "OBS-Clip-Manager.exe"
APP_VERSION = "1.0.0"
COMPANY_NAME = "StreamTools"
# =================================================

# Ruta a makensis.exe (ajústala si es necesario)
NSIS_MAKENSIS = r"B:\PROGRAMAS\NSIS\makensis.exe"

def clean_build_folders():
    """Elimina carpetas temporales de compilaciones anteriores."""
    for folder in ['build', 'dist', '__pycache__']:
        if os.path.exists(folder):
            shutil.rmtree(folder)
            print(f"✓ Eliminada {folder}")

def build_with_nuitka():
    """Compila la aplicación con Nuitka en modo standalone (carpeta), no onefile aún."""
    print("\n🚀 Compilando con Nuitka (modo standalone)...")
    print("   ⏳ Esto puede tardar varios minutos. Paciencia...\n")

    # Usamos --standalone sin --onefile primero para tener acceso a la carpeta dist/main.dist
    cmd = [
        sys.executable, "-m", "nuitka",
        "--standalone",
        "--windows-icon-from-ico=logo.ico",
        "--enable-plugin=pyqt6",
        "--show-progress",
        "--output-dir=dist",
        f"--output-filename={APP_EXE_NAME}",
        "--windows-disable-console",
        "main.py"
    ]

    # Incluir directorios de recursos (data, sonidos, etc.)
    if os.path.exists("data"):
        cmd.append("--include-data-dir=data=data")

    # Incluir archivos sueltos
    if os.path.exists("logo.ico"):
        cmd.append("--include-data-file=logo.ico=logo.ico")

    # Incluir FFmpeg si existe
    ffmpeg_path = "bin/ffmpeg.exe"
    if os.path.exists(ffmpeg_path):
        cmd.append(f"--include-data-file={ffmpeg_path}=ffmpeg.exe")

    # Forzar la inclusión de plugins de Qt (a veces Nuitka no los copia todos)
    cmd.append("--include-package-data=PyQt6")

    # Ejecutar Nuitka
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    for line in process.stdout:
        print(line, end='')
    process.wait()

    if process.returncode != 0:
        print("\n❌ Error en Nuitka. Revisa la salida arriba.")
        return False

    # Verificar que existe la carpeta dist/main.dist
    dist_dir = Path("dist") / "main.dist"
    if not dist_dir.exists():
        print(f"❌ No se encontró la carpeta de salida: {dist_dir}")
        return False

    print(f"\n✅ Compilación standalone exitosa: {dist_dir}")
    return True

def prepare_installer_files():
    """Prepara los archivos que se incluirán en el instalador."""
    print("\n📦 Preparando archivos para el instalador...")
    installer_dir = Path("installer")
    installer_dir.mkdir(exist_ok=True)

    dist_dir = Path("dist") / "main.dist"

    # Copiar toda la carpeta main.dist a installer/app
    app_dir = installer_dir / "app"
    if app_dir.exists():
        shutil.rmtree(app_dir)
    shutil.copytree(dist_dir, app_dir)
    print(f"✓ Aplicación copiada a: {app_dir}")

    # Copiar icono
    if os.path.exists("logo.ico"):
        shutil.copy2("logo.ico", installer_dir / "logo.ico")
        print("✓ Icono copiado")

    # Copiar FFmpeg si existe (para incluirlo en el instalador)
    if os.path.exists("bin/ffmpeg.exe"):
        shutil.copy2("bin/ffmpeg.exe", installer_dir / "ffmpeg.exe")
        print("✓ FFmpeg copiado")

    return installer_dir

def create_nsis_script(installer_dir):
    """Crea el script NSIS dentro de la carpeta installer."""
    print("\n📝 Generando script NSIS...")

    # Determinar si hay icono y ffmpeg
    has_icon = (installer_dir / "logo.ico").exists()
    has_ffmpeg = (installer_dir / "ffmpeg.exe").exists()

    icon_line = 'File "logo.ico"' if has_icon else '; File "logo.ico"'
    ffmpeg_line = 'File "ffmpeg.exe"' if has_ffmpeg else '; File "ffmpeg.exe"'

    # Páginas opcionales
    license_line = '!insertmacro MUI_PAGE_LICENSE "LICENSE.txt"' if os.path.exists("LICENSE.txt") else '; !insertmacro MUI_PAGE_LICENSE "LICENSE.txt"'
    bitmap_line = '!define MUI_WELCOMEFINISHPAGE_BITMAP "logo.bmp"' if os.path.exists("logo.bmp") else '; !define MUI_WELCOMEFINISHPAGE_BITMAP "logo.bmp"'
    header_bitmap_line = '!define MUI_HEADERIMAGE_BITMAP "logo.bmp"' if os.path.exists("logo.bmp") else '; !define MUI_HEADERIMAGE_BITMAP "logo.bmp"'

    nsi_content = f"""
; Script NSIS para {APP_NAME}
!include "MUI2.nsh"
!include "FileFunc.nsh"

Name "{APP_NAME}"
OutFile "{APP_NAME} Setup.exe"
InstallDir "$PROGRAMFILES\\{APP_NAME}"
InstallDirRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "InstallLocation"
RequestExecutionLevel admin

Var StartMenuFolder

!define MUI_ICON "logo.ico"
!define MUI_UNICON "logo.ico"
{bitmap_line}
{header_bitmap_line}

!insertmacro MUI_PAGE_WELCOME
{license_line}
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\\{APP_EXE_NAME}"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "English"

Section "Archivos del programa" SecProgram
    SectionIn RO
    SetOutPath "$INSTDIR"
    
    ; Copiar todos los archivos de la aplicación
    File /r "app\\*.*"
    
    ; Archivos adicionales en la raíz
    {icon_line}
    {ffmpeg_line}
    
    WriteUninstaller "$INSTDIR\\Uninstall.exe"

    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "DisplayName" "{APP_NAME}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "UninstallString" '"$INSTDIR\\Uninstall.exe"'
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "DisplayIcon" "$INSTDIR\\{APP_EXE_NAME}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "Publisher" "{COMPANY_NAME}"
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "DisplayVersion" "{APP_VERSION}"
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "NoModify" 1
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "NoRepair" 1
    WriteRegStr HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "InstallLocation" "$INSTDIR"

    ${{GetSize}} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}" "EstimatedSize" "$0"
SectionEnd

Section "Acceso directo en Menú Inicio" SecStartMenu
    !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
        CreateDirectory "$SMPROGRAMS\\$StartMenuFolder"
        CreateShortCut "$SMPROGRAMS\\$StartMenuFolder\\{APP_NAME}.lnk" "$INSTDIR\\{APP_EXE_NAME}" "" "$INSTDIR\\logo.ico"
        CreateShortCut "$SMPROGRAMS\\$StartMenuFolder\\Desinstalar {APP_NAME}.lnk" "$INSTDIR\\Uninstall.exe"
    !insertmacro MUI_STARTMENU_WRITE_END
SectionEnd

Section "Acceso directo en Escritorio" SecDesktop
    CreateShortCut "$DESKTOP\\{APP_NAME}.lnk" "$INSTDIR\\{APP_EXE_NAME}" "" "$INSTDIR\\logo.ico"
SectionEnd

LangString DESC_SecProgram ${{LANG_SPANISH}} "Archivos necesarios para ejecutar {APP_NAME}."
LangString DESC_SecStartMenu ${{LANG_SPANISH}} "Crea un acceso directo en el menú Inicio."
LangString DESC_SecDesktop ${{LANG_SPANISH}} "Crea un acceso directo en el escritorio."
LangString DESC_SecProgram ${{LANG_ENGLISH}} "Program files needed to run {APP_NAME}."
LangString DESC_SecStartMenu ${{LANG_ENGLISH}} "Create a Start Menu shortcut."
LangString DESC_SecDesktop ${{LANG_ENGLISH}} "Create a Desktop shortcut."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${{SecProgram}} $(DESC_SecProgram)
    !insertmacro MUI_DESCRIPTION_TEXT ${{SecStartMenu}} $(DESC_SecStartMenu)
    !insertmacro MUI_DESCRIPTION_TEXT ${{SecDesktop}} $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
    !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
    RMDir /r "$SMPROGRAMS\\$StartMenuFolder"
    Delete "$DESKTOP\\{APP_NAME}.lnk"
    RMDir /r "$INSTDIR"
    DeleteRegKey HKLM "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{APP_NAME}"
    DeleteRegKey HKCU "Software\\{APP_NAME}"
SectionEnd
"""
    nsi_path = installer_dir / "installer_script.nsi"
    with open(nsi_path, "w", encoding="utf-8") as f:
        f.write(nsi_content)
    print(f"✓ Script NSIS guardado: {nsi_path}")
    return nsi_path

def compile_nsis(installer_dir, nsi_path):
    """Compila el script NSIS y mueve el instalador a dist."""
    makensis = NSIS_MAKENSIS
    if not os.path.exists(makensis):
        makensis = shutil.which("makensis")
        if not makensis:
            for p in [r"C:\Program Files (x86)\NSIS\makensis.exe", r"C:\Program Files\NSIS\makensis.exe"]:
                if os.path.exists(p):
                    makensis = p
                    break
    if not makensis or not os.path.exists(makensis):
        print("❌ No se encontró NSIS (makensis.exe).")
        return False

    print("⚙️ Compilando instalador con NSIS...")
    result = subprocess.run(
        [makensis, str(nsi_path.name)],
        cwd=str(installer_dir),
        capture_output=True,
        text=True
    )
    output = result.stdout + result.stderr
    print(output)

    if result.returncode != 0:
        print("❌ Error al compilar el instalador.")
        return False

    generated = installer_dir / f"{APP_NAME} Setup.exe"
    if not generated.exists():
        print("❌ No se encontró el instalador generado.")
        return False

    os.makedirs("dist", exist_ok=True)
    target = Path("dist") / generated.name
    shutil.move(str(generated), str(target))
    print(f"✅ Instalador movido a: {target}")

    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"📏 Tamaño: {size_mb:.2f} MB")
    return True

def main():
    print("=" * 60)
    print(f"🔨 CONSTRUCTOR PROFESIONAL DE {APP_NAME} (Nuitka + NSIS)")
    print("=" * 60)

    clean_build_folders()

    if not build_with_nuitka():
        print("\n❌ Falló la compilación con Nuitka. Abortando.")
        return

    installer_dir = prepare_installer_files()
    nsi_script = create_nsis_script(installer_dir)
    if nsi_script is None:
        print("\n❌ No se pudo crear el script NSIS.")
        return

    if compile_nsis(installer_dir, nsi_script):
        print("\n✅ INSTALADOR NSIS GENERADO CORRECTAMENTE")
        print(f"  • Instalador: dist/{APP_NAME} Setup.exe")
    else:
        print("\n⚠️ No se generó el instalador NSIS.")

if __name__ == "__main__":
    main()