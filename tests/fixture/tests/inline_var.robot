*** Test Cases ***
Inline Var Test
    VAR    ${END_INLINE}    /api/inline/query
    Log    ${END_INLINE}

*** Keywords ***
Inline Var KW
    VAR    ${LOCAL_INLINE}    /api/local/query
    Log    ${LOCAL_INLINE}
