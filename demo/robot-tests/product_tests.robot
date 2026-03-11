*** Settings ***
Documentation    Ürün listesi testleri
Resource         resources/locators.resource

*** Test Cases ***
Urun Arama Calismali
    Input Text      ${SEARCH_INPUT}    laptop
    Wait Until Element Is Visible    css=.product-card

Sepete Urun Eklenebilmeli
    Click Element   ${ADD_TO_CART_BTN}
    Wait Until Page Contains    Sepete eklendi

Ilk Urun Detayi Acilabilmeli
    Click Element   ${FIRST_PRODUCT_BTN}
    Wait Until Page Contains    Ürün Detayı

Eski Filtre Butonu Kullanimi
    Click Element   ${OLD_FILTER_BTN}
    # Bu test kırık - old_filter_btn artık yok

*** Keywords ***
Urun Listesini Sirala
    [Arguments]    ${sort_by}
    Select From List By Value    ${SORT_SELECT}    ${sort_by}
