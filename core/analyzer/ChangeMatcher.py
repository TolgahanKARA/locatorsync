"""
ChangeMatcher - Vue elementleri ile Robot locator'larını eşleştirir.
Hangi locator'ın Vue'da karşılığı yok → kırık locator tespiti.
"""
import re
from difflib import SequenceMatcher
from typing import Optional

from models.VueElement import VueElement
from models.RobotLocator import RobotLocator
from models.AnalysisResult import MatchResult, CrossAnalysisResult


class ChangeMatcher:
    def __init__(self, config):
        self.config = config
        self._vue_classes: set = set()
        self._vue_ids: set = set()
        self._vue_data_tests: set = set()
        self._vue_names: set = set()
        self._vue_aria_labels: set = set()
        self._vue_elements: list = []

    def analyze(
        self,
        vue_elements: list[VueElement],
        robot_locators: list[RobotLocator],
        ignore_list: list = None,
    ) -> CrossAnalysisResult:
        """Çapraz analiz yap."""
        self._build_vue_index(vue_elements)
        self._vue_elements = vue_elements

        result = CrossAnalysisResult()
        ignore_list = ignore_list or []

        for loc in robot_locators:
            if loc.value in ignore_list:
                continue

            match_result = self._match_locator(loc)
            result.matches.append(match_result)

            if match_result.is_broken:
                result.broken.append(match_result)
            elif match_result.is_risky:
                result.risky.append(match_result)
            else:
                result.healthy.append(match_result)

        # Kullanılmayan Vue elementleri bul (VueElement hashable değil, id() kullan)
        used_element_ids = {id(m.matched_element) for m in result.matches if m.matched_element}
        result.unmatched_vue = [
            el for el in vue_elements
            if el.is_interactive and id(el) not in used_element_ids
        ]

        result.summary = self._build_summary(result, vue_elements, robot_locators)
        return result

    def _build_vue_index(self, elements: list[VueElement]):
        """Hızlı arama için index oluştur."""
        self._vue_classes = set()
        self._vue_ids = set()
        self._vue_data_tests = set()
        self._vue_names = set()
        self._vue_aria_labels = set()

        for el in elements:
            self._vue_classes.update(el.classes)
            if el.element_id:
                self._vue_ids.add(el.element_id)
            if el.data_test:
                self._vue_data_tests.add(el.data_test)
            if el.data_testid:
                self._vue_data_tests.add(el.data_testid)
            if el.name:
                self._vue_names.add(el.name)
            if el.aria_label:
                self._vue_aria_labels.add(el.aria_label)

    def _match_locator(self, loc: RobotLocator) -> MatchResult:
        """Locator'ı Vue elementleriyle eşleştir."""
        v = loc.value.strip()
        threshold = self.config.stability_threshold

        if loc.locator_type == "css":
            return self._match_css(loc, v.replace("css=", "").replace("css:", "").strip())

        if loc.locator_type == "xpath":
            return self._match_xpath(loc, v)

        if loc.locator_type == "id":
            return self._match_id(loc, v.replace("id=", "").strip())

        if loc.locator_type == "name":
            return self._match_name(loc, v.replace("name=", "").strip())

        if loc.locator_type == "aria":
            return self._match_aria(loc, re.sub(r"aria-label=", "", v).strip())

        if loc.locator_type in ("text", "link"):
            return self._match_text(loc)

        return MatchResult(
            locator=loc,
            is_risky=loc.stability_score < threshold,
            match_confidence=0.5,
        )

    def _match_css(self, loc: RobotLocator, css: str) -> MatchResult:
        """CSS selector analizi."""
        dt_match = re.search(r"\[data-test(?:id)?=['\"]([^'\"]+)['\"]", css)
        if dt_match:
            dt_val = dt_match.group(1)
            if dt_val in self._vue_data_tests:
                el = self._find_element_by_data_test(dt_val)
                return MatchResult(locator=loc, matched_element=el, match_confidence=1.0)
            similar = self._fuzzy_find(dt_val, self._vue_data_tests)
            return MatchResult(
                locator=loc,
                matched_element=None,
                is_broken=True,
                match_confidence=similar[1] if similar else 0.0,
                break_reason=f"data-test='{dt_val}' Vue'da bulunamadı"
                + (f" (en yakın: '{similar[0]}')" if similar else ""),
            )

        id_match = re.search(r"#([a-zA-Z][\w-]*)", css)
        if id_match:
            id_val = id_match.group(1)
            if id_val in self._vue_ids:
                el = self._find_element_by_id(id_val)
                return MatchResult(locator=loc, matched_element=el, match_confidence=0.95)
            return MatchResult(
                locator=loc,
                is_broken=True,
                break_reason=f"id='{id_val}' Vue'da bulunamadı",
            )

        class_matches = re.findall(r"\.([a-zA-Z][\w-]*)", css)
        if class_matches:
            found = [c for c in class_matches if c in self._vue_classes]
            missing = [c for c in class_matches if c not in self._vue_classes]

            if missing and not found:
                closest = self._fuzzy_find(missing[0], self._vue_classes)
                return MatchResult(
                    locator=loc,
                    is_broken=True,
                    break_reason=f".{missing[0]} Vue'da bulunamadı"
                    + (f" (en yakın: '.{closest[0]}')" if closest else ""),
                    match_confidence=closest[1] if closest else 0.0,
                )
            if missing:
                return MatchResult(
                    locator=loc,
                    is_risky=True,
                    match_confidence=len(found) / len(class_matches),
                    break_reason=f"Bazı class'lar Vue'da yok: {missing}",
                )
            el = self._find_element_by_class(class_matches[0])
            return MatchResult(
                locator=loc,
                matched_element=el,
                match_confidence=0.7,
                is_risky=loc.stability_score < self.config.stability_threshold,
            )

        return MatchResult(locator=loc, is_risky=True, match_confidence=0.3)

    def _match_xpath(self, loc: RobotLocator, xpath: str) -> MatchResult:
        """XPath için basit analiz."""
        dt = re.search(r"@data-test(?:id)?=['\"]([^'\"]+)['\"]", xpath)
        if dt:
            val = dt.group(1)
            if val in self._vue_data_tests:
                el = self._find_element_by_data_test(val)
                return MatchResult(locator=loc, matched_element=el, match_confidence=0.95)
            return MatchResult(
                locator=loc,
                is_broken=True,
                break_reason=f"XPath data-test='{val}' Vue'da bulunamadı",
            )

        id_m = re.search(r"@id=['\"]([^'\"]+)['\"]", xpath)
        if id_m:
            val = id_m.group(1)
            if val in self._vue_ids:
                return MatchResult(locator=loc, match_confidence=0.85)
            return MatchResult(
                locator=loc,
                is_broken=True,
                break_reason=f"XPath @id='{val}' Vue'da bulunamadı",
            )

        class_m = re.search(r"@class=['\"]([^'\"]+)['\"]", xpath)
        if class_m:
            cls = class_m.group(1).split()[0]
            if cls in self._vue_classes:
                return MatchResult(locator=loc, match_confidence=0.5, is_risky=True)
            return MatchResult(
                locator=loc,
                is_broken=True,
                break_reason=f"XPath class='{cls}' Vue'da bulunamadı",
            )

        return MatchResult(
            locator=loc,
            is_risky=loc.stability_score < self.config.stability_threshold,
            match_confidence=0.4,
        )

    def _match_id(self, loc: RobotLocator, id_val: str) -> MatchResult:
        if id_val in self._vue_ids:
            el = self._find_element_by_id(id_val)
            return MatchResult(locator=loc, matched_element=el, match_confidence=1.0)
        similar = self._fuzzy_find(id_val, self._vue_ids)
        return MatchResult(
            locator=loc,
            is_broken=True,
            break_reason=f"id='{id_val}' Vue'da bulunamadı"
            + (f" (en yakın: '{similar[0]}')" if similar else ""),
            match_confidence=similar[1] if similar else 0.0,
        )

    def _match_name(self, loc: RobotLocator, name_val: str) -> MatchResult:
        if name_val in self._vue_names:
            return MatchResult(locator=loc, match_confidence=0.9)
        return MatchResult(
            locator=loc,
            is_broken=True,
            break_reason=f"name='{name_val}' Vue'da bulunamadı",
        )

    def _match_aria(self, loc: RobotLocator, aria_val: str) -> MatchResult:
        if aria_val in self._vue_aria_labels:
            return MatchResult(locator=loc, match_confidence=0.85)
        return MatchResult(
            locator=loc,
            is_risky=True,
            break_reason=f"aria-label='{aria_val}' Vue'da bulunamadı",
        )

    def _match_text(self, loc: RobotLocator) -> MatchResult:
        """Text tabanlı locator'lar — eşleşmesi zor, risky say."""
        return MatchResult(
            locator=loc,
            is_risky=True,
            match_confidence=0.5,
            break_reason="Text tabanlı locator kırılgandır.",
        )

    def _fuzzy_find(self, target: str, candidates: set, threshold: float = 0.5) -> Optional[tuple]:
        """En benzer string'i bul."""
        best = None
        best_score = threshold
        for cand in candidates:
            score = SequenceMatcher(None, target.lower(), cand.lower()).ratio()
            if score > best_score:
                best_score = score
                best = cand
        return (best, best_score) if best else None

    def _find_element_by_data_test(self, value: str) -> Optional[VueElement]:
        for el in self._vue_elements:
            if el.data_test == value or el.data_testid == value:
                return el
        return None

    def _find_element_by_id(self, id_val: str) -> Optional[VueElement]:
        for el in self._vue_elements:
            if el.element_id == id_val:
                return el
        return None

    def _find_element_by_class(self, cls: str) -> Optional[VueElement]:
        for el in self._vue_elements:
            if cls in el.classes:
                return el
        return None

    def _build_summary(
        self,
        result: CrossAnalysisResult,
        vue_elements: list,
        robot_locators: list,
    ) -> dict:
        total = len(result.matches)
        return {
            "total_robot_locators": len(robot_locators),
            "total_vue_elements": len(vue_elements),
            "total_interactive_vue": sum(1 for e in vue_elements if e.is_interactive),
            "broken_locators": len(result.broken),
            "risky_locators": len(result.risky),
            "healthy_locators": len(result.healthy),
            "break_rate": round(len(result.broken) / total * 100, 1) if total else 0,
            "risk_rate": round(len(result.risky) / total * 100, 1) if total else 0,
            "health_rate": round(len(result.healthy) / total * 100, 1) if total else 0,
            "unmatched_vue_interactive": len(result.unmatched_vue),
        }
