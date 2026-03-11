"""
LocatorExtractor testleri — demo Robot Framework dosyaları üzerinde.
"""
import pytest
from configs.AppConfig import AppConfig
from core.analyzer.LocatorExtractor import LocatorExtractor


@pytest.fixture
def extractor():
    config = AppConfig("config.yaml")
    return LocatorExtractor(config)


class TestLocatorExtractorIntegration:
    def test_files_scanned(self, extractor):
        result = extractor.extract()
        assert result.files_scanned >= 3  # login_tests, product_tests, locators.resource

    def test_locators_found(self, extractor):
        result = extractor.extract()
        assert result.total_locators > 0

    def test_variable_locators_found(self, extractor):
        """locators.resource içindeki Variables bölümündeki locator'lar yakalanmalı."""
        result = extractor.extract()
        assert result.variable_locators > 0

    def test_data_test_locator_present(self, extractor):
        """data-test kullanan locator'lar listede bulunmalı."""
        result = extractor.extract()
        values = [loc.value for loc in result.locators]
        data_test_locs = [v for v in values if "data-test" in v]
        assert len(data_test_locs) > 0

    def test_locator_has_stability_score(self, extractor):
        result = extractor.extract()
        for loc in result.locators:
            assert isinstance(loc.stability_score, int)
            assert 0 <= loc.stability_score <= 100

    def test_by_type_grouping(self, extractor):
        result = extractor.extract()
        by_type = result.by_type()
        # En az CSS veya XPath tipi olmalı
        assert len(by_type) > 0

    def test_by_file_grouping(self, extractor):
        result = extractor.extract()
        by_file = result.by_file()
        assert len(by_file) >= 2
