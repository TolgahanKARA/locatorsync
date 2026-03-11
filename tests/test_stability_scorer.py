"""
StabilityScorer testleri.
"""
import pytest
from core.analyzer.StabilityScorer import StabilityScorer


class TestScoreLocator:
    def test_data_test_css(self):
        score, cat = StabilityScorer.score_locator("css=[data-test='login-btn']")
        assert score == 95
        assert cat == "data-test"

    def test_data_testid_attr(self):
        score, cat = StabilityScorer.score_locator("[data-testid='submit']")
        assert score == 95

    def test_xpath_with_data_test(self):
        # data-test içeren XPath, ilk data-test kontrolüne takılır → 95
        score, cat = StabilityScorer.score_locator("xpath=//*[@data-test='search']")
        assert score == 95
        assert cat == "data-test"

    def test_static_id(self):
        score, cat = StabilityScorer.score_locator("id=sort-select")
        assert score == 85
        assert cat == "id_static"

    def test_hash_id(self):
        score, cat = StabilityScorer.score_locator("#sort-select")
        assert score == 85

    def test_aria_label(self):
        score, cat = StabilityScorer.score_locator("aria-label=Close")
        assert score == 75
        assert cat == "aria-label"

    def test_name_locator(self):
        score, cat = StabilityScorer.score_locator("name=username")
        assert score == 70
        assert cat == "name"

    def test_class_semantic(self):
        score, cat = StabilityScorer.score_locator("css=.login-form")
        assert score == 35
        assert cat == "class_semantic"

    def test_class_ui_lib(self):
        score, cat = StabilityScorer.score_locator("css=.el-button")
        assert score == 20
        assert cat == "class_ui_lib"

    def test_xpath_indexed(self):
        score, cat = StabilityScorer.score_locator("xpath=//div[2]/button[1]")
        assert score == 10
        assert cat == "xpath_indexed"

    def test_nth_child(self):
        score, cat = StabilityScorer.score_locator("css=.list:nth-child(3)")
        assert score == 10
        assert cat == "nth_child"

    def test_empty_locator(self):
        score, cat = StabilityScorer.score_locator("")
        assert score == 25
        assert cat == "unknown"


class TestScoreVueElement:
    def _make_element(self, **kwargs):
        from models.VueElement import VueElement
        defaults = dict(tag="button", file="test.vue", line=1)
        defaults.update(kwargs)
        return VueElement(**defaults)

    def test_data_test_gives_95(self):
        el = self._make_element(data_test="my-btn")
        assert StabilityScorer.score_vue_element(el) == 95

    def test_data_testid_gives_95(self):
        el = self._make_element(data_testid="my-btn")
        assert StabilityScorer.score_vue_element(el) == 95

    def test_static_id_gives_85(self):
        el = self._make_element(element_id="sort-select")
        assert StabilityScorer.score_vue_element(el) == 85

    def test_aria_label_gives_75(self):
        el = self._make_element(aria_label="Kapat")
        assert StabilityScorer.score_vue_element(el) == 75

    def test_name_gives_70(self):
        el = self._make_element(name="username")
        assert StabilityScorer.score_vue_element(el) == 70

    def test_ui_lib_class_gives_20(self):
        el = self._make_element(classes=["el-button", "el-button--primary"])
        assert StabilityScorer.score_vue_element(el) == 20

    def test_semantic_class_gives_35(self):
        el = self._make_element(classes=["btn-login"])
        assert StabilityScorer.score_vue_element(el) == 35

    def test_no_selector_gives_10(self):
        el = self._make_element()
        assert StabilityScorer.score_vue_element(el) == 10


class TestLabel:
    def test_high(self):
        assert StabilityScorer.label(95) == "YÜKSEK"
        assert StabilityScorer.label(80) == "YÜKSEK"

    def test_medium(self):
        assert StabilityScorer.label(75) == "ORTA"
        assert StabilityScorer.label(50) == "ORTA"

    def test_low(self):
        assert StabilityScorer.label(35) == "DÜŞÜK"
        assert StabilityScorer.label(30) == "DÜŞÜK"

    def test_critical(self):
        assert StabilityScorer.label(29) == "KRİTİK"
        assert StabilityScorer.label(10) == "KRİTİK"
