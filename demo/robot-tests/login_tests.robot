*** Settings ***
Documentation    Login akışı testleri
Resource         resources/locators.resource

*** Test Cases ***
Kullanici Basarili Giris Yapabilmeli
    Open Browser    ${BASE_URL}    chrome
    Input Text      ${USERNAME_INPUT}    testuser
    Input Text      ${PASSWORD_INPUT}    password123
    Click Element   ${LOGIN_BUTTON}
    Wait Until Page Contains    Dashboard

Kullanici Sifre Unutma Linkine Tiklanabilmeli
    Open Browser    ${BASE_URL}    chrome
    Click Element   ${FORGOT_PWD_LINK}
    Wait Until Page Contains    Şifre Sıfırlama

*** Keywords ***
Login With Credentials
    [Arguments]    ${user}    ${pass}
    Input Text      ${USERNAME_INPUT}    ${user}
    Input Text      css=.input-password    ${pass}
    Click Element   ${OLD_LOGIN_BTN}
