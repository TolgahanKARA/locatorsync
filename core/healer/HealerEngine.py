"""
HealerEngine - Kırık ve riskli locator'lar için iyileştirme önerileri ve patch üretir.
"""
import re
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional

from models.RobotLocator import RobotLocator
from models.AnalysisResult import MatchResult, HealSuggestion, PatchFile, HealReport


class HealerEngine:
    def __init__(self, config):
        self.config = config

    def heal(
        self,
        match_results: list[MatchResult],
        generate_patch: bool = False,
    ) -> HealReport:
        """Tüm eşleşme sonuçları için heal önerileri üret."""
        report = HealReport()

        to_heal = [m for m in match_results if m.is_broken or m.is_risky]

        for match in to_heal:
            suggestion = self._suggest(match)
            if suggestion:
                report.suggestions.append(suggestion)
                if generate_patch and suggestion.patch_ready and suggestion.confidence in ("high", "medium"):
                    patch = self._create_patch(suggestion)
                    if patch:
                        report.patch_files.append(patch)
            else:
                report.skipped.append(match.locator)

        report.stats = {
            "total_healed": len(report.suggestions),
            "high_confidence": len(report.high_confidence),
            "medium_confidence": len(report.medium_confidence),
            "low_confidence": len(report.low_confidence),
            "patch_files": len(report.patch_files),
            "skipped_manual_review": len(report.skipped),
        }

        return report

    def _suggest(self, match: MatchResult) -> Optional[HealSuggestion]:
        """Tek bir eşleşme için öneri üret."""
        loc = match.locator
        el = match.matched_element

        if el and (el.data_test or el.data_testid):
            dt = el.data_test or el.data_testid
            new_val = f"css=[data-test='{dt}']"
            return HealSuggestion(
                locator=loc,
                original_value=loc.value,
                suggested_value=new_val,
                suggested_type="data-test",
                confidence="high",
                confidence_score=0.95,
                reason=f"Vue elementinde mevcut data-test='{dt}' attribute'u var.",
                patch_ready=True,
                vue_element_hint=None,
            )

        if el and el.element_id:
            new_val = f"id={el.element_id}"
            return HealSuggestion(
                locator=loc,
                original_value=loc.value,
                suggested_value=new_val,
                suggested_type="id",
                confidence="high",
                confidence_score=0.88,
                reason=f"Vue elementinde id='{el.element_id}' mevcut.",
                patch_ready=True,
            )

        if el and el.name:
            new_val = f"name={el.name}"
            return HealSuggestion(
                locator=loc,
                original_value=loc.value,
                suggested_value=new_val,
                suggested_type="name",
                confidence="medium",
                confidence_score=0.75,
                reason=f"Vue elementinde name='{el.name}' mevcut.",
                patch_ready=True,
            )

        if el and el.aria_label:
            new_val = f"css=[aria-label='{el.aria_label}']"
            return HealSuggestion(
                locator=loc,
                original_value=loc.value,
                suggested_value=new_val,
                suggested_type="aria-label",
                confidence="medium",
                confidence_score=0.7,
                reason=f"Vue elementinde aria-label='{el.aria_label}' mevcut.",
                patch_ready=True,
            )

        if match.is_broken:
            suggested_dt = self._derive_suggested_data_test(loc)
            return HealSuggestion(
                locator=loc,
                original_value=loc.value,
                suggested_value=f"css=[data-test='{suggested_dt}']",
                suggested_type="data-test",
                confidence="low",
                confidence_score=0.35,
                reason=f"Locator Vue'da bulunamadı. Vue bileşenine data-test='{suggested_dt}' eklenmeli.",
                patch_ready=False,
                vue_element_hint=f'<{self._guess_tag(loc)} data-test="{suggested_dt}">',
            )

        if match.is_risky:
            improved = self._improve_risky_locator(loc)
            if improved:
                new_val, reason, conf_score = improved
                return HealSuggestion(
                    locator=loc,
                    original_value=loc.value,
                    suggested_value=new_val,
                    suggested_type=self._detect_type(new_val),
                    confidence="medium" if conf_score > 0.6 else "low",
                    confidence_score=conf_score,
                    reason=reason,
                    patch_ready=conf_score > 0.6,
                )

        return None

    def _improve_risky_locator(self, loc: RobotLocator) -> Optional[tuple]:
        """Riskli locator için daha iyi versiyon üret."""
        v = loc.value

        if v.startswith("css=.") or v.startswith("."):
            css = v.replace("css=", "")
            if ":nth-child" in css or ":nth-of-type" in css:
                return (
                    f"# DİKKAT: {v} -> 'data-test' attribute ile değiştirilmeli",
                    "Indeks tabanlı CSS selector çok kırılgan. Elementa data-test ekleyin.",
                    0.3,
                )

        if v.startswith("xpath=//") or v.startswith("//"):
            xpath = v.replace("xpath=", "")
            tag_m = re.match(r"//(\w+)", xpath)
            tag = tag_m.group(1) if tag_m else "element"
            return (
                f"css={tag}[data-test='...']",
                f"XPath yerine CSS + data-test önerilir. {tag} elementine data-test ekleyin.",
                0.4,
            )

        return None

    def _create_patch(self, suggestion: HealSuggestion) -> Optional[PatchFile]:
        """Robot Framework dosyasında ilgili satırı patch'le."""
        try:
            file_path = Path(suggestion.locator.file)
            if not file_path.exists():
                return None

            content = file_path.read_text(encoding="utf-8", errors="ignore")
            lines = content.split("\n")
            target_line = suggestion.locator.line - 1

            if target_line >= len(lines):
                return None

            original = lines[target_line]
            patched = original.replace(
                suggestion.original_value,
                suggestion.suggested_value,
            )

            if patched == original:
                return None

            return PatchFile(
                robot_file=str(file_path),
                original_line=suggestion.locator.line,
                original_content=original,
                patched_content=patched,
                suggestion=suggestion,
            )
        except Exception:
            return None

    def apply_patches(self, patch_files: list[PatchFile], dry_run: bool = False) -> dict:
        """Patch'leri uygula (backup alarak)."""
        results = {"applied": [], "failed": [], "dry_run": dry_run}

        by_file: dict[str, list[PatchFile]] = {}
        for pf in patch_files:
            by_file.setdefault(pf.robot_file, []).append(pf)

        for robot_file, patches in by_file.items():
            try:
                fp = Path(robot_file)
                if not fp.exists():
                    results["failed"].append(robot_file)
                    continue

                if not dry_run and self.config.backup_before_patch:
                    backup_path = fp.with_suffix(
                        f".bak_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    )
                    shutil.copy2(fp, backup_path)

                content = fp.read_text(encoding="utf-8", errors="ignore")
                lines = content.split("\n")

                for patch in sorted(patches, key=lambda p: p.original_line, reverse=True):
                    idx = patch.original_line - 1
                    if 0 <= idx < len(lines):
                        lines[idx] = patch.patched_content

                if not dry_run:
                    fp.write_text("\n".join(lines), encoding="utf-8")

                results["applied"].append(robot_file)

            except Exception as e:
                results["failed"].append(f"{robot_file}: {e}")

        return results

    def _derive_suggested_data_test(self, loc: RobotLocator) -> str:
        """Locator değerinden uygun data-test ismi türet."""
        v = loc.value

        if loc.name:
            name = loc.name.lower()
            name = re.sub(r"[_\s]+", "-", name)
            name = re.sub(r"[^\w-]", "", name)
            return name.strip("-")[:40]

        classes = re.findall(r"\.([a-zA-Z][\w-]*)", v)
        if classes:
            return classes[0]

        id_m = re.search(r"#([a-zA-Z][\w-]*)", v)
        if id_m:
            return id_m.group(1)

        tag_m = re.search(r"//(\w+)", v)
        if tag_m:
            return f"{tag_m.group(1)}-element"

        return "element"

    def _guess_tag(self, loc: RobotLocator) -> str:
        """Locator'dan muhtemel HTML tag tahmin et."""
        v = loc.value.lower()
        if "btn" in v or "button" in v:
            return "button"
        if "input" in v or "field" in v or "text" in v:
            return "input"
        if "select" in v or "dropdown" in v:
            return "select"
        if "link" in v or "href" in v:
            return "a"
        return "div"

    def _detect_type(self, value: str) -> str:
        if "data-test" in value:
            return "data-test"
        if value.startswith("id="):
            return "id"
        if value.startswith("name="):
            return "name"
        if value.startswith("css="):
            return "css"
        if value.startswith("xpath=") or value.startswith("//"):
            return "xpath"
        return "unknown"
