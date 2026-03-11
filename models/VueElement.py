from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VueElement:
    tag: str
    file: str
    line: int
    data_test: Optional[str] = None
    data_testid: Optional[str] = None
    element_id: Optional[str] = None
    classes: list = field(default_factory=list)
    name: Optional[str] = None
    aria_label: Optional[str] = None
    inner_text: Optional[str] = None
    is_interactive: bool = False
    has_v_if: bool = False
    has_v_show: bool = False
    stability_score: int = 0

    def best_selector(self) -> Optional[str]:
        if self.data_test:
            return f"[data-test='{self.data_test}']"
        if self.data_testid:
            return f"[data-testid='{self.data_testid}']"
        if self.element_id:
            return f"#{self.element_id}"
        if self.name:
            return f"[name='{self.name}']"
        if self.aria_label:
            return f"[aria-label='{self.aria_label}']"
        if self.classes:
            return "." + ".".join(self.classes)
        return None

    def is_test_friendly(self) -> bool:
        return bool(self.data_test or self.data_testid)
