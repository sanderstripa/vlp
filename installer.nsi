Unicode true
!include "MUI2.nsh"
Name "LocalDub"
OutFile "${OUTDIR}\LocalDub-0.1.0-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\LocalDub"
RequestExecutionLevel user
SetCompressor /SOLID lzma
VIProductVersion "0.1.0.0"
VIAddVersionKey "ProductName" "LocalDub"
VIAddVersionKey "FileDescription" "LocalDub offline video player installer"
VIAddVersionKey "FileVersion" "0.1.0"
VIAddVersionKey "LegalCopyright" "LocalDub contributors"
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"
Section "LocalDub"
  SetShellVarContext current
  SetOutPath "$INSTDIR"
  File /r "${BINARY}\*"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\LocalDub"
  CreateShortCut "$SMPROGRAMS\LocalDub\LocalDub.lnk" "$INSTDIR\LocalDub.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalDub" "DisplayName" "LocalDub 0.1.0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalDub" "DisplayVersion" "0.1.0"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalDub" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalDub" "InstallLocation" "$INSTDIR"
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalDub" "NoModify" 1
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalDub" "NoRepair" 1
SectionEnd
Section "Uninstall"
  SetShellVarContext current
  !include "${OUTDIR}\uninstall-files.nsh"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  Delete "$SMPROGRAMS\LocalDub\LocalDub.lnk"
  RMDir "$SMPROGRAMS\LocalDub"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\LocalDub"
SectionEnd
