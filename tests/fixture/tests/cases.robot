*** Settings ***
Resource    ../collections/cases_page.resource
Suite Setup    Open Profile Browser    suite

*** Test Cases ***
Change Zone NEW Lists Zones
    [Documentation]    PROJ-2120: the zone search lists zones without a key press.
    [Tags]    bug:PROJ-2120    role:role_team_lead    op:GET /api/zones/list
    Open Cases Page    role_team_lead

Cases Page Opens For QC
    [Tags]    role:role_quality_control
    Open Cases Page    role_quality_control
