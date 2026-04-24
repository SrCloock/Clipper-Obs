
; Script NSIS para OBS Clip Manager
!include "MUI2.nsh"
!include "FileFunc.nsh"

Name "OBS Clip Manager"
OutFile "OBS Clip Manager Setup.exe"
InstallDir "$PROGRAMFILES\OBS Clip Manager"
InstallDirRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "InstallLocation"
RequestExecutionLevel admin

Var StartMenuFolder

!define MUI_ICON "logo.ico"
!define MUI_UNICON "logo.ico"
; !define MUI_WELCOMEFINISHPAGE_BITMAP "logo.bmp"
; !define MUI_HEADERIMAGE_BITMAP "logo.bmp"

!insertmacro MUI_PAGE_WELCOME
; !insertmacro MUI_PAGE_LICENSE "LICENSE.txt"
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder
!insertmacro MUI_PAGE_INSTFILES
!define MUI_FINISHPAGE_RUN "$INSTDIR\OBS-Clip-Manager.exe"
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Spanish"
!insertmacro MUI_LANGUAGE "English"

Section "Archivos del programa" SecProgram
    SectionIn RO
    SetOutPath "$INSTDIR"
    
    ; Copiar todos los archivos de la aplicación
    File /r "app\*.*"
    
    ; Archivos adicionales en la raíz
    File "logo.ico"
    File "ffmpeg.exe"
    
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "DisplayName" "OBS Clip Manager"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "UninstallString" '"$INSTDIR\Uninstall.exe"'
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "DisplayIcon" "$INSTDIR\OBS-Clip-Manager.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "Publisher" "StreamTools"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "DisplayVersion" "1.0.0"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "NoRepair" 1
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "InstallLocation" "$INSTDIR"

    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager" "EstimatedSize" "$0"
SectionEnd

Section "Acceso directo en Menú Inicio" SecStartMenu
    !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
        CreateDirectory "$SMPROGRAMS\$StartMenuFolder"
        CreateShortCut "$SMPROGRAMS\$StartMenuFolder\OBS Clip Manager.lnk" "$INSTDIR\OBS-Clip-Manager.exe" "" "$INSTDIR\logo.ico"
        CreateShortCut "$SMPROGRAMS\$StartMenuFolder\Desinstalar OBS Clip Manager.lnk" "$INSTDIR\Uninstall.exe"
    !insertmacro MUI_STARTMENU_WRITE_END
SectionEnd

Section "Acceso directo en Escritorio" SecDesktop
    CreateShortCut "$DESKTOP\OBS Clip Manager.lnk" "$INSTDIR\OBS-Clip-Manager.exe" "" "$INSTDIR\logo.ico"
SectionEnd

LangString DESC_SecProgram ${LANG_SPANISH} "Archivos necesarios para ejecutar OBS Clip Manager."
LangString DESC_SecStartMenu ${LANG_SPANISH} "Crea un acceso directo en el menú Inicio."
LangString DESC_SecDesktop ${LANG_SPANISH} "Crea un acceso directo en el escritorio."
LangString DESC_SecProgram ${LANG_ENGLISH} "Program files needed to run OBS Clip Manager."
LangString DESC_SecStartMenu ${LANG_ENGLISH} "Create a Start Menu shortcut."
LangString DESC_SecDesktop ${LANG_ENGLISH} "Create a Desktop shortcut."

!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
    !insertmacro MUI_DESCRIPTION_TEXT ${SecProgram} $(DESC_SecProgram)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecStartMenu} $(DESC_SecStartMenu)
    !insertmacro MUI_DESCRIPTION_TEXT ${SecDesktop} $(DESC_SecDesktop)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
    !insertmacro MUI_STARTMENU_GETFOLDER Application $StartMenuFolder
    RMDir /r "$SMPROGRAMS\$StartMenuFolder"
    Delete "$DESKTOP\OBS Clip Manager.lnk"
    RMDir /r "$INSTDIR"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\OBS Clip Manager"
    DeleteRegKey HKCU "Software\OBS Clip Manager"
SectionEnd
