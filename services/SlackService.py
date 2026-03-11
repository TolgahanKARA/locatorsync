"""
LocatorSync Slack Entegrasyonu.

Incoming Webhook URL ile Block Kit formatında analiz raporlarını Slack kanalına gönderir.
Slack Bot Token gerekmez — sadece webhook URL yeterlidir.
"""
import json
import requests
from datetime import datetime


class SlackService:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url.strip()

    def send_analysis_report(
        self,
        project_name: str,
        report_type: str,
        data: dict,
        duration: float = 0,
    ) -> dict:
        """
        Analiz sonucunu Slack'e gönderir.
        report_type: "audit" | "analyze" | "heal" | "diff" | "patch-vue"
        """
        blocks = self._build_blocks(project_name, report_type, data, duration)
        try:
            resp = requests.post(
                self.webhook_url,
                data=json.dumps({"blocks": blocks}),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code == 200:
                return {"ok": True}
            return {"ok": False, "errors": [f"Slack HTTP {resp.status_code}: {resp.text}"]}
        except requests.exceptions.Timeout:
            return {"ok": False, "errors": ["Slack bağlantısı zaman aşımına uğradı."]}
        except Exception as e:
            return {"ok": False, "errors": [str(e)]}

    # ── Block Kit ──────────────────────────────────────────────────

    def _build_blocks(
        self, project_name: str, report_type: str, data: dict, duration: float
    ) -> list:
        date = datetime.now().strftime("%d/%m/%Y %H:%M")
        type_labels = {
            "audit":     ":mag: Data-Test Audit",
            "analyze":   ":bar_chart: Capraz Analiz",
            "heal":      ":wrench: Heal",
            "diff":      ":twisted_rightwards_arrows: Vue Fark Analizi",
            "patch-vue": ":pencil: data-test Ekle",
        }
        label = type_labels.get(report_type, report_type)
        summary_blocks = self._get_summary_blocks(report_type, data)

        return [
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"*LocatorSync - {label}*\n\n"
                        f":file_folder:  Proje: *{project_name}*\n"
                        f":calendar:  _{date}_\n"
                        f":clock3:  _{duration}s_"
                    ),
                },
            },
            {"type": "divider"},
            *summary_blocks,
            {"type": "divider"},
        ]

    def _get_summary_blocks(self, report_type: str, data: dict) -> list:
        blocks = []

        if report_type == "audit":
            s = data.get("summary", data)
            covered = s.get("covered", 0)
            total = s.get("total_interactive", 0)
            pct = s.get("coverage_percent", 0)
            issues = s.get("total_issues", 0)
            blocks += [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":white_check_mark:  Kapsama"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": f"%{pct:.0f}  ({covered}/{total})"},
                        "style": "primary" if pct >= 80 else "danger",
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":warning:  Eksik data-test"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(issues)},
                    },
                },
            ]

        elif report_type == "analyze":
            s = data.get("summary", data)
            broken = s.get("broken_count", 0)
            risky = s.get("risky_count", 0)
            total = s.get("total_locators", 0)
            blocks += [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":x:  Kirик Locator"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(broken)},
                        "style": "danger" if broken > 0 else "primary",
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":warning:  Riskli Locator"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(risky)},
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":1234:  Toplam Locator"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(total)},
                    },
                },
            ]

        elif report_type == "heal":
            stats = data.get("stats", data)
            suggestions = stats.get("total_suggestions", 0)
            patch_results = data.get("patch_results", {})
            applied = len(patch_results.get("applied", []))
            blocks += [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":bulb:  Oneri"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(suggestions)},
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":white_check_mark:  Uygulanan"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(applied)},
                        "style": "primary",
                    },
                },
            ]

        elif report_type == "diff":
            removed = len(data.get("removed", []))
            renamed = len(data.get("renamed", []))
            added = len(data.get("added", []))
            affected = len(data.get("affected_robot_locators", []))
            blocks += [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":red_circle:  Silinen Element"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(removed)},
                        "style": "danger" if removed > 0 else "primary",
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":large_yellow_circle:  Yeniden Adlandirilan"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(renamed)},
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":green_circle:  Eklenen Element"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(added)},
                    },
                },
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":robot_face:  Etkilenen Robot Locator"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(affected)},
                    },
                },
            ]

        elif report_type == "patch-vue":
            apply_result = data.get("apply_result", {})
            applied = len(apply_result.get("applied", []))
            failed = len(apply_result.get("failed", []))
            dry_run = apply_result.get("dry_run", data.get("dry_run", True))
            status = "Dry-Run" if dry_run else "Uygulandi"
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f":pencil:  data-test Ekleme ({status})"},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": f"Basarili: {applied}"},
                    "style": "primary",
                },
            })
            if failed > 0:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": ":x:  Basarisiz"},
                    "accessory": {
                        "type": "button",
                        "text": {"type": "plain_text", "text": str(failed)},
                        "style": "danger",
                    },
                })

        return blocks
