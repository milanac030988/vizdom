; installer.nsh - custom NSIS page for the VizDOM Studio installer.
;
; electron-builder includes this file automatically (it sits in the build
; resources folder, `resources/`).
;
; Studio brings its own Python, so nothing here is needed to run Studio. This
; page is for people who run their Robot Framework suites with a Python of their
; own (RobotFramework AIO, python.org, a venv): it can install the VizDOM Robot
; Framework library into that interpreter, from the wheel the installer carries.
;
;   1. The page lists the Pythons it finds: RobotFramework AIO, `py -0p` (every
;      Python the launcher knows) and `where python`; Browse adds any other.
;   2. For the selected one it shows the version and whether VizDOM is already
;      installed. Only 64-bit Python 3.9 to 3.13 is accepted.
;   3. On install: pip install "<bundled wheel>[robot]"; when that fails, the
;      same version from PyPI. pip downloads the dependencies (PyTorch, EasyOCR,
;      OpenCV, ...) from the package index, so this step needs network access.
;
; The packages stay in that Python when Studio is uninstalled.
;
; The online installer (installer-online.nsh defines VIZDOM_ONLINE) ships without
; PyTorch and EasyOCR. Its "Text recognition" page, ticked by default, downloads
; them into Studio's own Python with resources\online\install_easyocr.cmd, at the
; versions the full installer of the same release carries. Without them Studio
; reads text with Tesseract; a failed download does not fail the installation.

!include "LogicLib.nsh"
!include "nsDialogs.nsh"

!ifndef CB_FINDSTRINGEXACT
  !define CB_FINDSTRINGEXACT 0x0158
!endif

!ifndef BUILD_UNINSTALLER

Var /GLOBAL PY_Dialog
Var /GLOBAL PY_Check
Var /GLOBAL PY_Combo
Var /GLOBAL PY_Browse
Var /GLOBAL PY_Status
Var /GLOBAL PY_DoInstall      ; "1" install into $PY_Path, "0" skip
Var /GLOBAL PY_Path
Var /GLOBAL PY_Supported      ; "1" when $PY_Path is a 64-bit Python 3.9 to 3.13

; ---------------------------------------------------------------------------
; Helpers
; ---------------------------------------------------------------------------

; Push <haystack>, Push <needle>, Call PY_StrContains, Pop -> "1" or "0"
Function PY_StrContains
  Exch $R1          ; needle
  Exch
  Exch $R2          ; haystack
  Push $R3
  Push $R4
  Push $R5
  StrLen $R3 $R1
  StrCpy $R4 0
  StrCpy $R0 "0"
  ${Do}
    StrCpy $R5 $R2 $R3 $R4
    ${If} $R5 == ""
      ${ExitDo}
    ${EndIf}
    ${If} $R5 == $R1
      StrCpy $R0 "1"
      ${ExitDo}
    ${EndIf}
    IntOp $R4 $R4 + 1
  ${Loop}
  Pop $R5
  Pop $R4
  Pop $R3
  Pop $R2
  Pop $R1
  Push $R0          ; result (the caller saves $R0 if it needs it)
FunctionEnd

; Push <string>, Call PY_TrimEnd, Pop -> string without trailing CR/LF/space
Function PY_TrimEnd
  Exch $R1
  Push $R2
  Push $R3
  ${Do}
    StrLen $R2 $R1
    ${If} $R2 == 0
      ${ExitDo}
    ${EndIf}
    IntOp $R2 $R2 - 1
    StrCpy $R3 $R1 1 $R2
    ${If} $R3 == "$\r"
    ${OrIf} $R3 == "$\n"
    ${OrIf} $R3 == " "
      StrCpy $R1 $R1 $R2
    ${Else}
      ${ExitDo}
    ${EndIf}
  ${Loop}
  Pop $R3
  Pop $R2
  Exch $R1
FunctionEnd

; Push <path>, Call PY_AddCandidate: adds it to the combo when the file exists,
; is not the Microsoft Store alias (WindowsApps) and is not listed yet.
Function PY_AddCandidate
  Exch $R1
  Push $R0
  Push $R7
  Push $R1
  Call PY_TrimEnd
  Pop $R1
  ${If} $R1 != ""
    IfFileExists "$R1" 0 py_add_done
    Push $R1
    Push "\WindowsApps\"
    Call PY_StrContains
    Pop $R0
    ${If} $R0 == "0"
      SendMessage $PY_Combo ${CB_FINDSTRINGEXACT} -1 "STR:$R1" $R7
      ${If} $R7 == -1
        ${NSD_CB_AddString} $PY_Combo "$R1"
      ${EndIf}
    ${EndIf}
  ${EndIf}
  py_add_done:
  Pop $R7
  Pop $R0
  Pop $R1
FunctionEnd

; Push <multi-line command output>, Call PY_AddFromOutput: every line that
; contains a drive path ("X:\...") adds the path from the drive letter on.
; Works for `where python` (one path per line) and `py -0p`
; (" -V:3.12 *        C:\...\python.exe").
Function PY_AddFromOutput
  Exch $R1          ; output
  Push $R2
  Push $R3
  Push $R4
  Push $R5
  Push $R6
  StrLen $R2 $R1
  StrCpy $R3 0      ; start of the current line
  StrCpy $R4 0      ; scan position
  ${Do}
    StrCpy $R5 $R1 1 $R4
    ${If} $R4 >= $R2
    ${OrIf} $R5 == "$\n"
    ${OrIf} $R5 == "$\r"
      IntOp $R6 $R4 - $R3
      ${If} $R6 > 2
        StrCpy $R5 $R1 $R6 $R3          ; the line
        ; find ":\" and take the path from one character before it
        StrCpy $R6 0
        ${Do}
          StrCpy $R0 $R5 2 $R6
          ${If} $R0 == ""
            ${ExitDo}
          ${EndIf}
          ${If} $R0 == ":\"
            ${If} $R6 > 0
              IntOp $R6 $R6 - 1
              StrCpy $R0 $R5 "" $R6
              Push $R0
              Call PY_AddCandidate
            ${EndIf}
            ${ExitDo}
          ${EndIf}
          IntOp $R6 $R6 + 1
        ${Loop}
      ${EndIf}
      ${If} $R4 >= $R2
        ${ExitDo}
      ${EndIf}
      IntOp $R4 $R4 + 1
      StrCpy $R3 $R4
    ${Else}
      IntOp $R4 $R4 + 1
    ${EndIf}
  ${Loop}
  Pop $R6
  Pop $R5
  Pop $R4
  Pop $R3
  Pop $R2
  Pop $R1
FunctionEnd

Function PY_PopulateCombo
  ; 1. RobotFramework AIO
  Push "$PROGRAMFILES64\RobotFramework\python3\python.exe"
  Call PY_AddCandidate
  Push "$PROGRAMFILES\RobotFramework\python3\python.exe"
  Call PY_AddCandidate
  ; 2. every Python the py launcher knows
  nsExec::ExecToStack 'py -0p'
  Pop $R0
  Pop $R1
  ${If} $R0 == "0"
    Push $R1
    Call PY_AddFromOutput
  ${EndIf}
  ; 3. python on the PATH
  nsExec::ExecToStack 'where python'
  Pop $R0
  Pop $R1
  ${If} $R0 == "0"
    Push $R1
    Call PY_AddFromOutput
  ${EndIf}
FunctionEnd

; Reads the selected interpreter and shows its version and VizDOM status.
Function PY_Detect
  ${NSD_GetText} $PY_Combo $PY_Path
  StrCpy $PY_Supported "0"
  ${If} $PY_Path == ""
    ${NSD_SetText} $PY_Status "No Python found. Choose python.exe with the ... button."
    Return
  ${EndIf}
  IfFileExists "$PY_Path" 0 py_detect_missing

  ; "3.12 64"
  nsExec::ExecToStack `"$PY_Path" -c "import sys,struct; v=sys.version_info; print('%d.%d %d' % (v[0], v[1], struct.calcsize('P') * 8))"`
  Pop $R0
  Pop $R1
  Push $R1
  Call PY_TrimEnd
  Pop $R1
  ${If} $R0 != "0"
    ${NSD_SetText} $PY_Status "This file did not run as Python (exit code $R0)."
    Return
  ${EndIf}

  ; split "M.m bits"
  StrCpy $R2 $R1 1                 ; major (single digit)
  StrCpy $R3 ""                    ; minor
  StrCpy $R4 2
  ${Do}
    StrCpy $R5 $R1 1 $R4
    ${If} $R5 == " "
    ${OrIf} $R5 == ""
      ${ExitDo}
    ${EndIf}
    StrCpy $R3 "$R3$R5"
    IntOp $R4 $R4 + 1
  ${Loop}
  IntOp $R4 $R4 + 1
  StrCpy $R6 $R1 "" $R4            ; bits

  ${If} $R6 != "64"
    ${NSD_SetText} $PY_Status "Python $R2.$R3 is $R6-bit. VizDOM needs a 64-bit Python 3.9 to 3.13."
    Return
  ${EndIf}
  ${If} $R2 != "3"
  ${OrIf} $R3 < 9
  ${OrIf} $R3 > 13
    ${NSD_SetText} $PY_Status "Python $R2.$R3 is not supported. VizDOM needs a 64-bit Python 3.9 to 3.13."
    Return
  ${EndIf}
  StrCpy $PY_Supported "1"

  nsExec::ExecToStack `"$PY_Path" -c "from importlib.metadata import version; print(version('vizdom'))"`
  Pop $R0
  Pop $R7
  Push $R7
  Call PY_TrimEnd
  Pop $R7
  ${If} $R0 == "0"
  ${AndIf} $R7 != ""
    ${NSD_SetText} $PY_Status "Python $R2.$R3, 64-bit. VizDOM $R7 is installed and will be upgraded to ${VERSION}."
  ${Else}
    ${NSD_SetText} $PY_Status "Python $R2.$R3, 64-bit. VizDOM ${VERSION} will be installed. pip downloads its dependencies (PyTorch, EasyOCR, about 1 GB) from the package index."
  ${EndIf}
  Return

  py_detect_missing:
  ${NSD_SetText} $PY_Status "There is no file at this path."
FunctionEnd

; nsDialogs::OnChange misses dropdown selections, so poll the combo text.
Function PY_Timer
  ${NSD_KillTimer} PY_Timer
  ${NSD_GetText} $PY_Combo $R8
  ${If} $R8 != $PY_Path
    Call PY_Detect
  ${EndIf}
  ${NSD_CreateTimer} PY_Timer 500
FunctionEnd

Function PY_OnCheck
  ${NSD_GetState} $PY_Check $R0
  ${If} $R0 == ${BST_CHECKED}
    StrCpy $PY_DoInstall "1"
    EnableWindow $PY_Combo 1
    EnableWindow $PY_Browse 1
    EnableWindow $PY_Status 1
  ${Else}
    StrCpy $PY_DoInstall "0"
    EnableWindow $PY_Combo 0
    EnableWindow $PY_Browse 0
    EnableWindow $PY_Status 0
  ${EndIf}
FunctionEnd

Function PY_OnBrowse
  nsDialogs::SelectFileDialog open "" "Python (python.exe)|python.exe|All files (*.*)|*.*"
  Pop $R0
  ${If} $R0 != ""
    SendMessage $PY_Combo ${CB_FINDSTRINGEXACT} -1 "STR:$R0" $R7
    ${If} $R7 == -1
      ${NSD_CB_AddString} $PY_Combo "$R0"
    ${EndIf}
    ${NSD_CB_SelectString} $PY_Combo "$R0"
    Call PY_Detect
  ${EndIf}
FunctionEnd

Function PY_PageCreate
  !ifmacrodef MUI_HEADER_TEXT
    !insertmacro MUI_HEADER_TEXT "Python for Robot Framework" "Optionally add the VizDOM library to a Python you already have."
  !endif
  nsDialogs::Create 1018
  Pop $PY_Dialog
  ${If} $PY_Dialog == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0u 100% 28u "VizDOM Studio brings its own Python. If you run Robot Framework suites with another Python (RobotFramework AIO, python.org, a virtual environment), the installer can add the VizDOM Robot Framework library to it."
  Pop $R0

  ${NSD_CreateCheckBox} 0 32u 100% 12u "Install the VizDOM Robot Framework library into this Python:"
  Pop $PY_Check
  ${NSD_OnClick} $PY_Check PY_OnCheck

  ${NSD_CreateComboBox} 0 48u 262u 100u ""
  Pop $PY_Combo
  ${NSD_CreateButton} 266u 47u 34u 15u "..."
  Pop $PY_Browse
  ${NSD_OnClick} $PY_Browse PY_OnBrowse

  ${NSD_CreateLabel} 0 68u 100% 36u ""
  Pop $PY_Status

  ${NSD_CreateLabel} 0 108u 100% 24u "Uninstalling Studio leaves these packages in that Python. You can also do this later with: python -m pip install $\"vizdom[robot]$\""
  Pop $R0

  Call PY_PopulateCombo
  ${If} $PY_Path != ""
    ${NSD_CB_SelectString} $PY_Combo "$PY_Path"
  ${Else}
    SendMessage $PY_Combo ${CB_SETCURSEL} 0 0
  ${EndIf}
  Call PY_Detect

  ${If} $PY_DoInstall == "1"
    ${NSD_Check} $PY_Check
  ${EndIf}
  Call PY_OnCheck

  ${NSD_CreateTimer} PY_Timer 500
  nsDialogs::Show
FunctionEnd

Function PY_PageLeave
  ${NSD_KillTimer} PY_Timer
  Call PY_Detect
  ${If} $PY_DoInstall == "1"
    IfFileExists "$PY_Path" py_leave_exists
      MessageBox MB_OK|MB_ICONEXCLAMATION "Python was not found at:$\n$PY_Path$\n$\nChoose python.exe, or clear the check box to skip this step."
      ${NSD_CreateTimer} PY_Timer 500
      Abort
    py_leave_exists:
    ${If} $PY_Supported != "1"
      MessageBox MB_OK|MB_ICONEXCLAMATION "VizDOM needs a 64-bit Python 3.9 to 3.13.$\n$\nChoose another Python, or clear the check box to skip this step."
      ${NSD_CreateTimer} PY_Timer 500
      Abort
    ${EndIf}
  ${EndIf}
FunctionEnd

; Installs the bundled wheel into $PY_Path; PyPI is the fallback.
Function PY_InstallLibrary
  DetailPrint "Installing the VizDOM Robot Framework library into $PY_Path"

  ; pip may be missing (an embeddable or minimal Python)
  nsExec::ExecToStack `"$PY_Path" -m pip --version`
  Pop $R0
  Pop $R1
  ${If} $R0 != "0"
    DetailPrint "pip is missing; running ensurepip"
    nsExec::ExecToLog `"$PY_Path" -m ensurepip --upgrade`
    Pop $R0
  ${EndIf}

  StrCpy $R2 ""
  FindFirst $R3 $R4 "$INSTDIR\resources\wheels\vizdom-*.whl"
  ${If} $R4 != ""
    StrCpy $R2 "$INSTDIR\resources\wheels\$R4"
  ${EndIf}
  FindClose $R3

  StrCpy $R0 "1"
  ${If} $R2 != ""
    DetailPrint "From the bundled wheel: $R2"
    nsExec::ExecToLog `"$PY_Path" -m pip install --upgrade --disable-pip-version-check "$R2[robot]"`
    Pop $R0
  ${EndIf}
  ${If} $R0 != "0"
    DetailPrint "Installing vizdom[robot]==${VERSION} from PyPI"
    nsExec::ExecToLog `"$PY_Path" -m pip install --upgrade --disable-pip-version-check "vizdom[robot]==${VERSION}"`
    Pop $R0
  ${EndIf}

  ${If} $R0 == "0"
    nsExec::ExecToStack `"$PY_Path" -c "import VisualGuiLibrary"`
    Pop $R0
    Pop $R1
  ${EndIf}

  ${If} $R0 == "0"
    DetailPrint "VizDOM Robot Framework library installed: Library    VisualGuiLibrary"
  ${Else}
    DetailPrint "Installing the VizDOM Robot Framework library failed (exit code $R0)."
    MessageBox MB_OK|MB_ICONEXCLAMATION "The VizDOM Robot Framework library could not be installed into:$\n$PY_Path$\n$\nStudio itself is installed. The details list shows pip's output. To retry later, run:$\n$\n$\"$PY_Path$\" -m pip install $\"vizdom[robot]$\""
  ${EndIf}
FunctionEnd

!ifdef VIZDOM_ONLINE
; ---------------------------------------------------------------------------
; Online installer: EasyOCR as a download
; ---------------------------------------------------------------------------
Var /GLOBAL OCR_Check
Var /GLOBAL OCR_DoInstall     ; "1" download EasyOCR into Studio's Python

Function OCR_PageCreate
  !ifmacrodef MUI_HEADER_TEXT
    !insertmacro MUI_HEADER_TEXT "Text recognition" "Choose how VizDOM Studio reads text on the screen."
  !endif
  nsDialogs::Create 1018
  Pop $R0
  ${If} $R0 == error
    Abort
  ${EndIf}

  ${NSD_CreateLabel} 0 0u 100% 36u "Studio reads text with Tesseract, which this installer includes. EasyOCR reads small and styled text better, and is what the full installer brings. It runs on PyTorch: the installer downloads both and the EasyOCR models, a few hundred MB, from the Python package index and GitHub."
  Pop $R0

  ${NSD_CreateCheckBox} 0 42u 100% 12u "Download and install EasyOCR (recommended)"
  Pop $OCR_Check
  ${If} $OCR_DoInstall == "1"
    ${NSD_Check} $OCR_Check
  ${EndIf}

  ${NSD_CreateLabel} 0 62u 100% 44u "Without it, Studio uses Tesseract. If the download fails (no network, a proxy), Studio is still installed. To add EasyOCR later, run install_easyocr.cmd in the resources\online folder of the installation, or use the full installer."
  Pop $R0

  nsDialogs::Show
FunctionEnd

Function OCR_PageLeave
  ${NSD_GetState} $OCR_Check $R0
  ${If} $R0 == ${BST_CHECKED}
    StrCpy $OCR_DoInstall "1"
  ${Else}
    StrCpy $OCR_DoInstall "0"
  ${EndIf}
FunctionEnd

Function OCR_Install
  DetailPrint "Downloading EasyOCR, CPU PyTorch and the EasyOCR models"
  nsExec::ExecToLog `"$SYSDIR\cmd.exe" /c ""$INSTDIR\resources\online\install_easyocr.cmd""`
  Pop $R0
  ${If} $R0 == "0"
    DetailPrint "EasyOCR is installed."
  ${Else}
    DetailPrint "EasyOCR could not be installed (exit code $R0); Studio reads text with Tesseract."
    ${IfNot} ${Silent}
      MessageBox MB_OK|MB_ICONEXCLAMATION "EasyOCR could not be downloaded. The details list shows why.$\n$\nStudio is installed and reads text with Tesseract. To add EasyOCR later, run:$\n$\n$INSTDIR\resources\online\install_easyocr.cmd"
    ${EndIf}
  ${EndIf}
FunctionEnd
!endif ; VIZDOM_ONLINE

!endif ; BUILD_UNINSTALLER

!macro customInit
  !ifdef VIZDOM_ONLINE
    StrCpy $OCR_DoInstall "1"     ; also for a silent install
  !endif
  StrCpy $PY_DoInstall "0"
  StrCpy $PY_Path ""
  ; A RobotFramework AIO installation is the common case: preselect it.
  ; A silent install (/S) never changes another Python.
  ${IfNot} ${Silent}
    IfFileExists "$PROGRAMFILES64\RobotFramework\python3\python.exe" 0 py_init_try32
      StrCpy $PY_Path "$PROGRAMFILES64\RobotFramework\python3\python.exe"
      StrCpy $PY_DoInstall "1"
      Goto py_init_done
    py_init_try32:
    IfFileExists "$PROGRAMFILES\RobotFramework\python3\python.exe" 0 py_init_done
      StrCpy $PY_Path "$PROGRAMFILES\RobotFramework\python3\python.exe"
      StrCpy $PY_DoInstall "1"
    py_init_done:
  ${EndIf}
!macroend

!macro customPageAfterChangeDir
  !ifdef VIZDOM_ONLINE
    Page custom OCR_PageCreate OCR_PageLeave
  !endif
  Page custom PY_PageCreate PY_PageLeave
!macroend

!macro customInstall
  !ifdef VIZDOM_ONLINE
    ${If} $OCR_DoInstall == "1"
      Call OCR_Install
    ${EndIf}
  !endif
  ${If} $PY_DoInstall == "1"
  ${AndIf} $PY_Path != ""
    Call PY_InstallLibrary
  ${EndIf}
!macroend
