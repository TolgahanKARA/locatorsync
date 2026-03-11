"""
AppConfig - Uygulama yapılandırma yöneticisi.
YAML dosyasından veya dict'ten yüklenebilir.
"""
import yaml
from pathlib import Path
from typing import Any, Optional


class AppConfig:
    DEFAULT_CONFIG = {
        "vue_project": {"path": ""},
        "robot_project": {"path": ""},
        "analysis": {
            "stability_threshold": 50,
            "critical_threshold": 30,
            "vue_extensions": [".vue"],
            "robot_extensions": [".robot", ".resource", ".txt"],
            "ignore_dirs": ["node_modules", ".git", "dist", "build", "__pycache__", "venv"],
        },
        "healing": {
            "backup_before_patch": True,
            "auto_apply_high_confidence": False,
            "min_confidence_score": 0.6,
        },
        "reporting": {
            "output_dir": "reports",
            "save_json": True,
            "report_prefix": "vue_test_healer",
        },
        "ignore_locators": [],
    }

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = Path(config_path) if config_path else Path("config.yaml")
        self._config: dict = {}
        self._load()

    def _load(self):
        self._config = dict(self.DEFAULT_CONFIG)
        if self.config_path.exists():
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
            self._deep_merge(self._config, loaded)

    def _deep_merge(self, base: dict, override: dict):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    @classmethod
    def from_dict(cls, d: dict) -> "AppConfig":
        """YAML dosyası olmadan dict üzerinden oluştur (Web UI için)."""
        obj = object.__new__(cls)
        obj.config_path = Path("(in-memory)")
        obj._config = {}
        for k, v in cls.DEFAULT_CONFIG.items():
            obj._config[k] = dict(v) if isinstance(v, dict) else v
        obj._deep_merge(obj._config, d)
        return obj

    def get(self, *keys: str, default: Any = None) -> Any:
        node = self._config
        for key in keys:
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    @property
    def vue_path(self) -> Optional[Path]:
        p = self.get("vue_project", "path")
        return Path(p) if p else None

    @property
    def vue_old_path(self) -> Optional[Path]:
        p = self.get("vue_project", "old_path")
        return Path(p) if p else None

    @property
    def robot_path(self) -> Optional[Path]:
        p = self.get("robot_project", "path")
        return Path(p) if p else None

    @property
    def stability_threshold(self) -> int:
        return self.get("analysis", "stability_threshold", default=50)

    @property
    def critical_threshold(self) -> int:
        return self.get("analysis", "critical_threshold", default=30)

    @property
    def vue_extensions(self) -> list:
        return self.get("analysis", "vue_extensions", default=[".vue"])

    @property
    def robot_extensions(self) -> list:
        return self.get("analysis", "robot_extensions", default=[".robot", ".resource", ".txt"])

    @property
    def ignore_dirs(self) -> list:
        return self.get("analysis", "ignore_dirs", default=[])

    @property
    def ignore_locators(self) -> list:
        return self.get("ignore_locators", default=[])

    @property
    def output_dir(self) -> Path:
        return Path(self.get("reporting", "output_dir", default="reports"))

    @property
    def backup_before_patch(self) -> bool:
        return self.get("healing", "backup_before_patch", default=True)

    def validate(self) -> list:
        errors = []
        if not self.vue_path:
            errors.append("vue_project.path tanımlı değil.")
        elif not self.vue_path.exists():
            errors.append(f"vue_project.path bulunamadı: {self.vue_path}")
        return errors

    def validate_robot(self) -> list:
        errors = []
        if not self.robot_path:
            errors.append("robot_project.path tanımlı değil.")
        elif not self.robot_path.exists():
            errors.append(f"robot_project.path bulunamadı: {self.robot_path}")
        return errors
