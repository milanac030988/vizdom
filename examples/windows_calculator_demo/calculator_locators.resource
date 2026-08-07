*** Comments ***
# ==============================================================================
# Calculator element locators — text with a description fallback (ADR-024)
# ==============================================================================
# Each control is defined as a FALLBACK CHAIN:
#
#     text=<literal read>  ||  desc=<what the control is>
#
# * space  = AND within one alternative (unchanged semantics)
# * ``||`` = ordered OR — alternatives are tried left to right, and the first
#            that resolves to exactly ONE element wins.
#
# Why both:
#   - ``text=`` is free and deterministic: a pure lookup in the Visual DOM. It is
#     tried first, so the happy path costs nothing.
#   - ``desc=`` is the safety net for exactly the cases we measured breaking:
#     OCR misreads a small glyph, or an icon caption is unstable. Operator keys
#     have no readable label at all, so their literal read comes from the symbol
#     reader and their fallback is a description.
#
# An alternative is abandoned when it matches NOTHING *or* is AMBIGUOUS, and when
# a fallback wins the library logs a warning naming the stale primary — treat
# that warning as a signal to update the primary locator.
# ==============================================================================

*** Variables ***
# --- digits -------------------------------------------------------------------
${BTN_0}          text=0 || desc="digit zero button"
${BTN_1}          text=1 || desc="digit one button"
${BTN_2}          text=2 || desc="digit two button"
${BTN_3}          text=3 || desc="digit three button"
${BTN_4}          text=4 || desc="digit four button"
${BTN_5}          text=5 || desc="digit five button"
${BTN_6}          text=6 || desc="digit six button"
${BTN_7}          text=7 || desc="digit seven button"
${BTN_8}          text=8 || desc="digit eight button"
${BTN_9}          text=9 || desc="digit nine button"

# --- operators ----------------------------------------------------------------
# `text` here comes from the symbol reader (a literal pixel read of the glyph);
# the canonical label ("Divide", "Multiply", ...) is what `desc` matches on.
${BTN_ADD}        text="+" || desc="plus button"
${BTN_SUBTRACT}   text="-" || desc="minus button"
${BTN_MULTIPLY}   text="×" || desc="multiply button"
${BTN_DIVIDE}     text="÷" || desc="divide button"
${BTN_EQUALS}     text="=" || desc="equals button"
${BTN_DECIMAL}    text="." || desc="decimal point button"

# --- editing ------------------------------------------------------------------
${BTN_CLEAR}      text=C || desc="clear button"
${BTN_BACKSPACE}  desc="backspace button"

# --- window controls ----------------------------------------------------------
# Title-bar icons keep their caption as the semantic name, so `desc` leads here.
${BTN_CLOSE}      desc="close button" || text="×"
${BTN_MINIMIZE}   desc="minimize button"

# --- result -------------------------------------------------------------------
# The display has no stable caption; match the value, fall back to the role.
${DISPLAY}        role=text || desc="calculator result display"


*** Keywords ***
Enter Number
    [Documentation]    Click the digit buttons that spell ``number``.
    ...                Each digit resolves through its own text||desc chain.
    [Arguments]    ${number}
    FOR    ${digit}    IN    @{{ list(str($number)) }}
        IF    '${digit}' == '.'
            Click Visual    ${BTN_DECIMAL}
        ELSE
            # Nested variable: ${digit} resolves first, giving ${BTN_7} etc.
            Click Visual    ${BTN_${digit}}
        END
    END

Compute
    [Documentation]    Enter ``a <op> b`` and press equals. ``op`` is one of
    ...                add | subtract | multiply | divide.
    [Arguments]    ${a}    ${op}    ${b}
    Enter Number    ${a}
    IF    '${op}' == 'add'
        Click Visual    ${BTN_ADD}
    ELSE IF    '${op}' == 'subtract'
        Click Visual    ${BTN_SUBTRACT}
    ELSE IF    '${op}' == 'multiply'
        Click Visual    ${BTN_MULTIPLY}
    ELSE IF    '${op}' == 'divide'
        Click Visual    ${BTN_DIVIDE}
    ELSE
        Fail    Unknown operator: ${op}
    END
    Enter Number    ${b}
    Click Visual    ${BTN_EQUALS}
