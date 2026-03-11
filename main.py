"""
Vue Test Healer - Ana CLI Giriş Noktası

Kullanım:
  python main.py data-test-audit         → Vue'da data-test denetimi
  python main.py vue-only                → Sadece Vue stabilite analizi
  python main.py analyze [--json]        → Çapraz analiz (Vue + Robot)
  python main.py heal [--patch] [--dry-run]  → Locator heal & patch
"""
import sys
import click

try:
    from rich.console import Console
    console = Console()
    def echo(msg, color=None):
        if color:
            console.print(f"[{color}]{msg}[/{color}]")
        else:
            console.print(msg)
except ImportError:
    def echo(msg, color=None):
        print(msg)

from configs.AppConfig import AppConfig
from core.scanner.VueScanner import VueScanner
from core.auditor.DataTestAuditor import DataTestAuditor
from core.analyzer.LocatorExtractor import LocatorExtractor
from core.analyzer.ChangeMatcher import ChangeMatcher
from core.healer.HealerEngine import HealerEngine
from services.ReportService import ReportService


CONFIG_PATH = "config.yaml"


def load_config(config_path: str = CONFIG_PATH) -> AppConfig:
    return AppConfig(config_path)


def abort_with_errors(errors: list):
    for e in errors:
        echo(f"  [HATA] {e}", color="red")
    echo("\nconfig.yaml dosyasını düzenleyip tekrar deneyin.", color="yellow")
    sys.exit(1)


# ─── CLI Grubu ────────────────────────────────────────────────────

@click.group()
@click.version_option("1.0.0", prog_name="Vue Test Healer")
def cli():
    """
    Vue Test Healer - Vue.js + Robot Framework Locator Analiz Aracı

    Vue projesini ve Robot Framework test projesini birlikte analiz ederek
    kırılgan locator'ları tespit eder, iyileştirme önerileri üretir.
    """


# ─── ADIM 2: data-test-audit ──────────────────────────────────────

@cli.command("data-test-audit")
@click.option("--config", default=CONFIG_PATH, help="config.yaml yolu")
@click.option("--min-coverage", default=80, help="Minimum beklenen kapsama yüzdesi (varsayılan: 80)")
def data_test_audit(config, min_coverage):
    """Vue projesindeki data-test eksikliklerini denetler."""
    cfg = load_config(config)
    errors = cfg.validate()
    if errors:
        abort_with_errors(errors)

    echo("\nVue projesi taranıyor...", color="cyan")
    auditor = DataTestAuditor(cfg)
    report = auditor.audit()

    rg = ReportService(cfg)
    rg.print_audit_report(report)

    # Çıkış kodu: kapsama düşükse non-zero (CI entegrasyonu için)
    if report.coverage_percent < min_coverage:
        echo(
            f"\nUYARI: Kapsama oranı (%{report.coverage_percent}) "
            f"beklenen minimumun (%{min_coverage}) altında!",
            color="red",
        )
        sys.exit(1)
    else:
        echo(f"\nKapsama oranı %{report.coverage_percent} — hedef karşılandı.", color="green")


# ─── ADIM 3: vue-only ─────────────────────────────────────────────

@cli.command("vue-only")
@click.option("--config", default=CONFIG_PATH, help="config.yaml yolu")
@click.option("--show-all", is_flag=True, default=False, help="Tüm elementleri göster")
def vue_only(config, show_all):
    """Sadece Vue projesini tarar ve locator stabilite raporu üretir."""
    cfg = load_config(config)
    errors = cfg.validate()
    if errors:
        abort_with_errors(errors)

    echo("\nVue projesi analiz ediliyor...", color="cyan")
    scanner = VueScanner(cfg)
    elements = scanner.scan()

    if not elements:
        echo("Hiç Vue elementi bulunamadı. vue_project.path'i kontrol edin.", color="yellow")
        sys.exit(1)

    rg = ReportService(cfg)
    rg.print_vue_stability_report(elements, scanner.scanned_files)


# ─── ADIM 5: analyze ──────────────────────────────────────────────

@cli.command("analyze")
@click.option("--config", default=CONFIG_PATH, help="config.yaml yolu")
@click.option("--json", "save_json", is_flag=True, default=False, help="JSON rapor kaydet")
@click.option("--only-broken", is_flag=True, default=False, help="Sadece kırık locator'ları göster")
def analyze(config, save_json, only_broken):
    """Vue ve Robot Framework projelerini birlikte analiz eder."""
    cfg = load_config(config)

    vue_errors = cfg.validate()
    robot_errors = cfg.validate_robot()
    all_errors = vue_errors + robot_errors
    if all_errors:
        abort_with_errors(all_errors)

    echo("\nVue projesi taranıyor...", color="cyan")
    scanner = VueScanner(cfg)
    vue_elements = scanner.scan()
    echo(f"  {scanner.scanned_files} Vue dosyası, {len(vue_elements)} element bulundu.", color="green")

    echo("\nRobot Framework projesi taranıyor...", color="cyan")
    extractor = LocatorExtractor(cfg)
    extraction = extractor.extract()
    echo(
        f"  {extraction.files_scanned} Robot dosyası, "
        f"{extraction.total_locators} locator bulundu "
        f"({extraction.variable_locators} değişken, {extraction.inline_locators} inline).",
        color="green",
    )

    if not extraction.locators:
        echo("Robot projesinde locator bulunamadı.", color="yellow")
        sys.exit(0)

    echo("\nÇapraz analiz yapılıyor...", color="cyan")
    matcher = ChangeMatcher(cfg)
    result = matcher.analyze(
        vue_elements,
        extraction.locators,
        ignore_list=cfg.ignore_locators,
    )

    rg = ReportService(cfg)
    rg.print_analysis_report(result, save_json=save_json or cfg.get("reporting", "save_json"))

    # CI için çıkış kodu
    if result.summary.get("broken_locators", 0) > 0:
        sys.exit(1)


# ─── ADIM 6: heal ─────────────────────────────────────────────────

@cli.command("heal")
@click.option("--config", default=CONFIG_PATH, help="config.yaml yolu")
@click.option("--patch", "generate_patch", is_flag=True, default=False, help="Patch dosyaları üret")
@click.option("--apply", "apply_patch", is_flag=True, default=False, help="Patch'leri doğrudan uygula")
@click.option("--dry-run", is_flag=True, default=False, help="Patch uygulama simülasyonu (dosya değiştirmez)")
@click.option("--only-high", is_flag=True, default=False, help="Sadece yüksek güvenli önerileri uygula")
def heal(config, generate_patch, apply_patch, dry_run, only_high):
    """Kırık/riskli locator'lar için heal önerileri ve patch üretir."""
    cfg = load_config(config)

    vue_errors = cfg.validate()
    robot_errors = cfg.validate_robot()
    all_errors = vue_errors + robot_errors
    if all_errors:
        abort_with_errors(all_errors)

    echo("\nVue projesi taranıyor...", color="cyan")
    scanner = VueScanner(cfg)
    vue_elements = scanner.scan()

    echo("\nRobot Framework projesi taranıyor...", color="cyan")
    extractor = LocatorExtractor(cfg)
    extraction = extractor.extract()

    echo("\nÇapraz analiz yapılıyor...", color="cyan")
    matcher = ChangeMatcher(cfg)
    cross_result = matcher.analyze(
        vue_elements,
        extraction.locators,
        ignore_list=cfg.ignore_locators,
    )

    echo("\nHeal önerileri üretiliyor...", color="cyan")
    healer = HealerEngine(cfg)
    heal_report = healer.heal(
        cross_result.matches,
        generate_patch=generate_patch or apply_patch,
    )

    patch_results = None
    if apply_patch and heal_report.patch_files:
        patches = heal_report.patch_files
        if only_high:
            patches = [p for p in patches if p.suggestion.confidence == "high"]

        echo(f"\n{len(patches)} patch uygulanıyor (dry_run={dry_run})...", color="yellow")
        patch_results = healer.apply_patches(patches, dry_run=dry_run)

    rg = ReportService(cfg)
    rg.print_heal_report(heal_report, patch_results)


# ─── Durum kontrolü ───────────────────────────────────────────────

@cli.command("status")
@click.option("--config", default=CONFIG_PATH, help="config.yaml yolu")
def status(config):
    """Araç yapılandırmasını ve proje yollarını kontrol eder."""
    cfg = load_config(config)
    echo("\nVue Test Healer — Durum Kontrolü\n", color="cyan")

    vue_ok = not cfg.validate()
    robot_ok = not cfg.validate_robot()

    echo(f"  Vue projesi  : {cfg.vue_path or '(tanimli degil)'}  {'[OK]' if vue_ok else '[HATA]'}", color="green" if vue_ok else "red")
    echo(f"  Robot projesi: {cfg.robot_path or '(tanimli degil)'}  {'[OK]' if robot_ok else '[HATA]'}", color="green" if robot_ok else "red")
    echo(f"  Stabilite eşiği: {cfg.stability_threshold}")
    echo(f"  Kritik eşik    : {cfg.critical_threshold}")
    echo(f"  Çıktı dizini   : {cfg.output_dir}")
    echo(f"  Yedekleme      : {'Evet' if cfg.backup_before_patch else 'Hayır'}")

    if not vue_ok:
        echo("\n  config.yaml'da vue_project.path'i ayarlayın.", color="yellow")
    if not robot_ok:
        echo("  config.yaml'da robot_project.path'i ayarlayın.", color="yellow")


if __name__ == "__main__":
    cli()
