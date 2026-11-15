from dataclasses import dataclass
from typing import Optional


@dataclass
class TranspilerDiagnostic:
    level: str  # "Error" or "Warning"
    category: str  # "Syntax Error", "Translation Error", "Type Inference Error", "Compilation Error"
    line: Optional[int]
    feature: str
    expression: str
    reason: str
    suggestion: str
    source_line: Optional[str] = None

    def format(self) -> str:
        parts = [f"{self.category}:"]
        if self.line is not None:
            parts.append(f"Line: {self.line}")
        if self.source_line:
            parts.append(f"Source: {self.source_line.strip()}")
        parts.append(f"Feature: {self.feature}")
        if self.expression:
            parts.append(f"Expression: {self.expression}")
        parts.append(f"Reason: {self.reason}")
        parts.append(f"Suggestion: {self.suggestion}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "category": self.category,
            "line": self.line,
            "feature": self.feature,
            "expression": self.expression,
            "reason": self.reason,
            "suggestion": self.suggestion,
            "source_line": self.source_line,
            "formatted": self.format(),
        }


class TranspilerError(Exception):
    """Structured compiler error with Python line numbers and actionable suggestions."""

    def __init__(
        self,
        feature: str,
        reason: str,
        suggestion: str,
        line: Optional[int] = None,
        expression: str = "",
        category: str = "Translation Error",
        source_line: Optional[str] = None,
    ):
        self.diagnostic = TranspilerDiagnostic(
            level="Error",
            category=category,
            line=line,
            feature=feature,
            expression=expression,
            reason=reason,
            suggestion=suggestion,
            source_line=source_line,
        )
        super().__init__(self.diagnostic.format())


def get_source_line(source_lines: list[str], line: Optional[int]) -> Optional[str]:
    if line is None or not source_lines:
        return None
    if 1 <= line <= len(source_lines):
        return source_lines[line - 1]
    return None