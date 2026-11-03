"""Pure Python teacher-answer checks, shared by local ranking and cloud collection."""

import re
from decimal import Decimal


def numeric_answer(text: str) -> Decimal | None:
    text = text.strip().replace("−", "-")
    if not re.fullmatch(r"[+-]?(?:(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d*)?|\.\d+)", text):
        return None
    return Decimal(text.replace(",", ""))


def teacher_eligible(row: dict) -> tuple[bool, str]:
    if row.get("finish_reason") in {"length", "abort"}:
        return False, "generation_truncated"
    response = row.get("response")
    if not isinstance(response, str) or not response.strip():
        return False, "missing_teacher_response"
    if "deepseek" not in str(row.get("teacher_model", "")).casefold():
        return False, "missing_deepseek_provenance"
    if not isinstance(row.get("teacher_revision"), str) or not row["teacher_revision"].strip():
        return False, "missing_teacher_revision"
    generation = row.get("generation")
    if not isinstance(generation, dict) or not generation.get("prompt_version") or not isinstance(generation.get("settings"), dict):
        return False, "missing_generation_provenance"
    if "####" not in response:
        return False, "missing_final_answer_marker"
    solution, final = response.rsplit("####", 1)
    if not solution.strip():
        return False, "missing_teacher_solution"
    predicted = numeric_answer(final.strip())
    gold = numeric_answer(str(row.get("gold_answer", "")))
    if gold is None:
        return False, "invalid_gold_answer"
    if predicted is None:
        return False, "unparsed_teacher_final_answer"
    if predicted != gold:
        return False, "incorrect_teacher_final_answer"
    return True, "verified_final_answer"
