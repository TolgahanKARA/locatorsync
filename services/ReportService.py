"""
ReportService - CLI (rich/colorama), JSON ve patch raporu üretimi.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

try:
    from colorama import init as colorama_init
    colorama_init(autoreset=True)
except ImportError:
    pass

from core.analyzer.StabilityScorer import StabilityScorer


class ReportService:
    def __init__(self, config):
        self.config = config
        self.console = Console() if HAS_RICH else None
        self.output_dir = config.output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ─── Data-Test Audit Raporu ─────────────────────────────────────

    def print_audit_report(self, audit_report) -> None:
        self._header("DATA-TEST AUDIT RAPORU")
        self._print_audit_summary(audit_report)
        self._print_audit_issues(audit_report)
        if self.config.get("reporting", "save_json"):
            path = self._save_json(
                self._audit_to_dict(audit_report), "data_test_audit"
            )
            self._info(f"\nJSON rapor kaydedildi: {path}")

    def _print_audit_summary(self, r):
        if HAS_RICH and self.console:
            table = Table(title="Ozet", box=box.ROUNDED, show_header=False)
            table.add_column("Metrik", style="cyan", width=35)
            table.add_column("Deger", justify="right", width=15)
            table.add_row("Taranan dosya", str(r.files_scanned))
            table.add_row("Toplam element", str(r.total_elements))
            table.add_row("Interaktif element", str(r.total_interactive))
            table.add_row("data-test mevcut", f"[green]{r.covered}[/green]")
            table.add_row("data-test eksik", f"[red]{r.missing_count}[/red]")
            cov_color = "green" if r.coverage_percent >= 80 else ("yellow" if r.coverage_percent >= 50 else "red")
            table.add_row("Kapsama orani", f"[{cov_color}]{r.coverage_percent}%[/{cov_color}]")
            self.console.print(table)
            table2 = Table(title="Sorun Dagilimi", box=box.ROUNDED, show_header=False)
            table2.add_column("Seviye", width=20)
            table2.add_column("Adet", justify="right")
            table2.add_row("[red]KRITIK[/red]", str(len(r.critical_issues)))
            table2.add_row("[yellow]UYARI[/yellow]", str(len(r.warning_issues)))
            table2.add_row("[blue]BILGI[/blue]", str(len(r.issues) - len(r.critical_issues) - len(r.warning_issues)))
            self.console.print(table2)
        else:
            print(f"\n  Dosya: {r.files_scanned} | Toplam: {r.total_elements} | Interaktif: {r.total_interactive}")
            print(f"  Kapsama: %{r.coverage_percent} | Eksik: {r.missing_count}")

    def _print_audit_issues(self, r):
        if not r.issues:
            self._success("Hicbir sorun bulunamadi! Tebrikler.")
            return

        if HAS_RICH and self.console:
            table = Table(
                title=f"Tespit Edilen Sorunlar ({len(r.issues)})",
                box=box.SIMPLE_HEAD,
                show_lines=False,
            )
            table.add_column("Seviye", width=10)
            table.add_column("Dosya:Satir", width=35)
            table.add_column("Element", width=10)
            table.add_column("Oneri", width=50)

            severity_colors = {"critical": "red", "warning": "yellow", "info": "blue"}
            for issue in r.issues[:50]:
                sev = issue.severity
                color = severity_colors.get(sev, "white")
                file_line = f"{Path(issue.element.file).name}:{issue.element.line}"
                table.add_row(
                    f"[{color}]{sev.upper()}[/{color}]",
                    file_line,
                    f"<{issue.element.tag}>",
                    issue.suggestion,
                )
            self.console.print(table)
            if len(r.issues) > 50:
                self._info(f"  ... ve {len(r.issues) - 50} sorun daha (JSON raporunda tam liste)")
        else:
            for issue in r.issues[:50]:
                print(f"  [{issue.severity.upper()}] {Path(issue.element.file).name}:{issue.element.line} | <{issue.element.tag}> | {issue.suggestion}")

    # ─── Vue-Only Stabilite Raporu ─────────────────────────────────

    def print_vue_stability_report(self, elements: list, files_scanned: int) -> None:
        self._header("VUE STABILITE RAPORU")

        interactive = [e for e in elements if e.is_interactive]
        scores = [e.stability_score for e in interactive]
        avg_score = round(sum(scores) / len(scores), 1) if scores else 0

        dt_count = sum(1 for e in interactive if e.data_test or e.data_testid)
        id_count = sum(1 for e in interactive if e.element_id)
        class_only = sum(1 for e in interactive if not e.data_test and not e.data_testid and not e.element_id and e.classes)
        no_selector = sum(1 for e in interactive if not e.best_selector())

        high_stab = sum(1 for s in scores if s >= 80)
        mid_stab = sum(1 for s in scores if 50 <= s < 80)
        low_stab = sum(1 for s in scores if 30 <= s < 50)
        critical_stab = sum(1 for s in scores if s < 30)

        if HAS_RICH and self.console:
            t = Table(title="Genel Bakis", box=box.ROUNDED, show_header=False)
            t.add_column("", width=35)
            t.add_column("", justify="right", width=15)
            t.add_row("Taranan dosya", str(files_scanned))
            t.add_row("Toplam element", str(len(elements)))
            t.add_row("Interaktif element", str(len(interactive)))
            avg_color = StabilityScorer.color(int(avg_score))
            t.add_row("Ortalama stabilite skoru", f"[{avg_color}]{avg_score}[/{avg_color}]")
            self.console.print(t)

            t2 = Table(title="Stabilite Dagilimi", box=box.ROUNDED)
            t2.add_column("Seviye", width=15)
            t2.add_column("Adet", justify="right", width=8)
            t2.add_column("Oran", justify="right", width=8)
            total = len(interactive) or 1
            t2.add_row("[green]YUKSEK (80+)[/green]", str(high_stab), f"{round(high_stab/total*100)}%")
            t2.add_row("[yellow]ORTA (50-79)[/yellow]", str(mid_stab), f"{round(mid_stab/total*100)}%")
            t2.add_row("[orange1]DUSUK (30-49)[/orange1]", str(low_stab), f"{round(low_stab/total*100)}%")
            t2.add_row("[red]KRITIK (<30)[/red]", str(critical_stab), f"{round(critical_stab/total*100)}%")
            self.console.print(t2)

            t3 = Table(title="Selector Tipi Dagilimi", box=box.ROUNDED)
            t3.add_column("Tip", width=25)
            t3.add_column("Adet", justify="right", width=8)
            t3.add_row("[green]data-test/data-testid[/green]", str(dt_count))
            t3.add_row("[cyan]id[/cyan]", str(id_count))
            t3.add_row("[yellow]Sadece class[/yellow]", str(class_only))
            t3.add_row("[red]Selector yok[/red]", str(no_selector))
            self.console.print(t3)

            worst = sorted(interactive, key=lambda e: e.stability_score)[:10]
            if worst:
                t4 = Table(title="En Kirilgan 10 Element", box=box.SIMPLE_HEAD)
                t4.add_column("Skor", width=8)
                t4.add_column("Seviye", width=10)
                t4.add_column("Dosya:Satir", width=40)
                t4.add_column("Tag", width=10)
                t4.add_column("Mevcut Selector", width=30)
                for el in worst:
                    color = StabilityScorer.color(el.stability_score)
                    label = StabilityScorer.label(el.stability_score)
                    sel = el.best_selector() or "(yok)"
                    t4.add_row(
                        f"[{color}]{el.stability_score}[/{color}]",
                        f"[{color}]{label}[/{color}]",
                        f"{Path(el.file).name}:{el.line}",
                        f"<{el.tag}>",
                        sel,
                    )
                self.console.print(t4)
        else:
            print(f"\n  Ortalama stabilite: {avg_score} | YUKSEK: {high_stab} | ORTA: {mid_stab} | DUSUK: {low_stab} | KRITIK: {critical_stab}")

        if self.config.get("reporting", "save_json"):
            path = self._save_json(
                self._vue_stability_to_dict(elements, files_scanned, avg_score), "vue_stability"
            )
            self._info(f"\nJSON rapor kaydedildi: {path}")

    # ─── Cross-Analysis Raporu ──────────────────────────────────────

    def print_analysis_report(self, cross_result, save_json: bool = True) -> Optional[Path]:
        self._header("CAPRAZ ANALIZ RAPORU (Vue + Robot Framework)")
        s = cross_result.summary

        if HAS_RICH and self.console:
            t = Table(title="Genel Ozet", box=box.ROUNDED, show_header=False)
            t.add_column("", width=35)
            t.add_column("", justify="right", width=15)
            t.add_row("Robot locator sayisi", str(s.get("total_robot_locators", 0)))
            t.add_row("Vue element sayisi", str(s.get("total_vue_elements", 0)))
            t.add_row("[red]Kirik locator[/red]", f"[red]{s.get('broken_locators', 0)}[/red]")
            t.add_row("[yellow]Riskli locator[/yellow]", f"[yellow]{s.get('risky_locators', 0)}[/yellow]")
            t.add_row("[green]Saglikli locator[/green]", f"[green]{s.get('healthy_locators', 0)}[/green]")
            t.add_row("Kirilma orani", f"{s.get('break_rate', 0)}%")
            t.add_row("Risk orani", f"{s.get('risk_rate', 0)}%")
            self.console.print(t)

            if cross_result.broken:
                t2 = Table(title=f"Kirik Locator'lar ({len(cross_result.broken)})", box=box.SIMPLE_HEAD)
                t2.add_column("Dosya", width=25)
                t2.add_column("Satir", width=6)
                t2.add_column("Locator", width=40)
                t2.add_column("Tip", width=10)
                t2.add_column("Neden Kirik", width=50)
                for mr in cross_result.broken[:30]:
                    loc = mr.locator
                    t2.add_row(
                        Path(loc.file).name,
                        str(loc.line),
                        f"[red]{loc.value[:38]}[/red]",
                        loc.locator_type,
                        mr.break_reason or "-",
                    )
                self.console.print(t2)

            if cross_result.risky:
                t3 = Table(title=f"Riskli Locator'lar ({len(cross_result.risky)})", box=box.SIMPLE_HEAD)
                t3.add_column("Dosya", width=25)
                t3.add_column("Satir", width=6)
                t3.add_column("Locator", width=40)
                t3.add_column("Skor", width=6)
                t3.add_column("Sebep", width=40)
                for mr in cross_result.risky[:20]:
                    loc = mr.locator
                    color = StabilityScorer.color(loc.stability_score)
                    t3.add_row(
                        Path(loc.file).name,
                        str(loc.line),
                        f"[{color}]{loc.value[:38]}[/{color}]",
                        f"[{color}]{loc.stability_score}[/{color}]",
                        mr.break_reason or "Kirilgan selector",
                    )
                self.console.print(t3)
        else:
            print(f"\n  Kirik: {s.get('broken_locators')} | Riskli: {s.get('risky_locators')} | Saglikli: {s.get('healthy_locators')}")

        json_path = None
        if save_json:
            data = self._cross_result_to_dict(cross_result)
            json_path = self._save_json(data, "analysis")
            self._info(f"\nJSON rapor kaydedildi: {json_path}")

        return json_path

    # ─── Heal Raporu ────────────────────────────────────────────────

    def print_heal_report(self, heal_report, patch_results: dict = None) -> None:
        self._header("HEAL / PATCH RAPORU")

        if HAS_RICH and self.console:
            t = Table(title="Ozet", box=box.ROUNDED, show_header=False)
            t.add_column("", width=35)
            t.add_column("", justify="right", width=15)
            stats = heal_report.stats
            t.add_row("Toplam oneri", str(stats.get("total_healed", 0)))
            t.add_row("[green]Yuksek guven[/green]", f"[green]{stats.get('high_confidence', 0)}[/green]")
            t.add_row("[yellow]Orta guven[/yellow]", f"[yellow]{stats.get('medium_confidence', 0)}[/yellow]")
            t.add_row("[red]Dusuk guven[/red]", f"[red]{stats.get('low_confidence', 0)}[/red]")
            t.add_row("Patch dosyasi", str(stats.get("patch_files", 0)))
            t.add_row("Manuel inceleme", str(stats.get("skipped_manual_review", 0)))
            self.console.print(t)

            if heal_report.suggestions:
                t2 = Table(title="Oneriler", box=box.SIMPLE_HEAD)
                t2.add_column("Guven", width=10)
                t2.add_column("Dosya", width=25)
                t2.add_column("Eski Locator", width=35)
                t2.add_column("Yeni Locator", width=35)
                t2.add_column("Sebep", width=40)

                conf_colors = {"high": "green", "medium": "yellow", "low": "red"}
                for s in heal_report.suggestions[:40]:
                    cc = conf_colors.get(s.confidence, "white")
                    t2.add_row(
                        f"[{cc}]{s.confidence.upper()}[/{cc}]",
                        Path(s.locator.file).name,
                        f"[red]{s.original_value[:33]}[/red]",
                        f"[green]{s.suggested_value[:33]}[/green]",
                        s.reason[:38],
                    )
                self.console.print(t2)

            if patch_results:
                applied = patch_results.get("applied", [])
                failed = patch_results.get("failed", [])
                dry = patch_results.get("dry_run", True)
                if dry:
                    self._info(f"\n[DRY RUN] {len(applied)} dosya patch uygulanabilir.")
                else:
                    self._success(f"\n{len(applied)} dosyaya patch uygulandı.")
                if failed:
                    self._error(f"{len(failed)} dosyada hata: {failed}")

            vue_hints = [s for s in heal_report.suggestions if s.vue_element_hint]
            if vue_hints:
                self.console.print(
                    Panel(
                        "\n".join(f"  {h.vue_element_hint}  -> ({Path(h.locator.file).name}:{h.locator.line})" for h in vue_hints[:10]),
                        title="[cyan]Vue Tarafi Onerileri[/cyan]",
                        border_style="cyan",
                    )
                )

        if self.config.get("reporting", "save_json"):
            path = self._save_json(self._heal_to_dict(heal_report), "heal")
            self._info(f"\nJSON rapor kaydedildi: {path}")

    # ─── JSON Serialization ─────────────────────────────────────────

    def _audit_to_dict(self, r) -> dict:
        return {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "files_scanned": r.files_scanned,
                "total_elements": r.total_elements,
                "total_interactive": r.total_interactive,
                "covered": r.covered,
                "missing": r.missing_count,
                "coverage_percent": r.coverage_percent,
                "critical": len(r.critical_issues),
                "warnings": len(r.warning_issues),
            },
            "issues": [
                {
                    "severity": i.severity,
                    "file": i.element.file,
                    "line": i.element.line,
                    "tag": i.element.tag,
                    "message": i.message,
                    "suggestion": i.suggestion,
                    "suggested_data_test": i.suggested_data_test,
                }
                for i in r.issues
            ],
        }

    def _vue_stability_to_dict(self, elements, files_scanned, avg_score) -> dict:
        interactive = [e for e in elements if e.is_interactive]
        return {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "files_scanned": files_scanned,
                "total_elements": len(elements),
                "total_interactive": len(interactive),
                "avg_stability_score": avg_score,
            },
            "elements": [
                {
                    "tag": e.tag,
                    "file": e.file,
                    "line": e.line,
                    "data_test": e.data_test,
                    "data_testid": e.data_testid,
                    "id": e.element_id,
                    "classes": e.classes,
                    "name": e.name,
                    "aria_label": e.aria_label,
                    "stability_score": e.stability_score,
                    "stability_label": StabilityScorer.label(e.stability_score),
                    "best_selector": e.best_selector(),
                    "is_test_friendly": e.is_test_friendly(),
                }
                for e in interactive
            ],
        }

    def _cross_result_to_dict(self, r) -> dict:
        def loc_dict(mr):
            loc = mr.locator
            return {
                "name": loc.name,
                "value": loc.value,
                "type": loc.locator_type,
                "file": loc.file,
                "line": loc.line,
                "stability_score": loc.stability_score,
                "stability_label": StabilityScorer.label(loc.stability_score),
                "is_variable": loc.is_variable,
                "is_broken": mr.is_broken,
                "is_risky": mr.is_risky,
                "match_confidence": mr.match_confidence,
                "break_reason": mr.break_reason,
                "matched_element": {
                    "tag": mr.matched_element.tag,
                    "file": mr.matched_element.file,
                    "line": mr.matched_element.line,
                    "data_test": mr.matched_element.data_test,
                } if mr.matched_element else None,
            }

        return {
            "generated_at": datetime.now().isoformat(),
            "summary": r.summary,
            "broken_locators": [loc_dict(m) for m in r.broken],
            "risky_locators": [loc_dict(m) for m in r.risky],
            "healthy_locators": [loc_dict(m) for m in r.healthy],
        }

    def _heal_to_dict(self, r) -> dict:
        return {
            "generated_at": datetime.now().isoformat(),
            "stats": r.stats,
            "suggestions": [
                {
                    "original": s.original_value,
                    "suggested": s.suggested_value,
                    "type": s.suggested_type,
                    "confidence": s.confidence,
                    "confidence_score": s.confidence_score,
                    "reason": s.reason,
                    "patch_ready": s.patch_ready,
                    "vue_element_hint": s.vue_element_hint,
                    "file": s.locator.file,
                    "line": s.locator.line,
                }
                for s in r.suggestions
            ],
        }

    # ─── Yardımcılar ────────────────────────────────────────────────

    def _save_json(self, data: dict, prefix: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{self.config.get('reporting', 'report_prefix', default='vue_test_healer')}_{prefix}_{ts}.json"
        path = self.output_dir / fname
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return path

    def _header(self, title: str):
        if HAS_RICH and self.console:
            self.console.print(Panel(f"[bold cyan]{title}[/bold cyan]", border_style="cyan"))
        else:
            print(f"\n{'='*60}\n  {title}\n{'='*60}")

    def _success(self, msg: str):
        if HAS_RICH and self.console:
            self.console.print(f"[green]{msg}[/green]")
        else:
            print(msg)

    def _info(self, msg: str):
        if HAS_RICH and self.console:
            self.console.print(f"[cyan]{msg}[/cyan]")
        else:
            print(msg)

    def _error(self, msg: str):
        if HAS_RICH and self.console:
            self.console.print(f"[red]{msg}[/red]")
        else:
            print(f"HATA: {msg}")
