*** Settings ***
Documentation     End-to-end VizDOM demo on Windows, fully distributed.
...
...               Launches the Windows Calculator, reads its Visual DOM, drives it
...               by what VizDOM sees on screen, and asserts the result.
...
...               All three ports run as gRPC services, selected purely by
...               ``vizdom.config.json`` — no code change between a local and a
...               distributed run:
...                 detector :50051   (the heavy model, e.g. on a GPU host)
...                 capture  :50053   (on the machine showing the Calculator)
...                 actuator :50054   (on the machine receiving the clicks)
...
...               The suite deliberately captures as little as possible: the app
...               is opened, connected and dumped ONCE (Suite Setup); both tests
...               drive the app from that one Visual DOM. Clicks never recapture
...               — a click resolves against the cached DOM and taps — so a
...               second test only needs a fresh dump if the LAYOUT changed, not
...               because the first test clicked around. That reuse is the core
...               economics of the parse-once approach.
...
...               PREREQUISITE: start the three services first (see README.md).
...
Resource          calculator_locators.resource
Library           VisualGuiLibrary
Library           Process
Library           OperatingSystem

Suite Setup       Prepare Calculator
Suite Teardown    Terminate All Processes

*** Variables ***
${CONFIG}         ${CURDIR}${/}vizdom.config.json
${TIMEOUT}        15s

*** Test Cases ***
Calculator Adds Two Numbers
    [Documentation]    7 + 5 = 12, driven entirely by visual element detection
    ...                against the DOM captured once in Suite Setup. Every button
    ...                is located by ``text=`` with a ``desc=`` fallback (see
    ...                calculator_locators.resource).
    Compute                      7    add    5

    # The display CONTENT changed, so re-dump before asserting on it. This is
    # the one capture this test performs.
    Dump Visual DOM
    Visual Should Exist          text=12

Calculator Divides And Verifies The Display Value
    [Documentation]    Exercises the operator glyphs (÷) — reusing the previous
    ...                test's DOM: no re-open, no re-capture. The keys have not
    ...                moved, so the cached element coordinates are still valid;
    ...                only the result is read back from the live screen
    ...                (``Verify Element Value``, ADR-023 region re-OCR).
    Focus Calculator
    Press Key                    esc    # clear "12" (actuator only — no capture)

    Compute                      8    divide    2

    # ADR-023 recap: re-captures and re-OCRs ONLY this element's region, so it
    # reads the state AFTER the clicks without a full detector pass.
    Verify Element Value         text=4    4

*** Keywords ***
Prepare Calculator
    [Documentation]    One-time arrange step for the whole suite: launch the app,
    ...                configure all three ports from one file, raise the window,
    ...                normalize its state, and build the Visual DOM ONCE.
    Start Process    calc.exe    shell=True
    Sleep            3s
    # One config file configures ALL THREE ports (detector/capture/actuator).
    Connect          ${CONFIG}
    Focus Calculator
    # Reset Calculator
    Dump Visual DOM
    Wait Until Visual Appears    ${BTN_7}    timeout=${TIMEOUT}

Reset Calculator
    [Documentation]    Put the Calculator into the state the locators assume.
    ...                ``calc.exe`` re-focuses an EXISTING window with its old
    ...                state: a leftover "4" on the display makes ``text=4``
    ...                ambiguous, and Scientific mode adds keys (x², 2nd) whose
    ...                glyphs collide with digit locators. Alt+1 forces Standard
    ...                mode; Esc clears the display. Runs after Focus Calculator,
    ...                so the keys go to the Calculator.
    Press Key    alt+1
    Sleep        0.6s
    Press Key    esc
    Sleep        0.3s

Focus Calculator
    [Documentation]    Raise the Calculator before capturing (ADR-021).
    ...                VizDOM grabs the whole screen and clicks by coordinate, so
    ...                a window covering the Calculator would make it analyse the
    ...                wrong pixels and click the wrong application. The title
    ...                comes from ``capture.window_title`` in the config; the raise
    ...                happens on the machine running the capture/actuator service.
    ...                Alternative: set ``focus_before_capture: true`` in the config
    ...                to do this before every grab automatically.
    Bring App To Front
