*** Settings ***
Resource    ../resources/common.resource

*** Keywords ***
Open Profile Browser
    [Documentation]    Same name as the common one, defined again here.
    Log    duplicate

Open Cases Page
    [Arguments]    ${role}
    Open Authenticated Browser    ${role}
