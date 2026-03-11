from enum import Enum


class StabilityLevel(str, Enum):
    HIGH = "YÜKSEK"       # 80+
    MEDIUM = "ORTA"       # 50-79
    LOW = "DÜŞÜK"         # 30-49
    CRITICAL = "KRİTİK"  # <30

    @classmethod
    def from_score(cls, score: int) -> "StabilityLevel":
        if score >= 80:
            return cls.HIGH
        if score >= 50:
            return cls.MEDIUM
        if score >= 30:
            return cls.LOW
        return cls.CRITICAL
