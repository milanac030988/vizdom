*** Settings ***
Documentation     Acceptance suite: VizDOM drives a real GUI end to end.
...
...               Starts a small PyQt calculator (app/demo_calculator.py), builds
...               its Visual DOM from pixels only (UIED + EasyOCR, CPU), clicks
...               keys through the desktop actuator and reads the result back
...               from the screen. Runs headless in CI under Xvfb
...               (.github/workflows/acceptance.yml); locally it needs a Linux
...               X display with the app visible.
Library           VisualGuiLibrary
Library           Process
Library           OperatingSystem

Suite Setup       Start Calculator
Suite Teardown    Terminate All Processes    kill=True
Test Setup        Clear Calculator

*** Variables ***
${CONFIG}         ${CURDIR}${/}vizdom.ci.config.json
${APP}            ${CURDIR}${/}app${/}demo_calculator.py
${TITLE}          VizDOM Demo Calculator
${TIMEOUT}        60s

*** Test Cases ***
Screen Is Read As A Visual DOM
    [Documentation]    The keys and the display are found from pixels alone.
    Dump Visual DOM
    Visual Should Exist          text=Plus
    Visual Should Exist          text=Equals
    Visual Should Exist          text=Clear
    Visual Should Exist          text=8

Calculator Adds Two Numbers
    [Documentation]    8 + 5 = 13, driven by what VizDOM sees on screen.
    Dump Visual DOM
    Click Visual                 text=8
    Click Visual                 text=Plus
    Click Visual                 text=5
    Click Visual                 text=Equals
    Wait Until Visual Appears    text=13    timeout=${TIMEOUT}

Calculator Subtracts Two Numbers
    [Documentation]    99 - 1 = 98. The keys do not move, so one dump serves
    ...                every click; only the result is read from a new capture.
    ...                Results are chosen so no key carries the same text.
    Dump Visual DOM
    Click Visual                 text=9
    Click Visual                 text=9
    Click Visual                 text=Minus
    Click Visual                 text=1
    Click Visual                 text=Equals
    Wait Until Visual Appears    text=98    timeout=${TIMEOUT}

Fallback Chain Rescues A Stale Locator
    [Documentation]    ADR-024: the first alternative no longer matches anything,
    ...                the second one does, and the click still lands.
    Dump Visual DOM
    Click Visual                 text=Eight || text=8
    Click Visual                 text=Eight || text=8
    Wait Until Visual Appears    text=88    timeout=${TIMEOUT}

*** Keywords ***
Start Calculator
    ${python}=    Evaluate    sys.executable    modules=sys
    Start Process    ${python}    ${APP}    alias=calculator
    ...    stdout=${OUTPUT DIR}${/}calculator.log    stderr=STDOUT
    Connect    ${CONFIG}
    Wait Until Keyword Succeeds    ${TIMEOUT}    2s    Bring App To Front    ${TITLE}

Clear Calculator
    Bring App To Front    ${TITLE}
    Press Key             esc
