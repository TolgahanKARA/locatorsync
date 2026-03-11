"""
RobotLocatorUpdater - Robot dosyalarındaki data-test locatorlarını id ile değiştirir.

Akış:
  1. Vue dosyalarını tara → hem data-test hem id olan elementlerin haritasını çıkar
  2. Robot dosyalarını tara → css=[data-test='X'] / xpath=...*@data-test='X' gibi locatorları bul
  3. data_test_value → id_value eşleşmesi varsa güncelleme öner

  preview()  → RobotUpdateReport (dosya değişmez)
  apply(...) → Robot dosyalarını günceller
"""
import re
from collections import defaultdict
from pathlib import Path

from configs.AppConfig import AppConfig
from core.scanner.VueScanner import VueScanner


# ── Veri modelleri ───────────────────────────────────────────────────────────

class RobotLocatorChange:
    """Bir Robot dosyasında yapılacak tek bir locator değişikliği."""
    def __init__(
        self,
        robot_file: str,
        robot_line: int,
        old_value: str,
        new_value: str,
        data_test_value: str,
        id_value: str,
    ):
        self.robot_file = robot_file
        self.robot_line = robot_line
        self.old_value = old_value
        self.new_value = new_value
        self.data_test_value = data_test_value
        self.id_value = id_value

    def to_dict(self) -> dict:
        return {
            "robot_file": self.robot_file,
            "robot_file_name": Path(self.robot_file).name,
            "robot_line": self.robot_line,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "data_test_value": self.data_test_value,
            "id_value": self.id_value,
        }


class RobotUpdateReport:
    def __init__(self):
        self.changes: list[RobotLocatorChange] = []
        self.stats: dict = {}

    def to_dict(self) -> dict:
        return {
            "changes": [c.to_dict() for c in self.changes],
            "stats": self.stats,
        }


# ── Ana sınıf ────────────────────────────────────────────────────────────────

class RobotLocatorUpdater:
    """
    Vue'da hem data-test hem id olan elementleri tespit eder,
    Robot dosyalarındaki data-test tabanlı locatorları id ile değiştirir.
    """

    # (pattern, replacement_fn) — replacement_fn(id_value) -> yeni locator stringi
    # Önce spesifik pattern'lar denenir; eşleşme olursa sonraki atlanır.
    _DT_PATTERNS = [
        # Tam selector: css=[data-test='X'] veya css=[data-testid='X']
        (re.compile(r"""css=\[data-test=['"]([^'"]+)['"]\]"""),   lambda v: f"css=#{v}"),
        (re.compile(r"""css=\[data-testid=['"]([^'"]+)['"]\]"""), lambda v: f"css=#{v}"),
        # XPath: xpath=...@data-test='X'
        (re.compile(r"""xpath=.*?@data-test=['"]([^'"]+)['"]"""),   lambda v: f"css=#{v}"),
        (re.compile(r"""xpath=.*?@data-testid=['"]([^'"]+)['"]"""), lambda v: f"css=#{v}"),
        # Gömülü: [data-test='X'] bir css selector içinde (örn. :has(), parent seçimi)
        # css=.input:has(input[data-test='X']) label  →  css=.input:has(input#id) label
        (re.compile(r"""\[data-test=['"]([^'"]+)['"]\]"""),   lambda v: f"#{v}"),
        (re.compile(r"""\[data-testid=['"]([^'"]+)['"]\]"""), lambda v: f"#{v}"),
    ]

    def __init__(self, config: AppConfig):
        self.config = config

    # ── Önizleme ────────────────────────────────────────────────

    def preview(self) -> RobotUpdateReport:
        report = RobotUpdateReport()

        # Vue'dan data-test -> id haritasi cikar (tarama istatistikleriyle birlikte)
        dt_to_id, skipped_non_unique, scan_stats = self._build_dt_to_id_map()

        # Robot dosyalarini tara
        robot_errors = self.config.validate_robot()
        if dt_to_id and not robot_errors:
            self._find_changes(dt_to_id, report)

        by_file = len({c.robot_file for c in report.changes})
        report.stats = {
            "total_changes": len(report.changes),
            "robot_files": by_file,
            "vue_elements_with_id": len(dt_to_id),
            "vue_elements_with_dt": len(dt_to_id),
            "skipped_non_unique": skipped_non_unique,
            "robot_available": not bool(robot_errors),
            "debug_dt_to_id_sample": dict(list(dt_to_id.items())[:10]),
            # Tarama istatistikleri — neden 0 döndüğünü anlamak için
            "scan_vue_files": scan_stats["vue_files"],
            "scan_total_elements": scan_stats["total_elements"],
            "scan_dynamic_skipped": scan_stats["dynamic_skipped"],
            "scan_no_dt_skipped": scan_stats["no_dt_skipped"],
        }
        return report

    def _build_dt_to_id_map(self) -> tuple[dict[str, str], list[str], dict]:
        """Vue'dan data-test olan elementlerin haritasi: {data_test_value: id_value}
        - id varsa kullanir; yoksa data-test degerini id olarak kullanir.
        - Yalnizca statik binding — dinamik (:data-test="expr") elementler haric tutulur.
        - Ayni data-test degerine sahip birden fazla farkli id varsa (non-unique) atlanir.
        Returns: (dt_to_id, skipped_non_unique_list, scan_stats)"""
        scanner = VueScanner(self.config)
        elements = scanner.scan()

        scan_stats = {
            "vue_files": len({el.file for el in elements}),
            "total_elements": len(elements),
            "dynamic_skipped": 0,
            "no_dt_skipped": 0,
        }

        # data-test degerine gore grupla
        dt_groups: dict[str, list[str]] = {}
        for el in elements:
            if el.is_dynamic_binding:
                scan_stats["dynamic_skipped"] += 1
                continue
            dt_value = el.data_test or el.data_testid
            if not dt_value:
                scan_stats["no_dt_skipped"] += 1
                continue
            # id varsa kullan, yoksa data-test degerini dogrudan id olarak kullan
            id_value = el.element_id if el.element_id else dt_value
            dt_groups.setdefault(dt_value, []).append(id_value)

        dt_to_id: dict[str, str] = {}
        skipped_non_unique: list[str] = []
        for dt_value, ids in dt_groups.items():
            unique_ids = list(dict.fromkeys(ids))
            if len(unique_ids) == 1:
                dt_to_id[dt_value] = unique_ids[0]
            else:
                skipped_non_unique.append(dt_value)

        return dt_to_id, skipped_non_unique, scan_stats

    def _find_changes(self, dt_to_id: dict, report: RobotUpdateReport):
        """Robot dosyalarını tara, data-test tabanlı locatorları bul ve eşleştir."""
        robot_path = self.config.robot_path
        if not robot_path or not robot_path.exists():
            return

        ignore = set(self.config.ignore_dirs)
        robot_files = [
            p for ext in self.config.robot_extensions
            for p in robot_path.rglob(f"*{ext}")
            if not any(part in ignore for part in p.parts)
        ]

        seen: set[tuple] = set()
        for robot_file in robot_files:
            try:
                lines = robot_file.read_text(encoding="utf-8", errors="ignore").split("\n")
            except Exception:
                continue

            for line_num, line in enumerate(lines, 1):
                for pattern, make_new in self._DT_PATTERNS:
                    m = pattern.search(line)
                    if not m:
                        continue
                    dt_value = m.group(1)
                    old_locator = m.group(0)

                    if dt_value not in dt_to_id:
                        break
                    id_value = dt_to_id[dt_value]
                    new_locator = make_new(id_value)

                    key = (str(robot_file), line_num, old_locator)
                    if key not in seen:
                        seen.add(key)
                        report.changes.append(RobotLocatorChange(
                            robot_file=str(robot_file),
                            robot_line=line_num,
                            old_value=old_locator,
                            new_value=new_locator,
                            data_test_value=dt_value,
                            id_value=id_value,
                        ))
                    break  # satırda bir eşleşme yeterli

    # ── Uygulama ────────────────────────────────────────────────

    def apply(
        self,
        changes: list[RobotLocatorChange],
        dry_run: bool = True,
    ) -> dict:
        if dry_run:
            return {
                "dry_run": True,
                "would_patch": len(changes),
                "applied": [],
                "failed": [],
            }

        by_file: dict[str, list[RobotLocatorChange]] = defaultdict(list)
        for c in changes:
            by_file[c.robot_file].append(c)

        applied, failed = [], []

        for file_path, file_changes in by_file.items():
            try:
                lines = Path(file_path).read_text(encoding="utf-8", errors="ignore").split("\n")
            except Exception as e:
                failed.append({"file": Path(file_path).name, "error": str(e)})
                continue

            changed = False
            for change in file_changes:
                idx = change.robot_line - 1
                if idx < 0 or idx >= len(lines):
                    continue
                old_line = lines[idx]
                new_line = old_line.replace(change.old_value, change.new_value, 1)
                if new_line != old_line:
                    lines[idx] = new_line
                    changed = True
                    applied.append({
                        "file": Path(file_path).name,
                        "line": change.robot_line,
                        "old": change.old_value,
                        "new": change.new_value,
                    })

            if changed:
                try:
                    Path(file_path).write_text("\n".join(lines), encoding="utf-8")
                except Exception as e:
                    failed.append({"file": Path(file_path).name, "error": str(e)})

        return {
            "dry_run": False,
            "applied": applied,
            "failed": failed,
        }
