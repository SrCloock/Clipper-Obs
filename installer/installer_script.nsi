; Script NSIS para OBS Clip Manager
; Generado automáticamente por build.py

!include "MUI2.nsh"
!include "FileFunc.nsh"

;--------------------------------
; Configuración general
Name "OBS Clip Manager"
OutFile "C:\Users\SrCloock\Desktop\Cliper Obs\dist\OBSClipManager_Setup.exe"
InstallDir "$PROGRAMFILES\OBSClipManager"
InstallDirRegKey HKCU "Software\OBSClipManager" ""
RequestExecutionLevel admin

;--------------------------------
; Variables
Var StartMenuFolder

;--------------------------------
; Interfaz
!define MUI_ICON "C:/Users/SrCloock/Desktop/Cliper Obs/logo.ico"
!define MUI_UNICON "C:/Users/SrCloock/Desktop/Cliper Obs/logo.ico"
; !define MUI_WELCOMEFINISHPAGE_BITMAP "logo.bmp"
; !define MUI_HEADERIMAGE
; !define MUI_HEADERIMAGE_BITMAP "logo.bmp"

;--------------------------------
; Páginas
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "C:/Users/SrCloock/Desktop/Cliper Obs/installer/OBSClipManager/README.txt"
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
  File /r "C:\Users\SrCloock\Desktop\Cliper Obs\installer\OBSClipManager\*.*"
  
  ; Crear desinstalador
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  
  ; Registrar en Add/Remove Programs
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBSClipManager" "DisplayName" "OBS Clip Manager"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBSClipManager" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBSClipManager" "DisplayIcon" "$INSTDIR\OBSClipManager.exe"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBSClipManager" "Publisher" "StreamTools"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBSClipManager" "DisplayVersion" "1.0.0"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBSClipManager" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBSClipManager" "NoRepair" 1
SectionEnd

Section "Acceso directo en Inicio" SecStartMenu
  !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
    CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
    CreateShortCut "$SMPROGRAMS\$StartMenuFolder\OBS Clip Manager.lnk" "$INSTDIR\OBSClipManager.exe" "" "$INSTDIR\logo.ico"
    CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Desinstalar.lnk" "$INSTDIR\Uninstall.exe"
  !insertmacro MUI_STARTMENU_WRITE_END
SectionEnd

Section "Acceso directo en Escritorio" SecDesktop
  CreateShortCut "$DESKTOP\OBS Clip Manager.lnk" "$INSTDIR\OBSClipManager.exe" "" "$INSTDIR\logo.ico"
SectionEnd

;--------------------------------
; Descripciones de las secciones
LangString DESC_SecProgram 30818 "Archivos necesarios para ejecutar OBS Clip Manager."
LangString DESC_SecStartMenu 30818 "Crea un acceso directo en el menú Inicio."
LangString DESC_SecDesktop 30818 "Crea un acceso directo en el escritorio."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecProgram} $(DESC_SecProgram)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} $(DESC_SecStartMenu)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

;--------------------------------
; Sección de desinstalación
Section "Uninstall"
  ; Eliminar archivos
  RMDir /r "$INSTDIR"
  
  ; Eliminar accesos directos
  !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
  RMDir /r "$SMPROGRAMS\$StartMenuFolder"
  Delete "$DESKTOP\OBS Clip Manager.lnk"
  
  ; Eliminar entradas de registro
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBSClipManager"
  DeleteRegKey HKCU "Software\OBSClipManager"
SectionEnd
