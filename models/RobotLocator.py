from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class RobotLocator:
    name: Optional[str]
    value: str
    locator_type: str           # css | xpath | id | name | text | class | aria | unknown
    file: str
    line: int
    stability_score: int = 0
    stability_category: str = ""
    usage_count: int = 0
    is_variable: bool = False

    def display(self) -> str:
        if self.name:
            return f"${{{self.name}}}"
        return self.value

    def short_file(self) -> str:
        return Path(self.file).name


@dataclass
class ExtractionResult:
    locators: list = field(default_factory=list)
    files_scanned: int = 0
    total_locators: int = 0
    variable_locators: int = 0
    inline_locators: int = 0

    def by_type(self) -> dict:
        result = {}
        for loc in self.locators:
            result.setdefault(loc.locator_type, []).append(loc)
        return result

    def by_file(self) -> dict:
        result = {}
        for loc in self.locators:
            result.setdefault(loc.file, []).append(loc)
        return result
