"""
VueScanner - .vue dosyalarını tarar, template içindeki elementleri çıkarır.
"""
import re
from pathlib import Path
from typing import Optional

from models.VueElement import VueElement
from core.analyzer.StabilityScorer import StabilityScorer

INTERACTIVE_TAGS = {
    "button", "input", "select", "textarea", "a", "form",
    "label", "option", "datalist", "output", "meter", "progress",
}

UI_LIB_PREFIXES = (
    "v-", "el-", "ant-", "q-", "md-", "b-", "n-", "p-",
    "mdc-", "mat-", "vuetify", "buefy", "bootstrap",
)


class VueScanner:
    def __init__(self, config):
        self.config = config
        self.elements: list[VueElement] = []
        self._scanned_files: int = 0

    def scan(self) -> list[VueElement]:
        self.elements = []
        self._scanned_files = 0
        vue_path = self.config.vue_path
        if not vue_path or not vue_path.exists():
            return []
        for ext in self.config.vue_extensions:
            for vue_file in self._find_files(vue_path, ext):
                self._scan_file(vue_file)
        return self.elements

    def _find_files(self, root: Path, ext: str):
        ignore = set(self.config.ignore_dirs)
        for path in root.rglob(f"*{ext}"):
            if not any(part in ignore for part in path.parts):
                yield path

    def _scan_file(self, file_path: Path):
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return
        self._scanned_files += 1
        template = self._extract_template(content)
        if not template:
            return
        base_line = self._find_template_start_line(content)
        elements = self._parse_elements(template, str(file_path), base_line)
        self.elements.extend(elements)

    def _extract_template(self, content: str) -> Optional[str]:
        match = re.search(r"<template[^>]*>([\s\S]*?)</template>", content, re.IGNORECASE)
        return match.group(1) if match else None

    def _find_template_start_line(self, content: str) -> int:
        for i, line in enumerate(content.split("\n"), 1):
            if re.match(r"\s*<template", line, re.IGNORECASE):
                return i
        return 1

    def _parse_elements(self, template: str, file_path: str, base_line: int) -> list[VueElement]:
        elements = []
        tag_pattern = re.compile(r"<([a-zA-Z][a-zA-Z0-9\-]*)\s*([^>]*?)(/?>)", re.DOTALL)
        for match in tag_pattern.finditer(template):
            tag = match.group(1).lower()
            attrs_str = match.group(2)
            line_offset = template[: match.start()].count("\n")
            line = base_line + line_offset
            attrs = self._parse_attributes(attrs_str)
            inner_text = self._extract_inner_text(template, match.end(), tag)
            # Hem statik (data-test) hem dynamic (:data-test) binding desteklenir
            static_dt   = attrs.get("data-test")
            dynamic_dt  = attrs.get(":data-test")
            static_dtid = attrs.get("data-testid")
            dynamic_dtid= attrs.get(":data-testid")
            static_id   = attrs.get("id")
            dynamic_id  = attrs.get(":id")
            is_dynamic  = bool(dynamic_dt or dynamic_dtid)

            element = VueElement(
                tag=tag,
                file=file_path,
                line=line,
                data_test=static_dt or dynamic_dt,
                data_testid=static_dtid or dynamic_dtid,
                element_id=static_id or dynamic_id,
                classes=self._parse_classes(attrs.get("class", "")),
                name=attrs.get("name"),
                aria_label=attrs.get("aria-label"),
                inner_text=inner_text,
                is_interactive=(tag in INTERACTIVE_TAGS),
                has_v_if="v-if" in attrs,
                has_v_show="v-show" in attrs,
                is_dynamic_binding=is_dynamic,
            )
            element.stability_score = StabilityScorer.score_vue_element(element)
            elements.append(element)
        return elements

    def _parse_attributes(self, attrs_str: str) -> dict:
        attrs = {}
        for m in re.finditer(r'([\w\-:@.]+)\s*=\s*["\']([^"\']*)["\']', attrs_str):
            raw_key = m.group(1)
            if raw_key.startswith("v-bind:"):
                key = raw_key[len("v-bind:"):]
                attrs[f":{key}"] = m.group(2)
            elif raw_key.startswith(":"):
                key = raw_key[1:]
                attrs[f":{key}"] = m.group(2)
            else:
                attrs[raw_key] = m.group(2)
        for m in re.finditer(r'\b(v-if|v-show|v-else|disabled|required|readonly)\b', attrs_str):
            attrs[m.group(1)] = True
        return attrs

    def _parse_classes(self, class_str: str) -> list:
        if not class_str:
            return []
        return [c.strip() for c in class_str.split() if c.strip()]

    def _extract_inner_text(self, template: str, pos: int, tag: str) -> Optional[str]:
        closing = f"</{tag}>"
        end = template.find(closing, pos)
        if end == -1:
            return None
        inner = re.sub(r"<[^>]+>", "", template[pos:end]).strip()
        inner = re.sub(r"\{\{[^}]+\}\}", "", inner).strip()
        return inner[:100] if inner else None

    @property
    def scanned_files(self) -> int:
        return self._scanned_files

    def get_interactive_elements(self) -> list[VueElement]:
        return [e for e in self.elements if e.is_interactive]

    def get_all_data_tests(self) -> set:
        dt = set()
        for el in self.elements:
            if el.data_test:
                dt.add(el.data_test)
            if el.data_testid:
                dt.add(el.data_testid)
        return dt

    def get_all_ids(self) -> set:
        return {el.element_id for el in self.elements if el.element_id}
