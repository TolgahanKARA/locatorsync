*** Settings ***
Documentation    Uygulama locator değişkenleri

*** Variables ***
# --- Login Sayfası ---
# STABLE: data-test kullanılıyor
${USERNAME_INPUT}       css=[data-test='username-input']
${FORGOT_PWD_LINK}      css=[data-test='forgot-password-link']

# FRAGILE: sadece class, kırılabilir
${PASSWORD_INPUT}       css=.input-password
${LOGIN_BUTTON}         css=.btn-login

# BROKEN: bu class Vue'da artık yok (refactor sonrası)
${OLD_LOGIN_BTN}        css=.login-submit-btn

# --- Ürün Listesi ---
# STABLE
${SEARCH_INPUT}         css=[data-test='search-input']
${SORT_SELECT}          id=sort-select

# FRAGILE: class tabanlı
${ADD_TO_CART_BTN}      css=.btn-add-cart
${PRODUCT_DETAIL_BTN}   css=.btn-detail

# VERY FRAGILE: index tabanlı XPath
${FIRST_PRODUCT_BTN}    xpath=//div[@class='product-grid']/div[1]/button[1]

# BROKEN: bu element artık yok
${OLD_FILTER_BTN}       css=.filter-panel .apply-filters-btn

# FRAGILE: derin CSS
${DEEP_CSS}             css=.product-list > .product-grid > .product-card > .btn-add-cart
