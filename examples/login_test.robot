*** Settings ***
Documentation    Example: Visual login test using Visual GUI Library
Library          VisualGuiLibrary    platform=desktop

*** Variables ***
${TIMEOUT}       10s

*** Test Cases ***
Login With Valid Credentials
    [Documentation]    Test login flow using visual element detection

    # Capture initial screen and generate DOM
    ${img}=    Capture Screen
    ${dom}=    Dump Visual DOM    ${img}

    # Wait for login form to appear
    Wait Until Visual Appears    text=Email    timeout=${TIMEOUT}

    # Enter credentials
    Click Visual                 hint=Email
    Type Text Visual             hint=Email    user@example.com

    Click Visual                 hint=Password
    Type Text Visual             hint=Password    P@ssw0rd

    # Submit login
    Click Visual                 text=Login

    # Verify successful login
    Wait Until Visual Appears    text=Welcome    timeout=${TIMEOUT}
    Visual Should Exist          text=Dashboard

Login Should Fail With Invalid Password
    [Documentation]    Verify error message on invalid login

    Wait Until Visual Appears    text=Email    timeout=${TIMEOUT}

    Click Visual                 hint=Email
    Type Text Visual             hint=Email    user@example.com

    Click Visual                 hint=Password
    Type Text Visual             hint=Password    wrongpassword

    Click Visual                 text=Login

    # Verify error message appears
    Wait Until Visual Appears    text=Invalid credentials    timeout=${TIMEOUT}
    Visual Should Not Exist      text=Welcome
