"""
StabilityScorer - Locator ve Vue elementlerine kırılganlık skoru verir.
Skor: 0 (çok kırılgan) → 100 (çok stabil)
"""
import re


class StabilityScorer:

    SCORES = {
        "data-test": 95,
        "data-testid": 95,
        "id_static": 85,
        "aria-label": 75,
        "name": 70,
        "role": 65,
        "text_exact": 50,
        "text_partial": 40,
        "class_semantic": 35,
        "class_ui_lib": 20,
        "css_complex": 20,
        "xpath_data_test": 90,
        "xpath_id": 80,
        "xpath_simple": 30,
        "xpath_indexed": 10,
        "xpath_deep": 15,
        "nth_child": 10,
        "unknown": 25,
    }

    UI_LIB_PREFIXES = (
        "el-", "ant-", "q-", "md-", "n-", "p-",
        "mdc-", "mat-", "v-btn", "v-card", "v-text",
        "el-button", "el-input", "bx--",
    )

    @classmethod
    def score_locator(cls, locator_value: str) -> tuple[int, str]:
        if not locator_value:
            return 25, "unknown"
        v = locator_value.strip()
        if re.search(r"\[data-test", v, re.IGNORECASE) or re.search(r"data-test=", v, re.IGNORECASE):
            return cls.SCORES["data-test"], "data-test"
        if v.startswith("xpath=") or v.startswith("//") or v.startswith("(//"):
            return cls._score_xpath(v)
        if v.startswith("css="):
            return cls._score_css(v[4:])
        if v.startswith("id="):
            id_val = v[3:]
            if re.search(r"\d{3,}", id_val):
                return 50, "id_dynamic"
            return cls.SCORES["id_static"], "id_static"
        if v.startswith("name="):
            return cls.SCORES["name"], "name"
        if v.startswith("aria-label=") or "aria-label" in v:
            return cls.SCORES["aria-label"], "aria-label"
        if v.startswith("link="):
            return cls.SCORES["text_exact"], "text_exact"
        if v.startswith("partial link="):
            return cls.SCORES["text_partial"], "text_partial"
        if v.startswith("text="):
            return cls.SCORES["text_exact"], "text_exact"
        if v.startswith("."):
            return cls._score_css(v)
        if v.startswith("#"):
            return cls.SCORES["id_static"], "id_static"
        return cls.SCORES["unknown"], "unknown"

    @classmethod
    def _score_css(cls, css: str) -> tuple[int, str]:
        if ":nth-child" in css or ":nth-of-type" in css:
            return cls.SCORES["nth_child"], "nth_child"
        if css.count(">") > 2 or css.count(" ") > 3:
            return cls.SCORES["css_complex"], "css_complex"
        if "data-test" in css or "data-testid" in css:
            return cls.SCORES["data-test"], "data-test"
        if css.startswith("#") or "[id=" in css:
            return cls.SCORES["id_static"], "id_static"
        if "aria-label" in css:
            return cls.SCORES["aria-label"], "aria-label"
        if any(css.lstrip(".").startswith(prefix) for prefix in cls.UI_LIB_PREFIXES):
            return cls.SCORES["class_ui_lib"], "class_ui_lib"
        if css.count(".") > 2:
            return cls.SCORES["css_complex"], "css_complex"
        if css.startswith(".") and not any(c.isdigit() for c in css):
            return cls.SCORES["class_semantic"], "class_semantic"
        return cls.SCORES["unknown"], "unknown"

    @classmethod
    def _score_xpath(cls, xpath: str) -> tuple[int, str]:
        x = xpath.replace("xpath=", "")
        if "@data-test" in x or "@data-testid" in x:
            return cls.SCORES["xpath_data_test"], "xpath_data_test"
        if "@id=" in x and not re.search(r"\d{4,}", x):
            return cls.SCORES["xpath_id"], "xpath_id"
        if re.search(r"\[\d+\]", x):
            return cls.SCORES["xpath_indexed"], "xpath_indexed"
        depth = x.count("/") - x.count("//")
        if depth > 5:
            return cls.SCORES["xpath_deep"], "xpath_deep"
        return cls.SCORES["xpath_simple"], "xpath_simple"

    @classmethod
    def score_vue_element(cls, element) -> int:
        if element.data_test or element.data_testid:
            return 95
        if element.element_id:
            if re.search(r"[0-9a-f]{8}-|__\d+", element.element_id):
                return 40
            return 85
        if element.aria_label:
            return 75
        if element.name:
            return 70
        if element.inner_text and len(element.inner_text) < 30:
            return 50
        if element.classes:
            if any(
                any(c.startswith(p) for p in cls.UI_LIB_PREFIXES)
                for c in element.classes
            ):
                return 20
            return 35
        return 10

    @classmethod
    def label(cls, score: int) -> str:
        if score >= 80:
            return "YÜKSEK"
        if score >= 50:
            return "ORTA"
        if score >= 30:
            return "DÜŞÜK"
        return "KRİTİK"

    @classmethod
    def color(cls, score: int) -> str:
        if score >= 80:
            return "green"
        if score >= 50:
            return "yellow"
        if score >= 30:
            return "orange1"
        return "red"
