*** Settings ***
Documentation     End-to-end VizDOM demo on Windows.
...
...               Launches the Windows Calculator, reads its Visual DOM through a
...               running detector gRPC service, drives it by the labels VizDOM sees
...               on screen, and asserts the result. Capture (windows) and actuator
...               (desktop) run in-process; only the detector is a service.
...
...               PREREQUISITE: start the detector service first (see README.md):
...                 start_detector.bat --backend omniparser
...
Library           VisualGuiLibrary    platform=desktop
Library           Process
Library           OperatingSystem

*** Variables ***
${CONFIG}         ${CURDIR}${/}vizdom.config.json
${TIMEOUT}        15s

*** Test Cases ***
Calculator Adds Two Numbers
    [Documentation]    7 + 5 = 12, driven entirely by visual element detection.
    [Setup]      Open Calculator

    # Configure the whole session from the JSON file (detector = gRPC service).
    Connect                      ${CONFIG}

    # Capture the screen and build the Visual DOM.
    Dump Visual DOM

    # Drive the calculator by the labels VizDOM reads on screen.
    Wait Until Visual Appears    text=7            timeout=${TIMEOUT}
    Click Visual                 text=7
    Click Visual                 text="+"
    Click Visual                 text=5
    Click Visual                 text="="

    # Re-read the DOM after the interaction and assert the result on the display.
    Dump Visual DOM
    Visual Should Exist          text=12

    [Teardown]   Terminate All Processes

*** Keywords ***
Open Calculator
    [Documentation]    Launch the Windows Calculator and give it time to render.
    Start Process    calc.exe    shell=True
    Sleep            3s
