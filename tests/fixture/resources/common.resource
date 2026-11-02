*** Settings ***
Library    Browser

*** Variables ***
${ENDPOINT_ITEMS_QUERY}    /api/items/query
&{SHELL_RULES}
...    cases=${{ ['role_team_lead', 'role_quality_control'] }}
...    item=${{ ['role_team_lead'] }}

*** Keywords ***
Open Profile Browser
    [Documentation]    Opens a browser on a fresh profile.
    ...    Second line of docs.
    [Arguments]    ${profile}    ${headless}=${True}
    Log    ${profile}

Open Authenticated Browser
    [Arguments]    ${role}
    Open Profile Browser    ${role}
    Query Items

Query Items
    [Documentation]    POST ${ENDPOINT_ITEMS_QUERY}
    Log    ${ENDPOINT_ITEMS_QUERY}
