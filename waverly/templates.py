from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


class TemplateError(RuntimeError):
    pass


@dataclass
class TemplateMetadata:
    template_id: str
    name: str
    severity: str
    tags: List[str]
    path: Path
    description: str = ""

    def to_dict(self) -> Dict[str, str]:
        return {
            "template_id": self.template_id,
            "name": self.name,
            "severity": self.severity,
            "tags": ",".join(self.tags),
            "path": str(self.path),
            "description": self.description,
        }


class TemplateManager:
    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def list_templates(self) -> List[TemplateMetadata]:
        templates = []
        for file_path in sorted(self.directory.glob("**/*.yaml")):
            metadata = self._read_metadata(file_path)
            if metadata:
                templates.append(metadata)
        return templates

    def load_template(self, template_id: str) -> str:
        path = self._find_by_id(template_id)
        if not path:
            raise TemplateError(f"Template {template_id} not found")
        return path.read_text(encoding="utf-8")

    def save_template(self, template_id: str, content: str) -> Path:
        metadata = self._metadata_from_content(content)
        if metadata.template_id != template_id:
            raise TemplateError("Template id mismatch")
        path = self.directory / f"{template_id}.yaml"
        path.write_text(content, encoding="utf-8")
        return path

    def create_template(
        self,
        name: str,
        severity: str,
        tags: Iterable[str],
        body: str,
        *,
        template_id: Optional[str] = None,
    ) -> Path:
        metadata = self._metadata_from_content(body)
        target_id = template_id or metadata.template_id
        path = self.directory / f"{target_id}.yaml"
        if path.exists():
            raise TemplateError(f"Template {target_id} already exists")
        path.write_text(body, encoding="utf-8")
        return path

    def delete_template(self, template_id: str) -> None:
        path = self._find_by_id(template_id)
        if path and path.exists():
            path.unlink()
        else:
            raise TemplateError(f"Template {template_id} not found")

    def import_templates(self, source: Path) -> List[Path]:
        source_path = Path(source)
        if not source_path.exists():
            raise TemplateError(f"Template source {source} not found")
        imported: List[Path] = []
        for file_path in source_path.rglob("*.yaml"):
            metadata = self._read_metadata(file_path)
            if not metadata:
                continue
            target_path = self.directory / f"{metadata.template_id}.yaml"
            if target_path.exists():
                continue
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(file_path, target_path)
            imported.append(target_path)
        return imported

    def _find_by_id(self, template_id: str) -> Optional[Path]:
        candidate = self.directory / f"{template_id}.yaml"
        if candidate.exists():
            return candidate
        for file_path in self.directory.glob("**/*.yaml"):
            metadata = self._read_metadata(file_path)
            if metadata and metadata.template_id == template_id:
                return file_path
        return None

    def _read_metadata(self, path: Path) -> Optional[TemplateMetadata]:
        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            return None
        try:
            return self._metadata_from_content(content, path)
        except TemplateError:
            return None

    def _metadata_from_content(self, content: str, path: Optional[Path] = None) -> TemplateMetadata:
        lines = content.splitlines()
        template_id = _extract_scalar(lines, "id")
        if not template_id:
            raise TemplateError("Template must include an id field")
        info = _extract_section(lines, "info")
        name = info.get("name", template_id)
        severity = info.get("severity", "info")
        tags = _ensure_list(info.get("tags", []))
        description = info.get("description", "")
        return TemplateMetadata(
            template_id=template_id,
            name=name,
            severity=severity,
            tags=tags,
            path=path or self.directory / f"{template_id}.yaml",
            description=description,
        )


def _ensure_list(value: object) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _extract_scalar(lines: List[str], key: str) -> Optional[str]:
    prefix = f"{key}:"
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith(prefix):
            value = stripped[len(prefix) :].strip()
            return _strip_quotes(value)
    return None


def _strip_quotes(value: str) -> str:
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    return value


def _extract_section(lines: List[str], section: str) -> Dict[str, object]:
    result: Dict[str, object] = {}
    section_prefix = f"{section}:"
    inside = False
    base_indent = None
    current_key: Optional[str] = None
    for line in lines:
        if not inside:
            if line.strip().startswith(section_prefix):
                inside = True
            continue
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        if base_indent is None:
            base_indent = indent
        if indent < base_indent:
            break
        stripped = line.strip()
        if stripped.startswith("-") and current_key:
            value = stripped[1:].strip()
            values = result.setdefault(current_key, [])
            if isinstance(values, list):
                values.append(_strip_quotes(value))
            continue
        if ":" in stripped:
            key, _, raw = stripped.partition(":")
            current_key = key.strip()
            value = raw.strip()
            if value:
                if value.startswith("[") and value.endswith("]"):
                    items = [item.strip() for item in value[1:-1].split(",") if item.strip()]
                    result[current_key] = [_strip_quotes(item) for item in items]
                else:
                    result[current_key] = _strip_quotes(value)
            else:
                result[current_key] = []
        elif current_key:
            # Multi-line strings
            existing = result.get(current_key, "")
            result[current_key] = f"{existing}\n{stripped}".strip()
    return result


def build_basic_template(
    template_id: str,
    name: str,
    severity: str,
    method: str,
    path: str,
    matcher_words: Iterable[str],
) -> str:
    words = list(matcher_words)
    word_lines = "\n".join(f"          - {_quote(word)}" for word in words) or "          - success"
    tags_line = ",".join(words) if words else "demo"
    lines = [
        f"id: {template_id}",
        "info:",
        f"  name: {name}",
        "  author: waverly",
        f"  severity: {severity}",
        f"  tags: {tags_line}",
        "http:",
        "  - method: {0}".format(method.upper()),
        "    path:",
        f"      - '{path}'",
        "    matchers:",
        "      - type: word",
        "        words:",
        word_lines,
    ]
    return "\n".join(lines)


def _quote(value: str) -> str:
    if any(ch in value for ch in [":", "#", "\"", "'"]):
        return f'"{value}"'
    return value


__all__ = ["TemplateManager", "TemplateMetadata", "TemplateError", "build_basic_template"]

