"""
VueDiffAnalyzer - Vue projesinin eski ve yeni halini karşılaştırır.
Silinen/yeniden adlandırılan elementleri bulur, etkilenen Robot locator'larını işaretler.
"""
import re
from difflib import SequenceMatcher
from typing import Optional

from models.VueElement import VueElement
from models.RobotLocator import RobotLocator
from models.AnalysisResult import ElementChange, VueDiffResult


class VueDiffAnalyzer:

    RENAME_THRESHOLD = 0.65     # Bu benzerlik oranının üstü "yeniden adlandırıldı" sayılır

    def compare(
        self,
        old_elements: list[VueElement],
        new_elements: list[VueElement],
        robot_locators: list[RobotLocator],
    ) -> VueDiffResult:
        result = VueDiffResult()

        # ── İndeksler ──────────────────────────────────────────
        old_dt = {e.data_test: e for e in old_elements if e.data_test}
        new_dt = {e.data_test: e for e in new_elements if e.data_test}
        old_dtid = {e.data_testid: e for e in old_elements if e.data_testid}
        new_dtid = {e.data_testid: e for e in new_elements if e.data_testid}
        old_id = {e.element_id: e for e in old_elements if e.element_id}
        new_id = {e.element_id: e for e in new_elements if e.element_id}

        # data-test + data-testid birleştir
        all_old_dt = {**old_dt, **old_dtid}
        all_new_dt = {**new_dt, **new_dtid}

        # ── Robot locator referans haritası ────────────────────
        robot_dt_refs: dict[str, list] = {}
        robot_id_refs: dict[str, list] = {}

        for loc in robot_locators:
            dt_m = re.search(r"\[data-test(?:id)?=['\"]([^'\"]+)['\"]", loc.value)
            if dt_m:
                robot_dt_refs.setdefault(dt_m.group(1), []).append(loc)

            xpath_dt = re.search(r"@data-test(?:id)?=['\"]([^'\"]+)['\"]", loc.value)
            if xpath_dt:
                robot_dt_refs.setdefault(xpath_dt.group(1), []).append(loc)

            id_m = re.search(r"(?:^|\s)id=([^\s]+)", loc.value)
            if id_m:
                robot_id_refs.setdefault(id_m.group(1), []).append(loc)

            css_id = re.search(r"#([a-zA-Z][\w-]*)", loc.value)
            if css_id:
                robot_id_refs.setdefault(css_id.group(1), []).append(loc)

        # ── data-test diff ─────────────────────────────────────
        removed_dt = set(all_old_dt) - set(all_new_dt)
        added_dt   = set(all_new_dt) - set(all_old_dt)

        matched_removed = set()
        matched_added   = set()

        for old_val in sorted(removed_dt):
            best = self._fuzzy_find(old_val, added_dt - matched_added)
            if best and best[1] >= self.RENAME_THRESHOLD:
                result.renamed.append(ElementChange(
                    change_type="renamed",
                    selector_type="data-test",
                    old_value=old_val,
                    new_value=best[0],
                    old_element=all_old_dt.get(old_val),
                    new_element=all_new_dt.get(best[0]),
                    affected_locators=robot_dt_refs.get(old_val, []),
                ))
                matched_removed.add(old_val)
                matched_added.add(best[0])

        for old_val in removed_dt - matched_removed:
            result.removed.append(ElementChange(
                change_type="removed",
                selector_type="data-test",
                old_value=old_val,
                old_element=all_old_dt.get(old_val),
                affected_locators=robot_dt_refs.get(old_val, []),
            ))

        for new_val in added_dt - matched_added:
            result.added.append(ElementChange(
                change_type="added",
                selector_type="data-test",
                new_value=new_val,
                new_element=all_new_dt.get(new_val),
            ))

        # ── id diff ────────────────────────────────────────────
        removed_id = set(old_id) - set(new_id)
        added_id   = set(new_id) - set(old_id)

        matched_rid = set()
        matched_aid = set()

        for old_val in sorted(removed_id):
            best = self._fuzzy_find(old_val, added_id - matched_aid)
            if best and best[1] >= self.RENAME_THRESHOLD:
                result.renamed.append(ElementChange(
                    change_type="renamed",
                    selector_type="id",
                    old_value=old_val,
                    new_value=best[0],
                    old_element=old_id.get(old_val),
                    new_element=new_id.get(best[0]),
                    affected_locators=robot_id_refs.get(old_val, []),
                ))
                matched_rid.add(old_val)
                matched_aid.add(best[0])

        for old_val in removed_id - matched_rid:
            result.removed.append(ElementChange(
                change_type="removed",
                selector_type="id",
                old_value=old_val,
                old_element=old_id.get(old_val),
                affected_locators=robot_id_refs.get(old_val, []),
            ))

        for new_val in added_id - matched_aid:
            result.added.append(ElementChange(
                change_type="added",
                selector_type="id",
                new_value=new_val,
                new_element=new_id.get(new_val),
            ))

        # ── Etkilenen Robot locator'ları ───────────────────────
        affected_ids = set()
        for change in result.removed + result.renamed:
            for loc in change.affected_locators:
                affected_ids.add(id(loc))
        result.affected_robot_locators = [
            loc for loc in robot_locators if id(loc) in affected_ids
        ]

        # ── Özet ───────────────────────────────────────────────
        result.summary = {
            "old_interactive": sum(1 for e in old_elements if e.is_interactive),
            "new_interactive": sum(1 for e in new_elements if e.is_interactive),
            "removed_count": len(result.removed),
            "renamed_count": len(result.renamed),
            "added_count": len(result.added),
            "affected_robot_count": len(result.affected_robot_locators),
        }

        return result

    def _fuzzy_find(self, target: str, candidates: set, threshold: float = 0.0) -> Optional[tuple]:
        best, best_score = None, threshold
        for cand in candidates:
            score = SequenceMatcher(None, target.lower(), cand.lower()).ratio()
            if score > best_score:
                best_score, best = score, cand
        return (best, best_score) if best else None
