"""
IdFromDataTestPatcher - Vue data-test attributelerini id'ye dönüştürür.

Akış:
  1. Vue dosyalarını tara -> data-test olan ama id olmayan elementleri bul
  2. data-test degeri + element tag tipine gore benzersiz id uret
     - Tekil element   : {tag_prefix}-{dt_slug}           (btn-test-form-inner-button)
     - Coklu element   : {tag_prefix}-{dt_slug}-{index}   (btn-test-form-inner-button-1)
  3. Robot dosyalarini tara -> tekil elementler icin locator guncellemesi oner
     Coklu elementler manuel inceleme gerektirir (hangi index hangi Robot locatora karsalik
     geliyor bilinemiyor).

  preview()   -> IdPatchReport (dosya degismez)
  apply(...)  -> Vue'a id yazar + Robot locatorlarini gunceller
"""
import re
from collections import defaultdict, Counter
from pathlib import Path
from typing import Optional

from configs.AppConfig import AppConfig
from core.scanner.VueScanner import VueScanner
from core.analyzer.LocatorExtractor import LocatorExtractor


# ── Sabitler ─────────────────────────────────────────────────────────────────

TAG_PREFIX = {
    'button': 'btn', 'input': 'inp', 'span': 'spn',
    'div': 'div', 'label': 'lbl', 'a': 'link',
    'select': 'sel', 'textarea': 'txt', 'form': 'frm',
    'img': 'img', 'ul': 'ul', 'li': 'li', 'p': 'p',
    'section': 'sec', 'article': 'art', 'nav': 'nav',
    'header': 'hdr', 'footer': 'ftr', 'main': 'main',
    'table': 'tbl', 'tr': 'tr', 'td': 'td', 'th': 'th',
}


# ── Veri modelleri ───────────────────────────────────────────────────────────

class RobotUpdate:
    """Bir Robot dosyasinda guncellenecek locator."""
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
    """Tek bir Vue elementi icin id ekleme onerisi."""
    def __init__(
        self,
        vue_file: str,
        vue_line: int,
        vue_tag: str,
        data_test_value: str,       # data-test attribute degeri/expression'i
        attr_source: str,           # "data-test" | ":data-test" | "data-testid" | ":data-testid"
        generated_id: str,          # Uretilen benzersiz id degeri
        original_snippet: str = "",
        robot_updates: Optional[list] = None,
        is_dynamic: bool = False,   # True -> :id yazilmali (dynamic binding)
        is_multi_instance: bool = False,  # True -> ayni data-test baska elementlerde de var
    ):
        self.vue_file = vue_file
        self.vue_line = vue_line
        self.vue_tag = vue_tag
        self.data_test_value = data_test_value
        self.attr_source = attr_source
        self.generated_id = generated_id
        self.original_snippet = original_snippet
        self.robot_updates: list[RobotUpdate] = robot_updates or []
        self.is_dynamic = is_dynamic
        self.is_multi_instance = is_multi_instance
        # Yazilacak attribute: dynamic -> :id, static -> id
        self.id_attr = ":id" if is_dynamic else "id"

    def to_dict(self) -> dict:
        return {
            "vue_file": self.vue_file,
            "vue_file_name": Path(self.vue_file).name,
            "vue_line": self.vue_line,
            "vue_tag": self.vue_tag,
            "data_test_value": self.data_test_value,
            "attr_source": self.attr_source,
            "generated_id": self.generated_id,
            "id_to_add": self.generated_id,       # geriye donuk uyumluluk
            "id_attr": self.id_attr,
            "is_dynamic": self.is_dynamic,
            "is_multi_instance": self.is_multi_instance,
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


# ── Ana sinif ────────────────────────────────────────────────────────────────

class IdFromDataTestPatcher:
    # Robot dosyasinda data-test tabanli CSS locatorlari eslestiren pattern'lar
    _DT_PATTERNS = [
        re.compile(r"""css=\[data-test=['"]([^'"]+)['"]\]"""),
        re.compile(r"""css=\[data-testid=['"]([^'"]+)['"]\]"""),
        re.compile(r"""xpath=.*?@data-test=['"]([^'"]+)['"]"""),
        re.compile(r"""xpath=.*?@data-testid=['"]([^'"]+)['"]"""),
    ]

    def __init__(self, config: AppConfig):
        self.config = config

    # ── ID uretimi ──────────────────────────────────────────────

    @staticmethod
    def _dt_slug(dt_value: str) -> str:
        """data-test degerinden CSS-guvenli slug uretir: test__form__inner -> test-form-inner"""
        slug = re.sub(r'__+', '-', dt_value)           # __ -> -
        slug = re.sub(r'[^a-zA-Z0-9-]', '-', slug)    # diger ozel karakterler -> -
        slug = re.sub(r'-+', '-', slug)                # coklu tire -> tek tire
        return slug.strip('-').lower()

    def _generate_id(self, tag: str, dt_value: str, index: Optional[int] = None) -> str:
        """Element tag tipi + data-test slugundan benzersiz id uretir."""
        prefix = TAG_PREFIX.get(tag.lower(), tag.lower()[:4])
        slug = self._dt_slug(dt_value)
        base = f"{prefix}-{slug}"
        return f"{base}-{index}" if index is not None else base

    # ── Onizleme ────────────────────────────────────────────────

    def preview(self) -> IdPatchReport:
        report = IdPatchReport()

        # Vue dosyalarini tara
        scanner = VueScanner(self.config)
        vue_elements = scanner.scan()

        # data-test olan ama id olmayan elementleri topla
        candidates = []
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

            candidates.append((el, dt_value, attr_source))

        # data-test degerine gore grupla -> coklu kullanim tespiti
        dt_counts = Counter(dt_value for _, dt_value, _ in candidates)
        dt_indices: dict[str, int] = {}   # data-test value -> sonraki index
        by_dt_value: dict[str, IdSuggestion] = {}  # sadece tekil elementler

        for el, dt_value, attr_source in candidates:
            is_multi = dt_counts[dt_value] > 1

            if is_multi:
                idx = dt_indices.get(dt_value, 1)
                dt_indices[dt_value] = idx + 1
                generated_id = self._generate_id(el.tag, dt_value, idx)
            else:
                generated_id = self._generate_id(el.tag, dt_value)

            snippet = self._get_snippet(el.file, el.line)
            sug = IdSuggestion(
                vue_file=el.file,
                vue_line=el.line,
                vue_tag=el.tag,
                data_test_value=dt_value,
                attr_source=attr_source,
                generated_id=generated_id,
                original_snippet=snippet,
                is_dynamic=el.is_dynamic_binding,
                is_multi_instance=is_multi,
            )
            report.suggestions.append(sug)

            # Robot eslestirmesi yalnizca tekil elementler icin (coklu -> hangi index belirsiz)
            if not is_multi:
                by_dt_value[dt_value] = sug

        # Robot dosyalarinda eslesen locatorlari bul
        robot_errors = self.config.validate_robot()
        if not robot_errors and by_dt_value:
            self._find_robot_updates(by_dt_value, report)

        unique_count = sum(1 for s in report.suggestions if not s.is_multi_instance)
        multi_count = len(report.suggestions) - unique_count
        report.stats = {
            "total_suggestions": len(report.suggestions),
            "unique_elements": unique_count,
            "multi_instance_elements": multi_count,
            "vue_files": len({s.vue_file for s in report.suggestions}),
            "robot_updates": sum(len(s.robot_updates) for s in report.suggestions),
            "robot_available": not bool(robot_errors),
        }
        return report

    def _find_robot_updates(self, by_dt_value: dict, report: IdPatchReport):
        """Robot dosyalarini tara, data-test tabanli locatorlari bul ve eslesir."""
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

                    if dt_value in by_dt_value:
                        sug = by_dt_value[dt_value]
                        new_locator = f"css=#{sug.generated_id}"
                        # Ayni robot satiri iki kez eklenmesin
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
                    break  # bir satirda bir esleme yeterli

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

        # Vue dosyalarina id yaz (satir numarasina gore ters sirada -> usttten ekleme kaymasi yok)
        by_file: dict[str, list[IdSuggestion]] = defaultdict(list)
        for sug in suggestions:
            by_file[sug.vue_file].append(sug)

        for file_path, file_sugs in by_file.items():
            result = self._patch_vue_file(file_path, file_sugs)
            applied_vue.extend(result["applied"])
            failed.extend(result["failed"])

        # Robot dosyalarini guncelle
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

    # ── Vue dosyasina id yaz ─────────────────────────────────────

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
                content, sug.vue_line, sug.vue_tag, sug.id_attr, sug.generated_id
            )
            if ok:
                content = new_content
                applied.append({
                    "file": Path(file_path).name,
                    "line": sug.vue_line,
                    "tag": sug.vue_tag,
                    "added": f'id="{sug.generated_id}"',
                })
            else:
                failed.append({
                    "file": Path(file_path).name,
                    "line": sug.vue_line,
                    "error": "Tag konumlanamadi veya id zaten mevcut",
                })

        if applied:
            try:
                Path(file_path).write_text(content, encoding="utf-8")
            except Exception as e:
                failed.extend(applied)
                applied = []

        return {"applied": applied, "failed": failed}

    # ── Robot dosyasina locator yaz ──────────────────────────────

    def _patch_robot_files(self, updates: list[RobotUpdate]) -> dict:
        """Robot dosyalarindaki data-test locatorlarini css=#id ile degistir."""
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

    # ── Attribute ekleme (VuePatcher ile ayni mantik) ────────────

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
