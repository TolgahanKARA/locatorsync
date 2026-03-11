"""
DataTestAuditor - Vue bileşenlerinde data-test/data-testid eksikliklerini raporlar.
Testability governance için temel analiz modülü.
"""
import re
from pathlib import Path
from typing import Optional

from models.VueElement import VueElement
from models.AnalysisResult import AuditIssue, AuditReport
from core.scanner.VueScanner import VueScanner


class DataTestAuditor:
    def __init__(self, config):
        self.config = config
        self.scanner = VueScanner(config)

    def audit(self) -> AuditReport:
        """Tam data-test denetimi yap."""
        elements = self.scanner.scan()
        report = AuditReport(
            total_elements=len(elements),
            files_scanned=self.scanner.scanned_files,
        )

        interactive = [e for e in elements if e.is_interactive]
        report.total_interactive = len(interactive)

        for el in interactive:
            if el.data_test or el.data_testid:
                report.covered += 1
            else:
                issue = self._create_issue(el)
                report.issues.append(issue)

        if report.total_interactive > 0:
            report.coverage_percent = round(
                report.covered / report.total_interactive * 100, 1
            )

        return report

    def _create_issue(self, el: VueElement) -> AuditIssue:
        """Element için uygun sorun kaydı oluştur."""
        severity = self._determine_severity(el)
        suggestion, suggested_data_test = self._generate_suggestion(el)
        message = self._generate_message(el)

        return AuditIssue(
            severity=severity,
            element=el,
            message=message,
            suggestion=suggestion,
            suggested_data_test=suggested_data_test,
        )

    def _determine_severity(self, el: VueElement) -> str:
        """
        Kritiklik seviyesi belirle:
        - critical: locator'ı hiç yok, tamamen körü körüne
        - warning: sadece class/text var, kırılgan
        - info: id veya name var ama data-test yok
        """
        has_id = bool(el.element_id)
        has_name = bool(el.name)
        has_class = bool(el.classes)
        has_text = bool(el.inner_text)
        has_aria = bool(el.aria_label)

        if not any([has_id, has_name, has_class, has_text, has_aria]):
            return "critical"
        if has_id or has_name or has_aria:
            return "info"
        return "warning"

    def _generate_suggestion(self, el: VueElement) -> tuple[str, Optional[str]]:
        """Geliştirici için önerilen data-test değerini üret."""
        suggested = self._derive_data_test_name(el)
        if suggested:
            vue_attr = f'data-test="{suggested}"'
            return (
                f"Elementa şu attribute eklenebilir: {vue_attr}",
                suggested,
            )
        return (
            f"<{el.tag}> elementine anlamlı bir data-test attribute ekleyin.",
            None,
        )

    def _derive_data_test_name(self, el: VueElement) -> Optional[str]:
        """
        Element özelliklerine bakarak uygun data-test ismi türet.
        Öncelik: text > name > id > class > tag
        """
        def slugify(s: str) -> str:
            s = s.lower().strip()
            s = re.sub(r"[^\w\s-]", "", s)
            s = re.sub(r"[\s_]+", "-", s)
            s = re.sub(r"-+", "-", s)
            return s.strip("-")[:40]

        if el.inner_text and len(el.inner_text) < 25:
            return f"{el.tag}-{slugify(el.inner_text)}"

        if el.name:
            return f"{el.tag}-{slugify(el.name)}"

        if el.element_id:
            return slugify(el.element_id)

        if el.aria_label:
            return f"{el.tag}-{slugify(el.aria_label)}"

        if el.classes:
            semantic_classes = [
                c for c in el.classes
                if not any(c.startswith(p) for p in (
                    "el-", "ant-", "q-", "md-", "v-", "n-", "p-"
                ))
            ]
            if semantic_classes:
                return slugify(semantic_classes[0])

        return el.tag

    def _generate_message(self, el: VueElement) -> str:
        loc = Path(el.file).name
        return (
            f"<{el.tag}> elementi data-test/data-testid attribute'u içermiyor "
            f"({loc}:{el.line})"
        )
