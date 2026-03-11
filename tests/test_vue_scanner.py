"""
VueScanner testleri — özellikle data-test parsing bug düzeltmesi.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from core.scanner.VueScanner import VueScanner
from models.VueElement import VueElement


def make_config(tmp_path=None):
    cfg = MagicMock()
    cfg.vue_path = tmp_path
    cfg.vue_extensions = [".vue"]
    cfg.ignore_dirs = ["node_modules", ".git", "dist", "venv"]
    return cfg


def make_scanner(tmp_path=None):
    return VueScanner(make_config(tmp_path))


# ─── _parse_attributes testleri ───────────────────────────────────

class TestParseAttributes:
    def setup_method(self):
        self.scanner = make_scanner()

    def test_data_test_not_mangled(self):
        """Bug fix: data-test, lstrip() ile 'ata-test'e dönüşmemeli."""
        attrs = self.scanner._parse_attributes('data-test="username-input"')
        assert attrs.get("data-test") == "username-input"
        assert "ata-test" not in attrs

    def test_data_testid_not_mangled(self):
        attrs = self.scanner._parse_attributes('data-testid="submit-btn"')
        assert attrs.get("data-testid") == "submit-btn"

    def test_plain_attributes(self):
        attrs = self.scanner._parse_attributes('type="text" name="username" id="user-field"')
        assert attrs["type"] == "text"
        assert attrs["name"] == "username"
        assert attrs["id"] == "user-field"

    def test_dynamic_binding_colon(self):
        """:data-test dinamik binding → ':data-test' anahtarıyla saklanmalı."""
        attrs = self.scanner._parse_attributes(':data-test="dynamicTest"')
        assert attrs.get(":data-test") == "dynamicTest"
        assert "data-test" not in attrs  # statik key olmamalı

    def test_dynamic_binding_v_bind(self):
        attrs = self.scanner._parse_attributes('v-bind:data-test="testVal"')
        assert attrs.get(":data-test") == "testVal"

    def test_v_model_not_mangled(self):
        """v-model 'model' olarak kırılmamalı."""
        attrs = self.scanner._parse_attributes('v-model="username"')
        assert attrs.get("v-model") == "username"
        assert "model" not in attrs

    def test_boolean_attributes(self):
        attrs = self.scanner._parse_attributes('disabled required v-if')
        assert attrs.get("disabled") is True
        assert attrs.get("required") is True
        assert attrs.get("v-if") is True

    def test_multiple_attributes_together(self):
        """Gerçek dünya: çok satırlı Vue input elementi."""
        attrs_str = (
            'v-model="username"\n'
            '  type="text"\n'
            '  class="form-control input-username"\n'
            '  placeholder="Kullanıcı adı"\n'
            '  data-test="username-input"\n'
            '  name="username"'
        )
        attrs = self.scanner._parse_attributes(attrs_str)
        assert attrs["data-test"] == "username-input"
        assert attrs["type"] == "text"
        assert attrs["name"] == "username"
        assert attrs["v-model"] == "username"


# ─── _parse_elements / full scan testleri ─────────────────────────

class TestParseElements:
    def setup_method(self):
        self.scanner = make_scanner()

    def _scan_template(self, template_html: str) -> list:
        return self.scanner._parse_elements(template_html, "test.vue", 1)

    def test_single_line_input_with_data_test(self):
        elements = self._scan_template('<input data-test="my-input" type="text" />')
        assert len(elements) == 1
        assert elements[0].data_test == "my-input"
        assert elements[0].tag == "input"

    def test_multiline_input_with_data_test(self):
        """Asıl bug senaryosu: çok satırlı Vue input elementi."""
        template = """<input
  v-model="username"
  type="text"
  class="form-control input-username"
  data-test="username-input"
  name="username"
/>"""
        elements = self._scan_template(template)
        assert len(elements) == 1
        assert elements[0].data_test == "username-input"

    def test_button_with_data_test(self):
        template = '<button data-test="forgot-password-link" @click="go">Şifremi Unuttum</button>'
        elements = self._scan_template(template)
        btns = [e for e in elements if e.tag == "button"]
        assert len(btns) == 1
        assert btns[0].data_test == "forgot-password-link"

    def test_element_without_data_test(self):
        elements = self._scan_template('<button class="el-button el-button--primary">Giriş</button>')
        assert elements[0].data_test is None
        assert "el-button" in elements[0].classes

    def test_element_with_id(self):
        elements = self._scan_template('<select id="sort-select" class="sort-dropdown"></select>')
        assert elements[0].element_id == "sort-select"

    def test_element_with_aria_label(self):
        elements = self._scan_template('<button aria-label="Kapat" class="close-btn">✕</button>')
        assert elements[0].aria_label == "Kapat"

    def test_interactive_flag(self):
        elements = self._scan_template('<input type="text" /><div class="wrapper"></div>')
        tags = {e.tag: e.is_interactive for e in elements}
        assert tags["input"] is True
        assert tags["div"] is False

    def test_v_if_detection(self):
        elements = self._scan_template('<button v-if class="btn">Yükle</button>')
        assert elements[0].has_v_if is True

    def test_classes_parsed_correctly(self):
        elements = self._scan_template('<button class="btn btn-primary size-lg">OK</button>')
        assert elements[0].classes == ["btn", "btn-primary", "size-lg"]

    def test_stability_score_assigned(self):
        elements = self._scan_template('<input data-test="foo" />')
        assert elements[0].stability_score == 95

    def test_stability_score_low_for_class_only(self):
        # inner_text kısa ise 50 puan verir; class-only skoru 35 olsun diye text olmadan test et
        elements = self._scan_template('<button class="some-btn"></button>')
        assert elements[0].stability_score <= 35


# ─── Demo dosyaları üzerinde entegrasyon testi ────────────────────

class TestScannerIntegration:
    def test_demo_data_tests_captured(self):
        """Demo Vue dosyalarındaki data-test değerleri doğru yakalanmalı."""
        from configs.AppConfig import AppConfig
        config = AppConfig("config.yaml")
        scanner = VueScanner(config)
        elements = scanner.scan()

        data_tests = {e.data_test for e in elements if e.data_test}
        assert "username-input" in data_tests
        assert "forgot-password-link" in data_tests
        assert "search-input" in data_tests

    def test_demo_no_false_data_test(self):
        """data-test olmayan elementlerde data_test None olmalı."""
        from configs.AppConfig import AppConfig
        config = AppConfig("config.yaml")
        scanner = VueScanner(config)
        elements = scanner.scan()

        # el-button sınıflı buton (LoginForm) data-test içermemeli
        el_buttons = [e for e in elements if "el-button" in e.classes]
        assert all(e.data_test is None for e in el_buttons)

    def test_demo_scanned_files_count(self):
        from configs.AppConfig import AppConfig
        config = AppConfig("config.yaml")
        scanner = VueScanner(config)
        scanner.scan()
        assert scanner.scanned_files == 2

    def test_get_all_data_tests(self):
        from configs.AppConfig import AppConfig
        config = AppConfig("config.yaml")
        scanner = VueScanner(config)
        scanner.scan()
        dt = scanner.get_all_data_tests()
        assert "username-input" in dt
        assert "forgot-password-link" in dt
        assert "search-input" in dt
