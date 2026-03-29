"""Assistant runner abstractions and payload validation helpers."""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from pathlib import Path

REQUIRED_SCORE_KEYS = (
    "Team",
    "Market",
    "Product",
    "Traction",
    "Unit Economics",
    "Defensibility",
    "Terms",
)
REQUIRED_PAYLOAD_FIELDS = (
    "deal_id",
    "company_name",
    "category_scores",
    "risk_flags",
    "sectors",
    "geographies",
    "rationale",
    "citations",
    "category_rationales",
    "web_sweep_findings",
    "web_sweep_sources",
    "milestones_to_monitor",
    "key_unknowns",
    "return_scenarios",
    "assessment_limitations",
    "assessment_process",
)


class CodexRunner:
    """Run a single-deal assessment prompt through the Codex CLI."""

    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        """Execute Codex, parse JSON response, and validate payload fields.

        Args:
            prompt: Prompt passed to the assistant CLI.
            cwd: Working directory used for command execution.

        Returns:
            Validated assessment payload.
        """

        command = ["codex", "--search", "exec", "--skip-git-repo-check", "-C", str(cwd), "-"]
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Codex assessment failed: {result.stderr.strip()}")

        payload = parse_assessment_json(result.stdout)
        return validate_assessment_payload(payload)


class ClaudeRunner:
    """Run a single-deal assessment prompt through the Claude CLI."""

    def run_assessment(self, prompt: str, cwd: Path) -> dict[str, object]:
        """Execute Claude, parse JSON response, and validate payload fields.

        Args:
            prompt: Prompt passed to the assistant CLI.
            cwd: Working directory used for command execution.

        Returns:
            Validated assessment payload.
        """

        command = ["claude", "-p"]
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, check=False, cwd=str(cwd))
        if result.returncode != 0:
            raise RuntimeError(f"Claude assessment failed: {result.stderr.strip()}")

        payload = parse_assessment_json(result.stdout)
        return validate_assessment_payload(payload)


class CodexIntakeClassifier:
    """Codex-backed folder classifier used by smart intake mode."""

    def __init__(self, cwd: Path | None = None) -> None:
        """Initialize classifier execution context.
        
        Args:
            cwd: Optional working directory for codex CLI calls.
        
        Returns:
            None.
        """

        self.cwd = cwd or Path.cwd()

    def is_deal_folder(self, folder_name: str, parent_name: str | None = None) -> bool:
        """Return whether a folder likely represents a startup deal.

        Args:
            folder_name: Folder basename to classify.
            parent_name: Optional parent folder name for context.

        Returns:
            ``True`` when folder likely contains a company deal.
        """

        prompt = build_intake_classification_prompt(folder_name=folder_name, parent_name=parent_name)
        command = ["codex", "--search", "exec", "--skip-git-repo-check", "-C", str(self.cwd), "-"]
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(f"Codex intake classification failed: {result.stderr.strip()}")
        payload = parse_json_object(result.stdout)
        return bool(payload.get("is_deal_folder", False))


class ClaudeIntakeClassifier:
    """Claude-backed folder classifier used by smart intake mode."""

    def __init__(self, cwd: Path | None = None) -> None:
        """Initialize classifier execution context.
        
        Args:
            cwd: Optional working directory for claude CLI calls.
        
        Returns:
            None.
        """

        self.cwd = cwd or Path.cwd()

    def is_deal_folder(self, folder_name: str, parent_name: str | None = None) -> bool:
        """Return whether a folder likely represents a startup deal.

        Args:
            folder_name: Folder basename to classify.
            parent_name: Optional parent folder name for context.

        Returns:
            ``True`` when folder likely contains a company deal.
        """

        prompt = build_intake_classification_prompt(folder_name=folder_name, parent_name=parent_name)
        command = ["claude", "-p"]
        result = subprocess.run(command, input=prompt, capture_output=True, text=True, check=False, cwd=str(self.cwd))
        if result.returncode != 0:
            raise RuntimeError(f"Claude intake classification failed: {result.stderr.strip()}")
        payload = parse_json_object(result.stdout)
        return bool(payload.get("is_deal_folder", False))


def build_intake_classification_prompt(folder_name: str, parent_name: str | None) -> str:
    """Build strict-JSON classification prompt for folder intake decisions.

    Args:
        folder_name: Folder basename to classify.
        parent_name: Optional parent folder name used as additional context.

    Returns:
        Prompt text instructing the assistant to return a strict JSON decision.
    """

    parent_label = parent_name or "-"
    return (
        "Classify whether this folder name likely represents a startup deal/company folder "
        "or an administrative/document bucket.\n"
        "Return strict JSON only with keys:\n"
        '{"is_deal_folder": true|false, "confidence": 0-1, "reason": "..."}\n'
        "Guidance: company/deal names should be true; folders like closing/legal/documents/admin should be false.\n"
        f"Folder name: {folder_name}\n"
        f"Parent folder: {parent_label}\n"
    )

def parse_json_object(raw_output: str) -> dict[str, object]:
    """Parse a JSON object from raw assistant output, including fenced snippets.

    Args:
        raw_output: Assistant output that should include a JSON object.

    Returns:
        Parsed JSON dictionary.

    Raises:
        ValueError: If no valid JSON object can be extracted.
    """

    cleaned = raw_output.strip()
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced_match = re.search(r"```json\s*(\{.*\})\s*```", cleaned, flags=re.DOTALL)
    if fenced_match:
        parsed = json.loads(fenced_match.group(1))
        if isinstance(parsed, dict):
            return parsed

    bracket_match = re.search(r"(\{.*\})", cleaned, flags=re.DOTALL)
    if bracket_match:
        parsed = json.loads(bracket_match.group(1))
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("Assistant output did not contain valid JSON object")


def parse_assessment_json(raw_output: str) -> dict[str, object]:
    """Parse and return the top-level assessment JSON object.

    Args:
        raw_output: Raw assistant output expected to contain assessment JSON.

    Returns:
        Parsed top-level assessment dictionary.
    """

    return parse_json_object(raw_output)


def validate_assessment_payload(payload: dict[str, object]) -> dict[str, object]:
    """Validate and normalize assistant assessment payload structure/types.

    Args:
        payload: Raw parsed JSON object returned by an assistant.

    Returns:
        Normalized payload with required fields and canonical value types.
    """

    for field in REQUIRED_PAYLOAD_FIELDS:
        if field not in payload:
            raise ValueError(f"Missing required field: {field}")

    scores = payload["category_scores"]
    if not isinstance(scores, dict):
        raise ValueError("category_scores must be an object")

    normalized_scores: dict[str, float] = {}
    for key in REQUIRED_SCORE_KEYS:
        if key not in scores:
            raise ValueError(f"Missing required score key: {key}")
        normalized_scores[key] = float(scores[key])

    category_rationales = payload["category_rationales"]
    if not isinstance(category_rationales, dict):
        raise ValueError("category_rationales must be an object")

    normalized_rationales: dict[str, str] = {}
    for key in REQUIRED_SCORE_KEYS:
        if key not in category_rationales:
            raise ValueError(f"Missing category rationale: {key}")
        normalized_rationales[key] = str(category_rationales[key])

    return_scenarios = payload["return_scenarios"]
    if not isinstance(return_scenarios, list):
        raise ValueError("return_scenarios must be a list")
    if len(return_scenarios) < 3:
        raise ValueError("return_scenarios must include at least 3 scenarios")

    assessment_process = payload["assessment_process"]
    if not isinstance(assessment_process, dict):
        raise ValueError("assessment_process must be an object")

    required_process_flags = (
        "single_deal_equivalent",
        "used_full_rubric",
        "performed_web_sweep",
        "reconciled_docs_with_web",
        "built_three_case_return_model",
    )
    normalized_process: dict[str, object] = {}
    for key in required_process_flags:
        if key not in assessment_process:
            raise ValueError(f"Missing assessment_process key: {key}")
        value = assessment_process[key]
        if key == "single_deal_equivalent":
            normalized_process[key] = str(value)
            continue
        normalized_process[key] = _normalize_bool(value, field_name=f"assessment_process.{key}")

    if "notes" in assessment_process:
        normalized_process["notes"] = str(assessment_process["notes"])

    return {
        "deal_id": str(payload["deal_id"]),
        "company_name": str(payload["company_name"]),
        "category_scores": normalized_scores,
        "risk_flags": [str(item) for item in _as_list(payload["risk_flags"])],
        "sectors": [str(item) for item in _as_list(payload["sectors"])],
        "geographies": [str(item) for item in _as_list(payload["geographies"])],
        "rationale": str(payload["rationale"]),
        "citations": [_normalize_detail_item(item) for item in _as_list(payload["citations"])],
        "category_rationales": normalized_rationales,
        "web_sweep_findings": [_normalize_detail_item(item) for item in _as_list(payload["web_sweep_findings"])],
        "web_sweep_sources": [_normalize_detail_item(item) for item in _as_list(payload["web_sweep_sources"])],
        "milestones_to_monitor": [str(item) for item in _as_list(payload["milestones_to_monitor"])],
        "key_unknowns": [str(item) for item in _as_list(payload["key_unknowns"])],
        "return_scenarios": [dict(item) for item in return_scenarios if isinstance(item, dict)],
        "assessment_limitations": str(payload["assessment_limitations"]),
        "assessment_process": normalized_process,
        "verdict_one_liner": str(payload.get("verdict_one_liner", "")),
        "why_not_invest_now": [str(item) for item in _as_list(payload.get("why_not_invest_now", []))],
        "what_would_upgrade_to_invest": [
            str(item) for item in _as_list(payload.get("what_would_upgrade_to_invest", []))
        ],
        "market_context": str(payload.get("market_context", "")),
        "reconciliation_gaps": [str(item) for item in _as_list(payload.get("reconciliation_gaps", []))],
        "fit_call": str(payload.get("fit_call", "")),
        "founder_questions": [str(item) for item in _as_list(payload.get("founder_questions", []))],
    }


def build_assistant_runner(name: str):
    """Build the configured assistant runner.

    Args:
        name: Assistant backend name (``codex`` or ``claude``).

    Returns:
        Runner instance implementing ``run_assessment``.
    """

    normalized = name.strip().lower()
    if normalized == "codex":
        _require_command("codex")
        return CodexRunner()
    if normalized == "claude":
        _require_command("claude")
        return ClaudeRunner()
    raise ValueError(f"Unsupported assistant runner: {name}")


def build_intake_classifier(name: str, cwd: Path | None = None):
    """Build intake folder classifier for smart intake mode.

    Args:
        name: Assistant backend name (``codex`` or ``claude``).
        cwd: Optional working directory for the classifier command.

    Returns:
        Classifier object or ``None`` when unsupported.
    """

    normalized = name.strip().lower()
    if normalized == "codex":
        _require_command("codex")
        return CodexIntakeClassifier(cwd=cwd)
    if normalized == "claude":
        _require_command("claude")
        return ClaudeIntakeClassifier(cwd=cwd)
    return None


def _as_list(value: object) -> list[object]:
    """Normalize scalar/None values into list form.

    Args:
        value: Candidate list-like payload value.

    Returns:
        Original list when already a list, empty list for ``None``, otherwise
        a single-item list containing ``value``.
    """

    if isinstance(value, list):
        return value
    if value is None:
        return []
    return [value]


def _normalize_detail_item(item: object) -> dict[str, object] | str:
    """Normalize a citation/detail item into stable output form.

    Args:
        item: Raw item from assistant payload.

    Returns:
        Dictionary with normalized scalar values when parseable as mapping;
        otherwise a string representation.
    """

    if isinstance(item, dict):
        normalized: dict[str, object] = {}
        for key, value in item.items():
            normalized[str(key)] = _normalize_detail_scalar(value)
        return normalized
    if isinstance(item, str):
        parsed = _try_parse_detail_mapping(item)
        if parsed is not None:
            return parsed
    return str(item)


def _normalize_detail_scalar(value: object) -> object:
    """Normalize nested citation/detail scalar values.

    Args:
        value: Raw scalar/list/dict value from a detail mapping.

    Returns:
        JSON-serializable normalized value.
    """

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, dict):
        return {str(key): str(item) for key, item in value.items()}
    return str(value)


def _try_parse_detail_mapping(raw: str) -> dict[str, object] | None:
    """Try parsing a stringified mapping into a normalized dictionary.

    Args:
        raw: String that may represent a mapping literal/object.

    Returns:
        Parsed mapping when successful, otherwise ``None``.
    """

    text = raw.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None

    parsers = (json.loads, ast.literal_eval)
    for parser in parsers:
        try:
            parsed = parser(text)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(parsed, dict):
            return {str(key): _normalize_detail_scalar(value) for key, value in parsed.items()}
    return None


def _normalize_bool(value: object, field_name: str) -> bool:
    """Coerce common boolean-like payload values into bool.

    Args:
        value: Raw value expected to represent a boolean.
        field_name: Payload field path used in validation errors.

    Returns:
        Normalized boolean value.

    Raises:
        ValueError: If value cannot be interpreted as boolean.
    """

    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes"}:
            return True
        if normalized in {"false", "no"}:
            return False
    raise ValueError(f"{field_name} must be boolean")


def _require_command(command: str) -> None:
    """Ensure a required CLI binary is available in PATH.
    
    Args:
        command: CLI executable name to resolve.
    
    Raises:
        RuntimeError: If the executable cannot be found.
    
    Returns:
        None.
    """

    if shutil.which(command):
        return
    raise RuntimeError(
        f"Required CLI '{command}' was not found in PATH. "
        f"Install it or add it to PATH, or switch --assistant."
    )
