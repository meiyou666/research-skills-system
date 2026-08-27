#!/usr/bin/env python3
"""Check structural and reference integrity of a hypothesis brief."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REVIEW_SEVERITIES = ("BLOCKING", "NARROWING", "INFORMATIVE")
REVIEW_STATUSES = ("OPEN", "RESOLVED", "ACCEPTED_RISK")


def dependency_cycles(
    node_ids: set[str], dependencies: dict[str, list[str]]
) -> list[list[str]]:
    """Return deterministic cycles among IDs in one dependency namespace."""

    state: dict[str, int] = {}
    stack: list[str] = []
    stack_index: dict[str, int] = {}
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def visit(node: str) -> None:
        state[node] = 1
        stack_index[node] = len(stack)
        stack.append(node)
        for target in dependencies.get(node, []):
            if target not in node_ids:
                continue
            if state.get(target, 0) == 0:
                visit(target)
            elif state.get(target) == 1:
                cycle = stack[stack_index[target] :] + [target]
                body = cycle[:-1]
                rotations = [tuple(body[index:] + body[:index]) for index in range(len(body))]
                canonical = min(rotations)
                if canonical not in seen_cycles:
                    seen_cycles.add(canonical)
                    cycles.append(list(canonical) + [canonical[0]])
        stack.pop()
        stack_index.pop(node, None)
        state[node] = 2

    for node in sorted(node_ids):
        if state.get(node, 0) == 0:
            visit(node)
    return cycles


def validate(value: Any) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(value, dict):
        return ["root must be an object"], warnings
    if value.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if not isinstance(value.get("brief_id"), str) or not value.get("brief_id", "").strip():
        errors.append("brief_id is required")
    if not isinstance(value.get("version"), int) or isinstance(value.get("version"), bool) or value.get("version", 0) < 1:
        errors.append("version must be a positive integer")
    if value.get("status") not in {"draft", "frozen"}:
        errors.append("status must be draft or frozen")
    if not value.get("purpose"):
        warnings.append("purpose is not recorded")
    if not value.get("evidence_input"):
        warnings.append("evidence-input provenance is not recorded")

    evidence = value.get("evidence_statements", [])
    if not isinstance(evidence, list):
        errors.append("evidence_statements must be a list")
        evidence = []
    evidence_ids: set[str] = set()
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            errors.append(f"evidence_statements[{index}] must be an object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"evidence_statements[{index}].id is required")
        elif item_id in evidence_ids:
            errors.append(f"duplicate evidence id: {item_id}")
        else:
            evidence_ids.add(item_id)
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append(
                f"evidence_statements[{index}].text is required and must be a non-empty string; got {text!r}"
            )

    questions = value.get("questions", [])
    if not isinstance(questions, list):
        errors.append("questions must be a list")
        questions = []
    question_ids: set[str] = set()
    question_dependencies: list[tuple[int, str | None, list[Any]]] = []
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            errors.append(f"questions[{index}] must be an object")
            continue
        qid = question.get("id")
        if not isinstance(qid, str) or not qid:
            errors.append(f"questions[{index}].id is required")
        elif qid in question_ids:
            errors.append(f"duplicate question id: {qid}")
        else:
            question_ids.add(qid)
            if qid in evidence_ids:
                errors.append(f"claim ID is reused across evidence and question namespaces: {qid}")
        if not question.get("question"):
            warnings.append(f"questions[{index}] has no question text")
        if not question.get("observables"):
            warnings.append(f"questions[{index}] has no observables")
        dependencies = question.get("depends_on", [])
        if not isinstance(dependencies, list):
            errors.append(f"questions[{index}].depends_on must be a list")
        else:
            question_dependencies.append(
                (index, qid if isinstance(qid, str) and qid else None, dependencies)
            )

    valid_question_dependencies = evidence_ids | question_ids
    for index, qid, dependencies in question_dependencies:
        for dependency in dependencies:
            if not isinstance(dependency, str) or not dependency.strip():
                errors.append(
                    f"questions[{index}].depends_on entries must be non-empty local ID strings"
                )
            elif dependency == qid:
                errors.append(f"questions[{index}] cannot depend on itself: {dependency}")
            elif dependency not in valid_question_dependencies:
                errors.append(f"questions[{index}] references unknown dependency {dependency}")
    question_graph = {
        qid: [item for item in dependencies if isinstance(item, str)]
        for _, qid, dependencies in question_dependencies
        if qid is not None
    }
    for cycle in dependency_cycles(question_ids, question_graph):
        errors.append("question dependency cycle: " + " -> ".join(cycle))

    hypotheses = value.get("hypotheses", [])
    if not isinstance(hypotheses, list):
        errors.append("hypotheses must be a list")
        hypotheses = []
    hypothesis_ids: set[str] = set()
    hypothesis_dependencies: dict[str, list[str]] = {}
    for index, hypothesis in enumerate(hypotheses):
        if not isinstance(hypothesis, dict):
            errors.append(f"hypotheses[{index}] must be an object")
            continue
        hid = hypothesis.get("id")
        if not isinstance(hid, str) or not hid:
            errors.append(f"hypotheses[{index}].id is required")
        elif hid in hypothesis_ids:
            errors.append(f"duplicate hypothesis id: {hid}")
        else:
            hypothesis_ids.add(hid)
            if hid in evidence_ids or hid in question_ids:
                errors.append(f"claim ID is reused across brief namespaces: {hid}")
        if not hypothesis.get("statement"):
            warnings.append(f"hypotheses[{index}] has no statement")
        refs = hypothesis.get("prior_evidence_ids", [])
        if not isinstance(refs, list):
            errors.append(f"hypotheses[{index}].prior_evidence_ids must be a list")
        else:
            for evidence_id in refs:
                if not isinstance(evidence_id, str) or not evidence_id.strip():
                    errors.append(
                        f"hypotheses[{index}].prior_evidence_ids entries must be non-empty ID strings"
                    )
                elif evidence_id not in evidence_ids:
                    errors.append(f"hypotheses[{index}] references unknown evidence {evidence_id}")
        dependencies = hypothesis.get("depends_on", [])
        if not isinstance(dependencies, list):
            errors.append(f"hypotheses[{index}].depends_on must be a list")
        elif isinstance(hid, str) and hid:
            hypothesis_dependencies[hid] = [
                item for item in dependencies if isinstance(item, str)
            ]
        if not hypothesis.get("falsifiers"):
            warnings.append(f"hypotheses[{index}] has no observable falsifier")

    valid_dependencies = question_ids | hypothesis_ids
    for index, hypothesis in enumerate(hypotheses):
        if isinstance(hypothesis, dict) and isinstance(hypothesis.get("depends_on", []), list):
            for dependency in hypothesis.get("depends_on", []):
                if not isinstance(dependency, str) or not dependency.strip():
                    errors.append(
                        f"hypotheses[{index}].depends_on entries must be non-empty local ID strings"
                    )
                elif dependency == hypothesis.get("id"):
                    errors.append(f"hypotheses[{index}] cannot depend on itself: {dependency}")
                elif dependency not in valid_dependencies:
                    errors.append(f"hypotheses[{index}] references unknown dependency {dependency}")
    for cycle in dependency_cycles(hypothesis_ids, hypothesis_dependencies):
        errors.append("hypothesis dependency cycle: " + " -> ".join(cycle))

    review = value.get("adversarial_review")
    blockers: list[Any] = []
    blocking_objections: list[tuple[str, str]] = []
    objection_statuses: dict[str, tuple[str, str]] = {}
    standalone_blockers: list[str] = []
    if review is not None and not isinstance(review, dict):
        errors.append(
            f"adversarial_review must be an object when present; got {type(review).__name__}"
        )
    elif isinstance(review, dict):
        objections = review.get("objections", [])
        if not isinstance(objections, list):
            errors.append(
                "adversarial_review.objections must be a list; "
                f"got {type(objections).__name__}"
            )
            objections = []
        objection_ids: set[str] = set()
        for index, objection in enumerate(objections):
            path = f"adversarial_review.objections[{index}]"
            if not isinstance(objection, dict):
                errors.append(f"{path} must be an object; got {type(objection).__name__}")
                continue
            objection_id = objection.get("id")
            if not isinstance(objection_id, str) or not objection_id.strip():
                errors.append(f"{path}.id is required and must be a non-empty string")
            elif objection_id in objection_ids:
                errors.append(f"duplicate adversarial-review objection id: {objection_id}")
            else:
                objection_ids.add(objection_id)
            severity = objection.get("severity")
            if severity not in REVIEW_SEVERITIES:
                errors.append(
                    f"{path}.severity must be one of {', '.join(REVIEW_SEVERITIES)}; got {severity!r}"
                )
            status = objection.get("status")
            if status not in REVIEW_STATUSES:
                errors.append(
                    f"{path}.status must be one of {', '.join(REVIEW_STATUSES)}; got {status!r}"
                )
            if (
                isinstance(objection_id, str)
                and objection_id.strip()
                and severity in REVIEW_SEVERITIES
                and status in REVIEW_STATUSES
            ):
                objection_statuses[objection_id] = (severity, status)
                if severity == "BLOCKING" and status != "RESOLVED":
                    blocking_objections.append((objection_id, status))
            affected = objection.get("affected_claim_ids", [])
            if not isinstance(affected, list):
                errors.append(f"{path}.affected_claim_ids must be a list; got {type(affected).__name__}")
            else:
                claim_ids = evidence_ids | question_ids | hypothesis_ids
                if not affected:
                    errors.append(f"{path}.affected_claim_ids must contain at least one local claim ID")
                for claim_id in affected:
                    if not isinstance(claim_id, str) or not claim_id.strip():
                        errors.append(
                            f"{path}.affected_claim_ids entries must be non-empty local ID strings"
                        )
                    elif claim_id not in claim_ids:
                        errors.append(f"{path} references unknown affected claim {claim_id}")
            if not objection.get("objection"):
                warnings.append(f"{path}.objection is not recorded")
            if not objection.get("evidence_dependency"):
                warnings.append(f"{path}.evidence_dependency is not recorded")
        blockers_value = review.get("unresolved_blockers")
        if blockers_value is not None and not isinstance(blockers_value, list):
            errors.append(
                "adversarial_review.unresolved_blockers must be a list; "
                f"got {type(blockers_value).__name__}"
            )
        elif isinstance(blockers_value, list):
            blockers = blockers_value
            for index, blocker in enumerate(blockers):
                if isinstance(blocker, str) and blocker.strip():
                    continue
                if isinstance(blocker, dict) and any(
                    isinstance(blocker.get(field), str) and blocker[field].strip()
                    for field in ("id", "text", "description")
                ):
                    continue
                errors.append(
                    "adversarial_review.unresolved_blockers"
                    f"[{index}] must be a non-empty objection ID/string or an object with id, text, or description"
                )
            summary_ids = {
                (blocker if isinstance(blocker, str) else blocker.get("id")).strip()
                for blocker in blockers
                if (
                    isinstance(blocker, str)
                    and blocker.strip()
                )
                or (
                    isinstance(blocker, dict)
                    and isinstance(blocker.get("id"), str)
                    and blocker["id"].strip()
                )
            }
            standalone_blockers = sorted(
                summary_id for summary_id in summary_ids if summary_id not in objection_statuses
            )
            standalone_blockers.extend(
                f"entry-{index}"
                for index, blocker in enumerate(blockers)
                if isinstance(blocker, dict)
                and not isinstance(blocker.get("id"), str)
                and any(
                    isinstance(blocker.get(field), str) and blocker[field].strip()
                    for field in ("text", "description")
                )
            )
            blocking_ids = {objection_id for objection_id, _ in blocking_objections}
            missing_ids = sorted(blocking_ids - summary_ids)
            stale_ids = sorted(
                objection_id
                for objection_id in summary_ids & objection_statuses.keys()
                if objection_id not in blocking_ids
            )
            if missing_ids:
                warnings.append(
                    "adversarial_review.unresolved_blockers omits non-resolved BLOCKING "
                    f"objection(s): {', '.join(missing_ids)}"
                )
            if stale_ids:
                warnings.append(
                    "adversarial_review.unresolved_blockers includes resolved or non-BLOCKING "
                    f"objection(s): {', '.join(stale_ids)}"
                )
    if value.get("status") == "frozen":
        if not questions or not hypotheses:
            errors.append("frozen brief needs at least one question and hypothesis")
        for objection_id, status in blocking_objections:
            errors.append(
                "frozen brief has non-resolved BLOCKING objection "
                f"{objection_id} with status {status}"
            )
        if standalone_blockers:
            errors.append(
                "frozen brief has standalone unresolved blocker summary entries: "
                f"{', '.join(standalone_blockers)}"
            )
        if not value.get("approval"):
            errors.append("frozen brief needs approval evidence")
    if not value.get("gap"):
        warnings.append("gap is not recorded")
    if not value.get("research_object"):
        warnings.append("research object is not recorded")
    return errors, warnings


def fixture() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "brief_id": "brief-1",
        "version": 1,
        "status": "draft",
        "purpose": "Explore a bounded relation",
        "evidence_input": {"kind": "equivalent_input", "note": "reviewed note"},
        "evidence_statements": [{"id": "E1", "text": "A bounded observation."}],
        "gap": {"missing_connection": "relation unresolved"},
        "research_object": {"unit": "observation"},
        "questions": [{"id": "Q1", "question": "Is A related to B?", "observables": ["A", "B"]}],
        "hypotheses": [{"id": "H1", "statement": "Under C, A relates to B.", "prior_evidence_ids": ["E1"], "falsifiers": ["No relation"], "depends_on": ["Q1"]}],
        "adversarial_review": {"unresolved_blockers": []},
    }


def self_test() -> None:
    assert validate(fixture()) == ([], [])
    partial = fixture()
    partial["hypotheses"][0]["falsifiers"] = []
    assert validate(partial)[0] == [] and any("falsifier" in warning for warning in validate(partial)[1])
    broken = fixture()
    broken["hypotheses"][0]["prior_evidence_ids"] = ["missing"]
    assert any("unknown evidence" in error for error in validate(broken)[0])
    question_dependency = fixture()
    question_dependency["questions"][0]["depends_on"] = ["E1"]
    assert validate(question_dependency) == ([], [])
    unknown_question_dependency = fixture()
    unknown_question_dependency["questions"][0]["depends_on"] = ["outside-brief"]
    assert any(
        "questions[0] references unknown dependency outside-brief" in error
        for error in validate(unknown_question_dependency)[0]
    )
    self_question_dependency = fixture()
    self_question_dependency["questions"][0]["depends_on"] = ["Q1"]
    assert any("cannot depend on itself" in error for error in validate(self_question_dependency)[0])
    invalid_question_dependency = fixture()
    invalid_question_dependency["questions"][0]["depends_on"] = [{"id": "E1"}]
    assert any(
        "depends_on entries must be non-empty local ID strings" in error
        for error in validate(invalid_question_dependency)[0]
    )
    duplicate_namespace = fixture()
    duplicate_namespace["questions"][0]["id"] = "E1"
    assert any("reused across evidence and question" in error for error in validate(duplicate_namespace)[0])
    question_cycle = fixture()
    question_cycle["questions"] = [
        {"id": "Q1", "question": "First?", "observables": ["x"], "depends_on": ["Q2"]},
        {"id": "Q2", "question": "Second?", "observables": ["y"], "depends_on": ["Q1"]},
    ]
    assert any("question dependency cycle" in error for error in validate(question_cycle)[0])
    hypothesis_cycle = fixture()
    hypothesis_cycle["hypotheses"] = [
        {"id": "H1", "statement": "One", "prior_evidence_ids": ["E1"], "falsifiers": ["x"], "depends_on": ["H2"]},
        {"id": "H2", "statement": "Two", "prior_evidence_ids": ["E1"], "falsifiers": ["y"], "depends_on": ["H1"]},
    ]
    assert any("hypothesis dependency cycle" in error for error in validate(hypothesis_cycle)[0])
    missing_text = fixture()
    missing_text["evidence_statements"][0].pop("text")
    assert any(
        "evidence_statements[0].text is required" in error for error in validate(missing_text)[0]
    )
    bad_review = fixture()
    bad_review["adversarial_review"] = []
    assert any("adversarial_review must be an object" in error for error in validate(bad_review)[0])
    bad_objection = fixture()
    bad_objection["adversarial_review"] = {
        "objections": [
            {
                "id": "O1",
                "affected_claim_ids": ["H1"],
                "objection": "A material challenge",
                "evidence_dependency": "E1",
                "severity": "HIGH",
                "status": "OPEN",
            }
        ],
        "unresolved_blockers": [],
    }
    assert any(
        "BLOCKING, NARROWING, INFORMATIVE" in error and "HIGH" in error
        for error in validate(bad_objection)[0]
    )
    unknown_affected_claim = fixture()
    unknown_affected_claim["adversarial_review"] = {
        "objections": [
            {
                "id": "O1",
                "affected_claim_ids": ["outside-brief"],
                "objection": "A material challenge",
                "evidence_dependency": "E1",
                "severity": "NARROWING",
                "status": "OPEN",
            }
        ]
    }
    assert any(
        "references unknown affected claim outside-brief" in error
        for error in validate(unknown_affected_claim)[0]
    )
    missing_affected_claim = fixture()
    missing_affected_claim["adversarial_review"] = {
        "objections": [
            {
                "id": "O1",
                "objection": "A material challenge",
                "evidence_dependency": "E1",
                "severity": "INFORMATIVE",
                "status": "OPEN",
            }
        ]
    }
    assert any(
        "affected_claim_ids must contain at least one" in error
        for error in validate(missing_affected_claim)[0]
    )
    bad_blocker = fixture()
    bad_blocker["adversarial_review"]["unresolved_blockers"] = [0]
    assert any(
        "unresolved_blockers[0]" in error for error in validate(bad_blocker)[0]
    )
    frozen_open_blocker = fixture()
    frozen_open_blocker["status"] = "frozen"
    frozen_open_blocker["approval"] = {"approved_by": "review-role"}
    frozen_open_blocker["adversarial_review"] = {
        "objections": [
            {
                "id": "O1",
                "affected_claim_ids": ["H1"],
                "objection": "A material challenge",
                "evidence_dependency": "E1",
                "severity": "BLOCKING",
                "status": "OPEN",
            }
        ],
        "unresolved_blockers": [],
    }
    blocker_errors, blocker_warnings = validate(frozen_open_blocker)
    assert any(
        "non-resolved BLOCKING objection O1 with status OPEN" in error
        for error in blocker_errors
    )
    assert any("omits non-resolved BLOCKING" in warning for warning in blocker_warnings)
    accepted_risk_blocker = json.loads(json.dumps(frozen_open_blocker))
    accepted_risk_blocker["adversarial_review"]["objections"][0]["status"] = "ACCEPTED_RISK"
    assert any(
        "with status ACCEPTED_RISK" in error for error in validate(accepted_risk_blocker)[0]
    )
    resolved_blocker = json.loads(json.dumps(frozen_open_blocker))
    resolved_blocker["adversarial_review"]["objections"][0]["status"] = "RESOLVED"
    resolved_blocker["adversarial_review"]["unresolved_blockers"] = ["O1"]
    resolved_errors, resolved_warnings = validate(resolved_blocker)
    assert resolved_errors == []
    assert any("resolved or non-BLOCKING" in warning for warning in resolved_warnings)
    standalone_blocker = fixture()
    standalone_blocker["status"] = "frozen"
    standalone_blocker["approval"] = {"approved_by": "review-role"}
    standalone_blocker["adversarial_review"] = {
        "objections": [],
        "unresolved_blockers": ["summary-blocker"],
    }
    assert any(
        "standalone unresolved blocker" in error
        for error in validate(standalone_blocker)[0]
    )
    print("self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("brief", nargs="?", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.brief is None:
        parser.error("brief is required unless --self-test is used")
    try:
        value = json.loads(args.brief.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"ERROR: invalid JSON: {exc}")
        return 2
    errors, warnings = validate(value)
    for warning in warnings:
        print(f"WARNING: {warning}")
    for error in errors:
        print(f"ERROR: {error}")
    if errors:
        return 1
    print("hypothesis brief: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
