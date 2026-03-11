"""
VuePatcher - İki yönlü Vue ↔ Robot reconciliation.

Robot-driven  : Robot bir elementin nasıl bulunduğuna bakar (risky/broken locator),
                Vue elementine kararlı `id` attribute ekler,
                Robot locator'ının `id=...` olarak güncellenmesi gerektiğini raporlar.

Audit-driven  : Robot'ta hiç referansı olmayan interaktif Vue elementlerine
                `data-test` attribute ekler.

Uygulama akışı:
  preview()          → VuePatchReport (dosya değişmez)
  apply(patches)     → Vue dosyalarına yazar (Robot güncellemesi: ayrıca Heal tab)
"""
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

from configs.AppConfig import AppConfig
from core.scanner.VueScanner import VueScanner
from core.analyzer.LocatorExtractor import LocatorExtractor
from core.analyzer.ChangeMatcher import ChangeMatcher
from models.VueElement import VueElement
from models.RobotLocator import RobotLocator
from models.AnalysisResult import MatchResult


# ── Veri modelleri ──────────────────────────────────────────────────────────

class PatchSuggestion:
    """
    Tek bir Vue elementi için patch önerisi.
    patch_type: "robot_driven" | "audit_driven"
    """
    def __init__(
        self,
        vue_file: str,
        vue_line: int,
        vue_tag: str,
        attr_to_add: str,           # "id" veya "data-test"
        attr_value: str,
        patch_type: str,
        original_snippet: str = "",
        severity: str = "info",
        # Robot bağlamı (robot_driven için)
        robot_file: str = "",
        robot_line: int = 0,
        robot_locator_value: str = "",
        robot_locator_type: str = "",
        robot_update_to: str = "",  # Robot'un güncellenmesi gereken locator
    ):
        self.vue_file = vue_file
        self.vue_line = vue_line
        self.vue_tag = vue_tag
        self.attr_to_add = attr_to_add
        self.attr_value = attr_value
        self.patch_type = patch_type
        self.original_snippet = original_snippet
        self.severity = severity
        self.robot_file = robot_file
        self.robot_line = robot_line
        self.robot_locator_value = robot_locator_value
        self.robot_locator_type = robot_locator_type
        self.robot_update_to = robot_update_to  # e.g. "id=login-btn"

    def to_dict(self) -> dict:
        return {
            "vue_file": self.vue_file,
            "vue_file_name": Path(self.vue_file).name,
            "vue_line": self.vue_line,
            "vue_tag": self.vue_tag,
            "attr_to_add": self.attr_to_add,
            "attr_value": self.attr_value,
            "patch_type": self.patch_type,
            "original_snippet": self.original_snippet,
            "severity": self.severity,
            "robot_file": Path(self.robot_file).name if self.robot_file else "",
            "robot_line": self.robot_line,
            "robot_locator_value": self.robot_locator_value,
            "robot_locator_type": self.robot_locator_type,
            "robot_update_to": self.robot_update_to,
        }


class VuePatchReport:
    def __init__(self):
        self.robot_driven: list[PatchSuggestion] = []   # Robot → Vue
        self.audit_driven: list[PatchSuggestion] = []   # Audit → Vue
        self.stats: dict = {}

    @property
    def all_patches(self) -> list[PatchSuggestion]:
        return self.robot_driven + self.audit_driven

    def to_dict(self) -> dict:
        return {
            "robot_driven": [p.to_dict() for p in self.robot_driven],
            "audit_driven": [p.to_dict() for p in self.audit_driven],
            "stats": self.stats,
        }


# ── Ana sınıf ────────────────────────────────────────────────────────────────

class VuePatcher:
    def __init__(self, config):
        self.config = config

    # ── Önizleme ────────────────────────────────────────────────

    def preview(self) -> VuePatchReport:
        """
        Eksik id / data-test attribute'larını analiz et.
        - Robot'tan türetilen: risky/broken locator'ların hedeflediği Vue elementlerine id ekle
        - Audit kaynaklı: Robot'ta referansı olmayan elementlere data-test ekle
        """
        # Vue tara
        scanner = VueScanner(self.config)
        vue_elements = scanner.scan()

        report = VuePatchReport()
        robot_driven_element_ids: set[int] = set()  # id() → aynı elementi iki kez önerme

        # Robot analizi — robot_path tanımlıysa yap
        robot_errors = self.config.validate_robot()
        if not robot_errors:
            extractor = LocatorExtractor(self.config)
            extraction = extractor.extract()

            if extraction.locators:
                matcher = ChangeMatcher(self.config)
                cross = matcher.analyze(vue_elements, extraction.locators, ignore_list=[])

                # Risky: Robot bulabiliyor ama kırılgan yol kullanıyor
                for match in cross.risky:
                    el = match.matched_element
                    if el is None:
                        continue
                    if id(el) in robot_driven_element_ids:
                        continue
                    sug = self._build_robot_suggestion(match, el)
                    if sug:
                        report.robot_driven.append(sug)
                        robot_driven_element_ids.add(id(el))

                # Broken: Robot hiç bulamıyor — locator değerinden Vue elementi bulmaya çalış
                for match in cross.broken:
                    result = self._try_resolve_broken(match, vue_elements, robot_driven_element_ids)
                    if result:
                        report.robot_driven.append(result)
                        robot_driven_element_ids.add(id(result))   # result is suggestion, store vue_line key
                        # robot_driven_element_ids'e vue element ekleyemiyoruz (element yok),
                        # PatchSuggestion'dan unique key olarak (file,line) kullan
                    # broken için element bulunamadıysa atla

        # Audit-driven: tüm interaktif elementler, Robot'ta karşılığı olmayanlar
        for el in vue_elements:
            if not el.is_interactive:
                continue
            if id(el) in robot_driven_element_ids:
                continue
            if el.data_test or el.data_testid:
                continue  # zaten data-test var
            sug = self._build_audit_suggestion(el)
            if sug:
                report.audit_driven.append(sug)

        report.stats = {
            "robot_driven": len(report.robot_driven),
            "audit_driven": len(report.audit_driven),
            "total": len(report.robot_driven) + len(report.audit_driven),
            "files": len({p.vue_file for p in report.all_patches}),
            "robot_available": not bool(robot_errors),
        }
        return report

    # ── Uygulama ────────────────────────────────────────────────

    def apply(self, patches: list[PatchSuggestion], dry_run: bool = True) -> dict:
        if dry_run:
            return {
                "dry_run": True,
                "would_patch": len(patches),
                "applied": [],
                "failed": [],
            }

        by_file: dict[str, list[PatchSuggestion]] = defaultdict(list)
        for p in patches:
            by_file[p.vue_file].append(p)

        applied, failed = [], []
        for file_path, file_patches in by_file.items():
            result = self._patch_file(file_path, file_patches)
            applied.extend(result["applied"])
            failed.extend(result["failed"])

        return {"dry_run": False, "applied": applied, "failed": failed}

    # ── Robot-driven öneri oluştur ───────────────────────────────

    def _build_robot_suggestion(
        self, match: MatchResult, el: VueElement
    ) -> Optional[PatchSuggestion]:
        """
        Risky bir locator için Vue elementine id ekle,
        Robot locator'ının güncellenecek halini hesapla.
        Element zaten stabil attribute'a sahipse sadece Robot güncelleme öner.
        """
        loc = match.locator

        # Element zaten id'ye sahipse → id ekleme gerekmez,
        # ama Robot'a "id=existing_id" kullan diyebiliriz.
        if el.element_id:
            # Vue değişmez, sadece Robot güncellemesi öneri
            return PatchSuggestion(
                vue_file=el.file,
                vue_line=el.line,
                vue_tag=el.tag,
                attr_to_add="id",
                attr_value=el.element_id,
                patch_type="robot_driven",
                original_snippet=self._get_snippet(el.file, el.line),
                severity="info",
                robot_file=loc.file,
                robot_line=loc.line,
                robot_locator_value=loc.value,
                robot_locator_type=loc.locator_type,
                robot_update_to=f"id={el.element_id}",
            ) if not el.element_id == "" else None

        # Element data-test'e sahipse → data-test ile yönlendir
        if el.data_test:
            return PatchSuggestion(
                vue_file=el.file,
                vue_line=el.line,
                vue_tag=el.tag,
                attr_to_add="data-test",
                attr_value=el.data_test,
                patch_type="robot_driven",
                original_snippet=self._get_snippet(el.file, el.line),
                severity="info",
                robot_file=loc.file,
                robot_line=loc.line,
                robot_locator_value=loc.value,
                robot_locator_type=loc.locator_type,
                robot_update_to=f"css=[data-test='{el.data_test}']",
            )

        # Element data-testid'ye sahipse → data-testid ile yönlendir
        if el.data_testid:
            return PatchSuggestion(
                vue_file=el.file,
                vue_line=el.line,
                vue_tag=el.tag,
                attr_to_add="data-testid",
                attr_value=el.data_testid,
                patch_type="robot_driven",
                original_snippet=self._get_snippet(el.file, el.line),
                severity="info",
                robot_file=loc.file,
                robot_line=loc.line,
                robot_locator_value=loc.value,
                robot_locator_type=loc.locator_type,
                robot_update_to=f"css=[data-testid='{el.data_testid}']",
            )

        # Element stabil attribute yok → id ekle
        new_id = self._derive_id_from_locator(loc, el)
        if not new_id:
            return None

        return PatchSuggestion(
            vue_file=el.file,
            vue_line=el.line,
            vue_tag=el.tag,
            attr_to_add="id",
            attr_value=new_id,
            patch_type="robot_driven",
            original_snippet=self._get_snippet(el.file, el.line),
            severity="warning",
            robot_file=loc.file,
            robot_line=loc.line,
            robot_locator_value=loc.value,
            robot_locator_type=loc.locator_type,
            robot_update_to=f"id={new_id}",
        )

    def _try_resolve_broken(
        self,
        match: MatchResult,
        vue_elements: list[VueElement],
        already_covered: set[int],
    ) -> Optional[PatchSuggestion]:
        """
        Broken locator için Vue elementini locator değerinden tahmin et.
        Sınırlı — sadece sınıf ve metin eşleşmesi yapılabilir.
        """
        loc = match.locator
        value = loc.value.strip()

        # CSS class → Vue'da o class'a sahip element ara
        class_m = re.findall(r"\.([a-zA-Z][\w-]*)", value)
        if class_m:
            el = self._find_el_by_class(class_m[0], vue_elements, already_covered)
            if el:
                new_id = self._slugify(class_m[0])
                sug = PatchSuggestion(
                    vue_file=el.file,
                    vue_line=el.line,
                    vue_tag=el.tag,
                    attr_to_add="id",
                    attr_value=new_id,
                    patch_type="robot_driven",
                    original_snippet=self._get_snippet(el.file, el.line),
                    severity="critical",
                    robot_file=loc.file,
                    robot_line=loc.line,
                    robot_locator_value=loc.value,
                    robot_locator_type=loc.locator_type,
                    robot_update_to=f"id={new_id}",
                )
                already_covered.add(id(el))
                return sug

        # XPath class → benzer
        xp_class = re.search(r"@class=['\"]([^'\"]+)['\"]", value)
        if xp_class:
            cls = xp_class.group(1).split()[0]
            el = self._find_el_by_class(cls, vue_elements, already_covered)
            if el:
                new_id = self._slugify(cls)
                sug = PatchSuggestion(
                    vue_file=el.file,
                    vue_line=el.line,
                    vue_tag=el.tag,
                    attr_to_add="id",
                    attr_value=new_id,
                    patch_type="robot_driven",
                    original_snippet=self._get_snippet(el.file, el.line),
                    severity="critical",
                    robot_file=loc.file,
                    robot_line=loc.line,
                    robot_locator_value=loc.value,
                    robot_locator_type=loc.locator_type,
                    robot_update_to=f"id={new_id}",
                )
                already_covered.add(id(el))
                return sug

        return None

    # ── Audit-driven öneri oluştur ───────────────────────────────

    def _build_audit_suggestion(self, el: VueElement) -> Optional[PatchSuggestion]:
        """Robot'ta referans olmayan element için data-test öner."""
        value = self._best_audit_value(el)
        if not value:
            return None
        return PatchSuggestion(
            vue_file=el.file,
            vue_line=el.line,
            vue_tag=el.tag,
            attr_to_add="data-test",
            attr_value=value,
            patch_type="audit_driven",
            original_snippet=self._get_snippet(el.file, el.line),
            severity="warning" if el.classes else "info",
        )

    # ── Dosya düzenleme ─────────────────────────────────────────

    def _patch_file(self, file_path: str, patches: list[PatchSuggestion]) -> dict:
        try:
            content = Path(file_path).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            return {
                "applied": [],
                "failed": [
                    {"file": Path(file_path).name, "line": p.vue_line, "error": str(e)}
                    for p in patches
                ],
            }

        sorted_patches = sorted(patches, key=lambda p: p.vue_line, reverse=True)
        applied, failed = [], []

        for patch in sorted_patches:
            # Zaten bu attribute var mı kontrol et (önizlemeden uygulamaya kadar değişmiş olabilir)
            snippet = self._get_snippet_from_content(content, patch.vue_line)
            if f'{patch.attr_to_add}=' in snippet:
                continue  # zaten var, atla

            new_content, ok = self._insert_attr(
                content, patch.vue_line, patch.vue_tag,
                patch.attr_to_add, patch.attr_value
            )
            if ok:
                content = new_content
                applied.append({
                    "file": Path(file_path).name,
                    "line": patch.vue_line,
                    "tag": patch.vue_tag,
                    "added": f'{patch.attr_to_add}="{patch.attr_value}"',
                    "patch_type": patch.patch_type,
                    "robot_update_to": patch.robot_update_to,
                })
            else:
                failed.append({
                    "file": Path(file_path).name,
                    "line": patch.vue_line,
                    "error": "Tag konumlanamadı veya attribute zaten mevcut",
                })

        if applied:
            try:
                Path(file_path).write_text(content, encoding="utf-8")
            except Exception as e:
                failed.extend(applied)
                applied = []

        return {"applied": applied, "failed": failed}

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
        if attr_name in tag_content:
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

    # ── ID türetme ───────────────────────────────────────────────

    def _derive_id_from_locator(self, loc: RobotLocator, el: VueElement) -> Optional[str]:
        """
        Robot locator değerinden Vue elementi için uygun id türet.
        """
        value = loc.value.strip()
        ltype = (loc.locator_type or "").lower()

        # id= locator zaten id değeri → direkt kullan
        if ltype == "id":
            return value.replace("id=", "").strip()

        # data-test CSS → data-test değerini al
        dt = re.search(r"data-test(?:id)?\s*=\s*['\"]([^'\"]+)['\"]", value)
        if dt:
            return self._slugify(dt.group(1))

        # CSS: #id
        css_id = re.search(r"#([a-zA-Z][\w-]*)", value)
        if css_id:
            return css_id.group(1)

        # CSS: .class-name → class-name
        css_class = re.findall(r"\.([a-zA-Z][\w-]*)", value)
        if css_class:
            # UI lib prefix'lerini filtrele
            for cls in css_class:
                if not any(cls.startswith(p) for p in ("el-", "ant-", "v-", "q-", "md-")):
                    return self._slugify(cls)

        # XPath: @id='val'
        xp_id = re.search(r"@id=['\"]([^'\"]+)['\"]", value)
        if xp_id:
            return xp_id.group(1)

        # XPath: @class='val'
        xp_cls = re.search(r"@class=['\"]([^'\"]+)['\"]", value)
        if xp_cls:
            first_cls = xp_cls.group(1).split()[0]
            return self._slugify(first_cls)

        # XPath: text()='val' → button-val
        xp_txt = re.search(r"text\(\)\s*=\s*['\"]([^'\"]+)['\"]", value)
        if xp_txt:
            return f"{el.tag}-{self._slugify(xp_txt.group(1))}"

        # ClassName locator
        if ltype in ("class", "classname"):
            return self._slugify(value.replace("class=", "").strip())

        # Name locator
        if ltype == "name":
            name_val = value.replace("name=", "").strip()
            return f"{el.tag}-{self._slugify(name_val)}"

        # Vue elementinden türet (fallback)
        return self._best_audit_value(el)

    def _best_audit_value(self, el: VueElement) -> Optional[str]:
        """
        id öncelikli, sonra inner_text/name/class/tag.
        """
        if el.element_id:
            return el.element_id

        def slugify(s: str) -> str:
            return self._slugify(s)

        if el.inner_text and len(el.inner_text) < 25:
            return f"{el.tag}-{slugify(el.inner_text)}"
        if el.name:
            return f"{el.tag}-{slugify(el.name)}"
        if el.aria_label:
            return f"{el.tag}-{slugify(el.aria_label)}"
        if el.classes:
            semantic = [
                c for c in el.classes
                if not any(c.startswith(p) for p in ("el-", "ant-", "q-", "md-", "v-", "n-", "p-"))
            ]
            if semantic:
                return self._slugify(semantic[0])
        return el.tag

    # ── Yardımcılar ──────────────────────────────────────────────

    @staticmethod
    def _slugify(s: str) -> str:
        s = s.lower().strip()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        s = re.sub(r"-+", "-", s)
        return s.strip("-")[:40]

    def _find_el_by_class(
        self, cls: str, elements: list[VueElement], skip_ids: set[int]
    ) -> Optional[VueElement]:
        for el in elements:
            if el.is_interactive and id(el) not in skip_ids and cls in el.classes:
                return el
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
