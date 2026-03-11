"""
Vue Test Healer - Web API Sunucusu
FastAPI tabanlı, ekip kullanımı için çok-proje desteği.
Yerel yol veya Git repo (URL + branch/commit) desteği.
"""
import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))

from configs.AppConfig import AppConfig
from core.scanner.VueScanner import VueScanner
from core.auditor.DataTestAuditor import DataTestAuditor
from core.analyzer.LocatorExtractor import LocatorExtractor
from core.analyzer.ChangeMatcher import ChangeMatcher
from core.analyzer.VueDiffAnalyzer import VueDiffAnalyzer
from core.healer.HealerEngine import HealerEngine
from core.patcher.VuePatcher import VuePatcher
from core.patcher.IdFromDataTestPatcher import IdFromDataTestPatcher
from services.ReportService import ReportService


# ─── Projects Storage ─────────────────────────────────────────────

PROJECTS_FILE = Path(__file__).parent.parent / "projects.json"


def load_projects() -> dict:
    if PROJECTS_FILE.exists():
        with open(PROJECTS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"projects": {}, "active_project": None}


def save_projects(data: dict):
    with open(PROJECTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_project_data(name: str) -> dict:
    data = load_projects()
    if name not in data["projects"]:
        raise HTTPException(status_code=404, detail=f"'{name}' projesi bulunamadi.")
    return data["projects"][name]


# ─── Git Resolver ────────────────────────────────────────────────

def _git_clone_to(url: str, ref: str, subdir: str, tmp: str) -> Path:
    """
    git init + fetch + checkout yaklasimiyla hem branch/tag hem commit hash destekler.
    """
    subprocess.run(["git", "init", tmp], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", tmp, "remote", "add", "origin", url],
        check=True, capture_output=True,
    )
    fetch_ref = ref.strip() if ref and ref.strip() else "HEAD"
    result = subprocess.run(
        ["git", "-C", tmp, "fetch", "--depth", "1", "origin", fetch_ref],
        capture_output=True, text=True, timeout=180,
    )
    if result.returncode != 0:
        raise ValueError(
            f"Git fetch basarisiz ({url} @ {fetch_ref}):\n{result.stderr.strip()}"
        )
    subprocess.run(
        ["git", "-C", tmp, "checkout", "FETCH_HEAD"],
        check=True, capture_output=True,
    )
    path = Path(tmp)
    if subdir and subdir.strip():
        path = path / subdir.strip("/\\")
        if not path.exists():
            raise ValueError(f"Git repo icinde alt dizin bulunamadi: {subdir}")
    return path


@contextmanager
def resolve_paths(p: dict):
    """
    Proje verisinden yerel yol veya git repo yollarini cozumler.
    Git klonlari icin gecici dizinleri oluşturur, bitince temizler.
    Yields: (vue_path, vue_old_path, robot_path) as str
    """
    tmps: List[str] = []

    def resolve(source: str, local_path: str, git_url: str,
                 git_ref: str, git_subdir: str, optional: bool = False) -> str:
        if source == "git":
            if not git_url or not git_url.strip():
                if optional:
                    return ""
                raise ValueError("Git URL bos olamaz.")
            tmp = tempfile.mkdtemp(prefix="vth_")
            tmps.append(tmp)
            return str(_git_clone_to(git_url.strip(), git_ref, git_subdir, tmp))
        return local_path or ""

    try:
        vue_path = resolve(
            p.get("vue_source", "local"),
            p.get("vue_path", ""),
            p.get("vue_git_url", ""),
            p.get("vue_git_branch", "main"),
            p.get("vue_git_subdir", ""),
        )
        # Eski Vue: tamamen opsiyonel
        old_source = p.get("vue_old_source", "local")
        old_path_raw = p.get("vue_old_path", "")
        old_git_url = p.get("vue_old_git_url", "")
        if old_source == "git" and old_git_url:
            vue_old_path = resolve(
                "git", "", old_git_url,
                p.get("vue_old_git_ref", ""),
                p.get("vue_old_git_subdir", ""),
                optional=True,
            )
        else:
            vue_old_path = old_path_raw or ""

        robot_path = resolve(
            p.get("robot_source", "local"),
            p.get("robot_path", ""),
            p.get("robot_git_url", ""),
            p.get("robot_git_branch", "main"),
            p.get("robot_git_subdir", ""),
        )
        yield vue_path, vue_old_path, robot_path
    finally:
        for t in tmps:
            shutil.rmtree(t, ignore_errors=True)


def build_config(vue_path: str, vue_old_path: str, robot_path: str, p: dict) -> AppConfig:
    return AppConfig.from_dict({
        "vue_project": {"path": vue_path, "old_path": vue_old_path},
        "robot_project": {"path": robot_path},
        "analysis": {
            "stability_threshold": p.get("stability_threshold", 50),
            "critical_threshold": p.get("critical_threshold", 30),
        },
        "reporting": {
            "output_dir": p.get("output_dir", "reports"),
            "save_json": True,
        },
        "ignore_locators": p.get("ignore_locators", []),
        "priority_folders": p.get("priority_folders", []),
    })


# ─── FastAPI App ──────────────────────────────────────────────────

app = FastAPI(title="LocatorSync", version="1.0.0")

# Eş zamanlı analiz kilidi — aynı anda yalnızca bir analiz çalışır
_analysis_lock = asyncio.Lock()
WEB_DIR = Path(__file__).parent


@app.get("/", response_class=HTMLResponse)
async def index():
    html_path = WEB_DIR / "index.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


# ─── Project Model ────────────────────────────────────────────────

class ProjectBody(BaseModel):
    name: str
    # Vue (guncel)
    vue_source: str = "local"       # "local" | "git"
    vue_path: str = ""
    vue_git_url: str = ""
    vue_git_branch: str = "main"
    vue_git_subdir: str = ""
    # Vue (eski snapshot — diff icin, opsiyonel)
    vue_old_source: str = "local"
    vue_old_path: str = ""
    vue_old_git_url: str = ""
    vue_old_git_ref: str = ""       # branch, tag veya commit hash
    vue_old_git_subdir: str = ""
    # Robot
    robot_source: str = "local"
    robot_path: str = ""
    robot_git_url: str = ""
    robot_git_branch: str = "main"
    robot_git_subdir: str = ""
    # Ayarlar
    stability_threshold: int = 50
    critical_threshold: int = 30
    ignore_locators: List[str] = []
    output_dir: str = "reports"
    # Tarama önceliği (opsiyonel)
    priority_folders: List[str] = []
    # Slack entegrasyonu (opsiyonel)
    slack_webhook: str = ""


# ─── Project Management ───────────────────────────────────────────

@app.get("/api/projects")
async def list_projects():
    data = load_projects()
    return {"ok": True, "projects": data["projects"], "active": data.get("active_project")}


@app.post("/api/projects")
async def create_project(body: ProjectBody):
    data = load_projects()
    if body.name in data["projects"]:
        raise HTTPException(status_code=409, detail=f"'{body.name}' projesi zaten mevcut.")
    project = body.model_dump()
    data["projects"][body.name] = project
    if not data["active_project"]:
        data["active_project"] = body.name
    save_projects(data)
    return {"ok": True, "project": project}


@app.put("/api/projects/{name}")
async def update_project(name: str, body: ProjectBody):
    data = load_projects()
    if name not in data["projects"]:
        raise HTTPException(status_code=404, detail=f"'{name}' projesi bulunamadi.")
    project = body.model_dump()
    project["name"] = name
    data["projects"][name] = project
    save_projects(data)
    return {"ok": True, "project": project}


@app.delete("/api/projects/{name}")
async def delete_project(name: str):
    data = load_projects()
    if name not in data["projects"]:
        raise HTTPException(status_code=404, detail=f"'{name}' projesi bulunamadi.")
    del data["projects"][name]
    if data.get("active_project") == name:
        remaining = list(data["projects"].keys())
        data["active_project"] = remaining[0] if remaining else None
    save_projects(data)
    return {"ok": True}


# ─── Validate ────────────────────────────────────────────────────

@app.get("/api/projects/{name}/validate")
async def validate_project(name: str):
    p = get_project_data(name)
    errors = []
    vue_source = p.get("vue_source", "local")
    robot_source = p.get("robot_source", "local")

    if vue_source == "local":
        vue_path = p.get("vue_path", "")
        if not vue_path or not Path(vue_path).exists():
            errors.append(f"Vue yolu bulunamadi: {vue_path}")
    else:
        if not p.get("vue_git_url", "").strip():
            errors.append("Vue Git URL bos.")

    if robot_source == "local":
        robot_path = p.get("robot_path", "")
        if not robot_path or not Path(robot_path).exists():
            errors.append(f"Robot yolu bulunamadi: {robot_path}")
    else:
        if not p.get("robot_git_url", "").strip():
            errors.append("Robot Git URL bos.")

    return {
        "ok": len(errors) == 0,
        "vue_source": vue_source,
        "robot_source": robot_source,
        "errors": errors,
        "settings": {
            "stability_threshold": p.get("stability_threshold", 50),
            "critical_threshold": p.get("critical_threshold", 30),
            "output_dir": p.get("output_dir", "reports"),
        },
    }


# ─── Audit ───────────────────────────────────────────────────────

@app.post("/api/projects/{name}/audit")
async def run_audit(name: str, min_coverage: int = 80):
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                auditor = DataTestAuditor(cfg)
                report = auditor.audit()
                rg = ReportService(cfg)
                data = rg._audit_to_dict(report)
                by_file = {}
                for issue in report.issues:
                    fname = Path(issue.element.file).name
                    by_file.setdefault(fname, []).append({
                        "severity": issue.severity,
                        "file": issue.element.file,
                        "line": issue.element.line,
                        "tag": issue.element.tag,
                        "message": issue.message,
                        "suggestion": issue.suggestion,
                        "suggested_data_test": issue.suggested_data_test,
                    })
                data["by_file"] = by_file
                data["coverage_ok"] = report.coverage_percent >= min_coverage
                return {"ok": True, "data": data, "duration": round(time.time() - t0, 2)}
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    async with _analysis_lock:
        return await asyncio.to_thread(_blocking)


# ─── Vue Only ────────────────────────────────────────────────────

@app.post("/api/projects/{name}/vue-only")
async def run_vue_only(name: str):
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                scanner = VueScanner(cfg)
                elements = scanner.scan()
                if not elements:
                    return {"ok": False, "errors": ["Hic Vue elementi bulunamadi."]}
                interactive = [e for e in elements if e.is_interactive]
                scores = [e.stability_score for e in interactive]
                avg_score = round(sum(scores) / len(scores), 1) if scores else 0
                rg = ReportService(cfg)
                data = rg._vue_stability_to_dict(elements, scanner.scanned_files, avg_score)
                total = len(interactive) or 1
                data["distribution"] = {
                    "high": sum(1 for s in scores if s >= 80),
                    "medium": sum(1 for s in scores if 50 <= s < 80),
                    "low": sum(1 for s in scores if 30 <= s < 50),
                    "critical": sum(1 for s in scores if s < 30),
                    "total": total,
                }
                return {"ok": True, "data": data, "duration": round(time.time() - t0, 2)}
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    async with _analysis_lock:
        return await asyncio.to_thread(_blocking)


# ─── Analyze ─────────────────────────────────────────────────────

@app.post("/api/projects/{name}/analyze")
async def run_analyze(name: str):
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate() + cfg.validate_robot()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                scanner = VueScanner(cfg)
                vue_elements = scanner.scan()
                extractor = LocatorExtractor(cfg)
                extraction = extractor.extract()
                if not extraction.locators:
                    return {"ok": False, "errors": ["Robot projesinde locator bulunamadi."]}
                matcher = ChangeMatcher(cfg)
                result = matcher.analyze(vue_elements, extraction.locators, ignore_list=cfg.ignore_locators)
                rg = ReportService(cfg)
                data = rg._cross_result_to_dict(result)
                data["scan_info"] = {
                    "vue_files": scanner.scanned_files,
                    "vue_elements": len(vue_elements),
                    "robot_files": extraction.files_scanned,
                    "robot_locators": extraction.total_locators,
                    "variable_locators": extraction.variable_locators,
                    "inline_locators": extraction.inline_locators,
                }
                return {"ok": True, "data": data, "duration": round(time.time() - t0, 2)}
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    async with _analysis_lock:
        return await asyncio.to_thread(_blocking)


# ─── Heal ────────────────────────────────────────────────────────

@app.post("/api/projects/{name}/heal")
async def run_heal(name: str):
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate() + cfg.validate_robot()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                scanner = VueScanner(cfg)
                vue_elements = scanner.scan()
                extractor = LocatorExtractor(cfg)
                extraction = extractor.extract()
                matcher = ChangeMatcher(cfg)
                cross_result = matcher.analyze(vue_elements, extraction.locators, ignore_list=cfg.ignore_locators)
                healer = HealerEngine(cfg)
                heal_report = healer.heal(cross_result.matches, generate_patch=False)
                rg = ReportService(cfg)
                data = rg._heal_to_dict(heal_report)
                return {"ok": True, "data": data, "duration": round(time.time() - t0, 2)}
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    async with _analysis_lock:
        return await asyncio.to_thread(_blocking)


class ApplyBody(BaseModel):
    dry_run: bool = True
    only_high: bool = False


@app.post("/api/projects/{name}/heal/apply")
async def apply_heal(name: str, body: ApplyBody):
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    # Git'ten çekilen Robot projesine yazma yapılamaz
    if p.get("robot_source", "local") == "git" and not body.dry_run:
        return {
            "ok": False,
            "errors": [
                "Git'ten çekilen Robot projesine yazma yapılamaz. "
                "Proje ayarlarında Robot kaynağını 'Yerel' olarak seçin."
            ],
        }

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate() + cfg.validate_robot()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                scanner = VueScanner(cfg)
                vue_elements = scanner.scan()
                extractor = LocatorExtractor(cfg)
                extraction = extractor.extract()
                matcher = ChangeMatcher(cfg)
                cross_result = matcher.analyze(vue_elements, extraction.locators, ignore_list=cfg.ignore_locators)
                healer = HealerEngine(cfg)
                heal_report = healer.heal(cross_result.matches, generate_patch=True)
                patches = heal_report.patch_files or []
                if body.only_high:
                    patches = [patch for patch in patches if patch.suggestion.confidence == "high"]
                patch_results = (
                    healer.apply_patches(patches, dry_run=body.dry_run)
                    if patches
                    else {"applied": [], "failed": [], "dry_run": body.dry_run}
                )
                rg = ReportService(cfg)
                data = rg._heal_to_dict(heal_report)
                data["patch_results"] = patch_results
                data["dry_run"] = body.dry_run
                return {"ok": True, "data": data, "duration": round(time.time() - t0, 2)}
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    async with _analysis_lock:
        return await asyncio.to_thread(_blocking)


# ─── Vue Diff ────────────────────────────────────────────────────

@app.post("/api/projects/{name}/diff")
async def run_diff(name: str):
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, vue_old_path, robot_path):
                if not vue_old_path:
                    return {
                        "ok": False,
                        "errors": [
                            "Eski Vue kaynak tanimli degil. "
                            "Proje ayarlarinda 'Eski Vue' bolumunu doldurun."
                        ],
                    }
                cfg = build_config(vue_path, vue_old_path, robot_path, p)
                errors = cfg.validate() + cfg.validate_robot()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()

                old_cfg = AppConfig.from_dict({"vue_project": {"path": vue_old_path}})
                old_scanner = VueScanner(old_cfg)
                old_elements = old_scanner.scan()

                new_scanner = VueScanner(cfg)
                new_elements = new_scanner.scan()

                extractor = LocatorExtractor(cfg)
                extraction = extractor.extract()

                analyzer = VueDiffAnalyzer()
                diff = analyzer.compare(old_elements, new_elements, extraction.locators)

                def change_dict(c):
                    return {
                        "change_type": c.change_type,
                        "selector_type": c.selector_type,
                        "old_value": c.old_value,
                        "new_value": c.new_value,
                        "old_file": Path(c.old_element.file).name if c.old_element else None,
                        "old_line": c.old_element.line if c.old_element else None,
                        "new_file": Path(c.new_element.file).name if c.new_element else None,
                        "new_line": c.new_element.line if c.new_element else None,
                        "affected_locators": [
                            {"value": l.value, "file": Path(l.file).name, "line": l.line}
                            for l in c.affected_locators
                        ],
                    }

                data = {
                    "summary": diff.summary,
                    "removed": [change_dict(c) for c in diff.removed],
                    "renamed": [change_dict(c) for c in diff.renamed],
                    "added": [change_dict(c) for c in diff.added],
                    "scan_info": {
                        "old_vue_path": vue_old_path,
                        "new_vue_path": vue_path,
                        "old_vue_files": old_scanner.scanned_files,
                        "new_vue_files": new_scanner.scanned_files,
                        "robot_locators": extraction.total_locators,
                    },
                }
                return {"ok": True, "data": data, "duration": round(time.time() - t0, 2)}
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    async with _analysis_lock:
        return await asyncio.to_thread(_blocking)


# ─── Vue Patcher ─────────────────────────────────────────────────

class PatchVueBody(BaseModel):
    dry_run: bool = True
    selected_indices: Optional[List[int]] = None


@app.post("/api/projects/{name}/patch-vue")
async def patch_vue_preview(name: str):
    """Eksik data-test attribute'larini tespit et, önizleme döndür (dosya degismez)."""
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                patcher = VuePatcher(cfg)
                report = patcher.preview()
                return {
                    "ok": True,
                    "data": report.to_dict(),
                    "duration": round(time.time() - t0, 2),
                }
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    return await asyncio.to_thread(_blocking)


@app.post("/api/projects/{name}/patch-vue/apply")
async def patch_vue_apply(name: str, body: PatchVueBody):
    """data-test attribute'larini Vue dosyalarına yaz."""
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    # Git kaynagindaki Vue dosyalarina yazamayiz
    if p.get("vue_source", "local") == "git":
        return {
            "ok": False,
            "errors": [
                "Git'ten çekilen Vue projesine yazma yapılamaz. "
                "Proje ayarlarında Vue kaynağını 'Yerel' olarak seçin."
            ],
        }

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                patcher = VuePatcher(cfg)
                report = patcher.preview()
                patches_to_apply = report.all_patches
                if body.selected_indices is not None:
                    idx_set = set(body.selected_indices)
                    patches_to_apply = [p for i, p in enumerate(patches_to_apply) if i in idx_set]
                result = patcher.apply(patches_to_apply, dry_run=body.dry_run)
                return {
                    "ok": True,
                    "data": {
                        **report.to_dict(),
                        "apply_result": result,
                        "dry_run": body.dry_run,
                    },
                    "duration": round(time.time() - t0, 2),
                }
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    async with _analysis_lock:
        return await asyncio.to_thread(_blocking)


# ─── ID from data-test ───────────────────────────────────────────

class IdPatchApplyBody(BaseModel):
    dry_run: bool = True
    apply_robot: bool = True
    selected_indices: Optional[List[int]] = None


@app.post("/api/projects/{name}/id-patch")
async def id_patch_preview(name: str):
    """data-test olan ama id olmayan Vue elementlerini tespit et (dosya değişmez)."""
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                patcher = IdFromDataTestPatcher(cfg)
                report = patcher.preview()
                return {
                    "ok": True,
                    "data": report.to_dict(),
                    "duration": round(time.time() - t0, 2),
                }
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    return await asyncio.to_thread(_blocking)


@app.post("/api/projects/{name}/id-patch/apply")
async def id_patch_apply(name: str, body: IdPatchApplyBody):
    """Vue dosyalarına id ekle ve Robot locatorlarını güncelle."""
    if _analysis_lock.locked():
        return {"ok": False, "errors": ["Baska bir analiz devam ediyor. Lutfen bekleyin."], "busy": True}
    p = get_project_data(name)

    if p.get("vue_source", "local") == "git":
        return {
            "ok": False,
            "errors": ["Git'ten çekilen Vue projesine yazma yapılamaz. Proje ayarlarında Vue kaynağını 'Yerel' olarak seçin."],
        }
    if body.apply_robot and not body.dry_run and p.get("robot_source", "local") == "git":
        return {
            "ok": False,
            "errors": ["Git'ten çekilen Robot projesine yazma yapılamaz."],
        }

    def _blocking():
        try:
            with resolve_paths(p) as (vue_path, _, robot_path):
                cfg = build_config(vue_path, "", robot_path, p)
                errors = cfg.validate()
                if errors:
                    return {"ok": False, "errors": errors}
                t0 = time.time()
                patcher = IdFromDataTestPatcher(cfg)
                report = patcher.preview()
                sugs = report.suggestions
                if body.selected_indices is not None:
                    idx_set = set(body.selected_indices)
                    sugs = [s for i, s in enumerate(sugs) if i in idx_set]
                result = patcher.apply(sugs, dry_run=body.dry_run, apply_robot=body.apply_robot)
                return {
                    "ok": True,
                    "data": {**report.to_dict(), "apply_result": result, "dry_run": body.dry_run},
                    "duration": round(time.time() - t0, 2),
                }
        except ValueError as e:
            return {"ok": False, "errors": [str(e)]}

    async with _analysis_lock:
        return await asyncio.to_thread(_blocking)


# ─── Slack ───────────────────────────────────────────────────────

class SlackReportBody(BaseModel):
    report_type: str      # "audit" | "analyze" | "heal" | "diff" | "patch-vue"
    data: dict
    duration: float = 0


@app.post("/api/projects/{name}/slack-report")
async def send_slack_report(name: str, body: SlackReportBody):
    """Analiz sonucunu proje Slack webhook URL'sine gönderir."""
    p = get_project_data(name)
    webhook_url = p.get("slack_webhook", "").strip()
    if not webhook_url:
        return {
            "ok": False,
            "errors": ["Proje ayarlarinda Slack Webhook URL tanimli degil."],
        }
    from services.SlackService import SlackService
    slack = SlackService(webhook_url)
    return slack.send_analysis_report(name, body.report_type, body.data, body.duration)


# ─── Reports ─────────────────────────────────────────────────────

@app.get("/api/reports")
async def list_reports():
    reports_dir = Path("reports")
    if not reports_dir.exists():
        return {"ok": True, "reports": []}
    files = sorted(reports_dir.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return {
        "ok": True,
        "reports": [
            {"filename": f.name, "size": f.stat().st_size, "modified": f.stat().st_mtime}
            for f in files[:30]
        ],
    }


@app.get("/api/reports/{filename}")
async def get_report(filename: str):
    path = Path("reports") / filename
    if not path.exists() or path.suffix != ".json":
        raise HTTPException(status_code=404)
    return FileResponse(str(path), media_type="application/json")
