*** Settings ***
Default Tags    dflt:yes

*** Test Cases ***
Has Own Tags
    [Tags]    own:yes
    Log    x

No Own Tags
    Log    y
