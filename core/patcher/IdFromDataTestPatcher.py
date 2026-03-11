"""
IdFromDataTestPatcher - Vue data-test attributelerini id'ye dönüştürür.

Akış:
  1. Vue dosyalarını tara → data-test olan ama id olmayan elementleri bul
  2. Her element için id="<data-test-value>" öner
  3. Robot dosyalarını tara → css=[data-test='X'] gibi locatorları bul
  4. Bu locatorların id=X ile değiştirilmesi gerektiğini raporla

  preview()   → IdPatchReport (dosya değişmez)
  apply(...)  → Vue'a id yazar + Robot locatorlarını günceller
"""
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from configs.AppConfig import AppConfig
from core.scanner.VueScanner import VueScanner
from core.analyzer.LocatorExtractor import LocatorExtractor


# ── Veri modelleri ───────────────────────────────────────────────────────────

class RobotUpdate:
    """Bir Robot dosyasında güncellenecek locator."""
    def __init__(self, robot_file: str, robot_line: int, old_value: str, new_value: str):
        self.robot_file = robot_file
        self.robot_line = robot_line
        self.old_value = old_value
        self.new_value = new_value

    def to_dict(self) -> dict:
        return {
            "robot_file": self.robot_file,
            "robot_file_name": Path(self.robot_file).name,
            "robot_line": self.robot_line,
            "old_value": self.old_value,
            "new_value": self.new_value,
        }


class IdSuggestion:
    """Tek bir Vue elementi için id ekleme önerisi."""
    def __init__(
        self,
        vue_file: str,
        vue_line: int,
        vue_tag: str,
        data_test_value: str,       # data-test attribute değeri/expression'ı
        attr_source: str,           # "data-test" | ":data-test" | "data-testid" | ":data-testid"
        original_snippet: str = "",
        robot_updates: Optional[list] = None,
        is_dynamic: bool = False,   # True → :id yazılmalı (dynamic binding)
    ):
        self.vue_file = vue_file
        self.vue_line = vue_line
        self.vue_tag = vue_tag
        self.data_test_value = data_test_value
        self.attr_source = attr_source
        self.original_snippet = original_snippet
        self.robot_updates: list[RobotUpdate] = robot_updates or []
        self.is_dynamic = is_dynamic
        # Yazılacak attribute: dynamic → :id, static → id
        self.id_attr = ":id" if is_dynamic else "id"

    def to_dict(self) -> dict:
        return {
            "vue_file": self.vue_file,
            "vue_file_name": Path(self.vue_file).name,
            "vue_line": self.vue_line,
            "vue_tag": self.vue_tag,
            "data_test_value": self.data_test_value,
            "attr_source": self.attr_source,
            "id_to_add": self.data_test_value,
            "id_attr": self.id_attr,
            "is_dynamic": self.is_dynamic,
            "original_snippet": self.original_snippet,
            "robot_updates": [u.to_dict() for u in self.robot_updates],
        }


class IdPatchReport:
    def __init__(self):
        self.suggestions: list[IdSuggestion] = []
        self.stats: dict = {}

    def to_dict(self) -> dict:
        return {
            "suggestions": [s.to_dict() for s in self.suggestions],
            "stats": self.stats,
        }


# ── Ana sınıf ────────────────────────────────────────────────────────────────

class IdFromDataTestPatcher:
    # Robot dosyasında data-test tabanlı CSS locatorları eşleştiren pattern'lar
    _DT_PATTERNS = [
        re.compile(r"""css=\[data-test=['"]([^'"]+)['"]\]"""),
        re.compile(r"""css=\[data-testid=['"]([^'"]+)['"]\]"""),
        re.compile(r"""xpath=.*?@data-test=['"]([^'"]+)['"]"""),
        re.compile(r"""xpath=.*?@data-testid=['"]([^'"]+)['"]"""),
    ]

    def __init__(self, config: AppConfig):
        self.config = config

    # ── Önizleme ────────────────────────────────────────────────

    def preview(self) -> IdPatchReport:
        report = IdPatchReport()

        # Vue dosyalarını tara
        scanner = VueScanner(self.config)
        vue_elements = scanner.scan()

        # data-test olan ama id olmayan elementleri topla
        # data_test_value → IdSuggestion indexi (robot update eşleştirmek için)
        by_dt_value: dict[str, IdSuggestion] = {}

        for el in vue_elements:
            if el.element_id:
                continue  # zaten id var

            dt_value = None
            attr_source = None
            if el.data_test:
                dt_value = el.data_test
                attr_source = ":data-test" if el.is_dynamic_binding else "data-test"
            elif el.data_testid:
                dt_value = el.data_testid
                attr_source = ":data-testid" if el.is_dynamic_binding else "data-testid"

            if not dt_value:
                continue

            snippet = self._get_snippet(el.file, el.line)
            sug = IdSuggestion(
                vue_file=el.file,
                vue_line=el.line,
                vue_tag=el.tag,
                data_test_value=dt_value,
                attr_source=attr_source,
                original_snippet=snippet,
                is_dynamic=el.is_dynamic_binding,
            )
            report.suggestions.append(sug)
            # Aynı data-test değeri birden fazla elementte olabilir → liste ile tut
            by_dt_value.setdefault(dt_value, sug)

        # Robot dosyalarında eşleşen locatorları bul
        robot_errors = self.config.validate_robot()
        if not robot_errors and by_dt_value:
            self._find_robot_updates(by_dt_value, report)

        report.stats = {
            "total_suggestions": len(report.suggestions),
            "vue_files": len({s.vue_file for s in report.suggestions}),
            "robot_updates": sum(len(s.robot_updates) for s in report.suggestions),
            "robot_available": not bool(robot_errors),
        }
        return report

    def _find_robot_updates(self, by_dt_value: dict, report: IdPatchReport):
        """Robot dosyalarını tara, data-test tabanlı locatorları bul ve eşleştir."""
        extractor = LocatorExtractor(self.config)

        robot_path = self.config.robot_path
        if not robot_path or not robot_path.exists():
            return

        ignore = set(self.config.ignore_dirs)
        robot_files = [
            p for ext in self.config.robot_extensions
            for p in robot_path.rglob(f"*{ext}")
            if not any(part in ignore for part in p.parts)
        ]

        for robot_file in robot_files:
            try:
                lines = robot_file.read_text(encoding="utf-8", errors="ignore").split("\n")
            except Exception:
                continue

            for line_num, line in enumerate(lines, 1):
                for pattern in self._DT_PATTERNS:
                    m = pattern.search(line)
                    if not m:
                        continue
                    dt_value = m.group(1)
                    old_locator = m.group(0)
                    new_locator = f"id={dt_value}"

                    if dt_value in by_dt_value:
                        sug = by_dt_value[dt_value]
                        # Aynı robot satırı iki kez eklenmesin
                        already = any(
                            u.robot_file == str(robot_file) and u.robot_line == line_num
                            for u in sug.robot_updates
                        )
                        if not already:
                            sug.robot_updates.append(RobotUpdate(
                                robot_file=str(robot_file),
                                robot_line=line_num,
                                old_value=old_locator,
                                new_value=new_locator,
                            ))
                    break  # bir satırda bir eşleşme yeterli

    # ── Uygulama ────────────────────────────────────────────────

    def apply(
        self,
        suggestions: list[IdSuggestion],
        dry_run: bool = True,
        apply_robot: bool = True,
    ) -> dict:
        if dry_run:
            robot_total = sum(len(s.robot_updates) for s in suggestions)
            return {
                "dry_run": True,
                "would_patch_vue": len(suggestions),
                "would_patch_robot": robot_total,
                "applied_vue": [],
                "applied_robot": [],
                "failed": [],
            }

        applied_vue, applied_robot, failed = [], [], []

        # Vue dosyalarına id yaz (satır numarasına göre ters sırada → üstten ekleme kayması yok)
        by_file: dict[str, list[IdSuggestion]] = defaultdict(list)
        for sug in suggestions:
            by_file[sug.vue_file].append(sug)

        for file_path, file_sugs in by_file.items():
            result = self._patch_vue_file(file_path, file_sugs)
            applied_vue.extend(result["applied"])
            failed.extend(result["failed"])

        # Robot dosyalarını güncelle
        if apply_robot:
            robot_updates_all: list[RobotUpdate] = []
            for sug in suggestions:
                robot_updates_all.extend(sug.robot_updates)

            result = self._patch_robot_files(robot_updates_all)
            applied_robot.extend(result["applied"])
            failed.extend(result["failed"])

        return {
            "dry_run": False,
            "applied_vue": applied_vue,
            "applied_robot": applied_robot,
            "failed": failed,
        }

    # ── Vue dosyasına id yaz ─────────────────────────────────────

    def _patch_vue_file(self, file_path: str, sugs: list[IdSuggestion]) -> dict:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return {
                "applied": [],
                "failed": [{"file": Path(file_path).name, "error": str(e)}],
            }

        sorted_sugs = sorted(sugs, key=lambda s: s.vue_line, reverse=True)
        applied, failed = [], []

        for sug in sorted_sugs:
            snippet = self._get_snippet_from_content(content, sug.vue_line)
            if 'id=' in snippet or ':id=' in snippet:
                continue  # zaten id var

            new_content, ok = self._insert_attr(
                content, sug.vue_line, sug.vue_tag, sug.id_attr, sug.data_test_value
            )
            if ok:
                content = new_content
                applied.append({
                    "file": Path(file_path).name,
                    "line": sug.vue_line,
                    "tag": sug.vue_tag,
                    "added": f'id="{sug.data_test_value}"',
                })
            else:
                failed.append({
                    "file": Path(file_path).name,
                    "line": sug.vue_line,
                    "error": "Tag konumlanamadı veya id zaten mevcut",
                })

        if applied:
            try:
                Path(file_path).write_text(content, encoding="utf-8")
            except Exception as e:
                failed.extend(applied)
                applied = []

        return {"applied": applied, "failed": failed}

    # ── Robot dosyasına locator yaz ──────────────────────────────

    def _patch_robot_files(self, updates: list[RobotUpdate]) -> dict:
        """Robot dosyalarındaki css=[data-test='X'] → id=X ile değiştir."""
        by_file: dict[str, list[RobotUpdate]] = defaultdict(list)
        for u in updates:
            by_file[u.robot_file].append(u)

        applied, failed = [], []

        for file_path, file_updates in by_file.items():
            try:
                lines = Path(file_path).read_text(encoding="utf-8", errors="ignore").split("\n")
            except Exception as e:
                failed.append({"file": Path(file_path).name, "error": str(e)})
                continue

            changed = False
            for update in file_updates:
                idx = update.robot_line - 1
                if idx < 0 or idx >= len(lines):
                    continue
                old_line = lines[idx]
                new_line = old_line.replace(update.old_value, update.new_value, 1)
                if new_line != old_line:
                    lines[idx] = new_line
                    changed = True
                    applied.append({
                        "file": Path(file_path).name,
                        "line": update.robot_line,
                        "old": update.old_value,
                        "new": update.new_value,
                    })

            if changed:
                try:
                    Path(file_path).write_text("\n".join(lines), encoding="utf-8")
                except Exception as e:
                    failed.append({"file": Path(file_path).name, "error": str(e)})

        return {"applied": applied, "failed": failed}

    # ── Attribute ekleme (VuePatcher ile aynı mantık) ────────────

    def _insert_attr(
        self, content: str, line: int, tag: str, attr_name: str, attr_value: str
    ) -> tuple[str, bool]:
        lines = content.split("\n")
        idx = line - 1
        if idx < 0 or idx >= len(lines):
            return content, False

        line_text = lines[idx]
        tag_re = re.compile(rf"<{re.escape(tag)}\b", re.IGNORECASE)
        m = tag_re.search(line_text)
        if not m:
            return content, False

        char_offset = sum(len(l) + 1 for l in lines[:idx]) + m.start()
        end_pos = self._find_tag_end(content, char_offset)
        if end_pos is None:
            return content, False

        tag_content = content[char_offset:end_pos]
        # Hem statik hem dynamic kontrol et (id= veya :id=)
        bare = attr_name.lstrip(":")
        if f'{attr_name}=' in tag_content or f'{bare}=' in tag_content:
            return content, False

        insert_at = end_pos - 1 if content[end_pos - 1] == "/" else end_pos
        new_content = (
            content[:insert_at]
            + f' {attr_name}="{attr_value}"'
            + content[insert_at:]
        )
        return new_content, True

    @staticmethod
    def _find_tag_end(content: str, start: int) -> Optional[int]:
        i, in_single, in_double = start, False, False
        while i < len(content):
            c = content[i]
            if c == '"' and not in_single:
                in_double = not in_double
            elif c == "'" and not in_double:
                in_single = not in_single
            elif not in_single and not in_double and c == ">":
                return i
            i += 1
        return None

    def _get_snippet(self, file_path: str, line: int) -> str:
        try:
            lines = Path(file_path).read_text(encoding="utf-8", errors="ignore").split("\n")
            return lines[line - 1].strip() if 0 < line <= len(lines) else ""
        except Exception:
            return ""

    def _get_snippet_from_content(self, content: str, line: int) -> str:
        lines = content.split("\n")
        return lines[line - 1].strip() if 0 < line <= len(lines) else ""
