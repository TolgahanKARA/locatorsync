"""
LocatorExtractor - Robot Framework .robot ve .resource dosyalarından locator'ları çıkarır.
"""
import re
from pathlib import Path
from typing import Optional

from models.RobotLocator import RobotLocator, ExtractionResult
from core.analyzer.StabilityScorer import StabilityScorer

LOCATOR_PREFIXES = (
    "css=", "xpath=", "id=", "name=", "link=", "partial link=",
    "tag=", "class=", "css:", "class:", "//", "(//",
    "text=", "aria-label=",
)

LOCATOR_TYPE_MAP = {
    "css=": "css", "css:": "css",
    "xpath=": "xpath", "//": "xpath", "(//": "xpath",
    "id=": "id", "name=": "name",
    "link=": "text", "partial link=": "text", "text=": "text",
    "class=": "class", "class:": "class",
    "aria-label=": "aria", "tag=": "tag",
}


class LocatorExtractor:
    VAR_PATTERN = re.compile(r"^\s*\$\{([^}]+)\}\s+(.+)$")
    INLINE_PATTERN = re.compile(
        r"(?:^|\s+)(css=|xpath=|id=|name=|link=|partial link=|text=|class=|aria-label=|//|\(//|class:)[^\s,]+"
    )

    def __init__(self, config):
        self.config = config

    def extract(self) -> ExtractionResult:
        result = ExtractionResult()
        robot_path = self.config.robot_path
        if not robot_path or not robot_path.exists():
            return result

        seen = set()
        for ext in self.config.robot_extensions:
            for robot_file in self._find_files(robot_path, ext):
                locators = self._extract_from_file(robot_file)
                result.files_scanned += 1
                for loc in locators:
                    key = (loc.value, loc.file, loc.line)
                    if key not in seen:
                        seen.add(key)
                        result.locators.append(loc)
                        if loc.is_variable:
                            result.variable_locators += 1
                        else:
                            result.inline_locators += 1

        result.total_locators = len(result.locators)
        for loc in result.locators:
            score, cat = StabilityScorer.score_locator(loc.value)
            loc.stability_score = score
            loc.stability_category = cat

        return result

    def _find_files(self, root: Path, ext: str):
        ignore = set(self.config.ignore_dirs)
        for path in root.rglob(f"*{ext}"):
            if not any(part in ignore for part in path.parts):
                yield path

    def _extract_from_file(self, file_path: Path) -> list[RobotLocator]:
        locators = []
        try:
            content = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return locators

        lines = content.split("\n")
        in_variables_section = False

        for line_num, line in enumerate(lines, 1):
            stripped = line.strip()
            if re.match(r"^\*+\s*Variables?\s*\*+", stripped, re.IGNORECASE):
                in_variables_section = True
                continue
            if re.match(r"^\*+\s*(Keywords?|Test Cases?|Settings?|Tasks?)\s*\*+", stripped, re.IGNORECASE):
                in_variables_section = False
                continue
            if stripped.startswith("#"):
                continue

            if in_variables_section:
                loc = self._try_extract_variable(line, line_num, str(file_path))
                if loc:
                    locators.append(loc)
            else:
                locators.extend(self._try_extract_inline(line, line_num, str(file_path)))

        return locators

    def _try_extract_variable(self, line: str, line_num: int, file: str) -> Optional[RobotLocator]:
        m = self.VAR_PATTERN.match(line)
        if not m:
            return None
        var_name = m.group(1).strip()
        value = m.group(2).strip()
        if not self._is_locator(value):
            return None
        return RobotLocator(
            name=var_name, value=value,
            locator_type=self._detect_type(value),
            file=file, line=line_num, is_variable=True,
        )

    def _try_extract_inline(self, line: str, line_num: int, file: str) -> list[RobotLocator]:
        locators = []
        for part in re.split(r"\s{2,}|\t", line):
            part = part.strip()
            if self._is_locator(part):
                locators.append(RobotLocator(
                    name=None, value=part,
                    locator_type=self._detect_type(part),
                    file=file, line=line_num, is_variable=False,
                ))
        return locators

    def _is_locator(self, value: str) -> bool:
        if not value:
            return False
        return any(value.strip().startswith(prefix) for prefix in LOCATOR_PREFIXES)

    def _detect_type(self, value: str) -> str:
        v = value.strip()
        for prefix, loc_type in LOCATOR_TYPE_MAP.items():
            if v.startswith(prefix):
                return loc_type
        return "unknown"
