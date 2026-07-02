from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import re
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data" / "raw_expected_qa.json"
DEFAULT_REPORT = ROOT / "data" / "raw_qa_accuracy_report.json"
DEFAULT_CSV = ROOT / "data" / "raw_qa_accuracy_results.csv"
GRAPH_PATH = ROOT / "src" / "core" / "graph_test2.py"


def load_graph_module():
    sys.path.insert(0, str(GRAPH_PATH.parent))
    spec = importlib.util.spec_from_file_location("graph_test2_eval_target", GRAPH_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {GRAPH_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def keyword_score(answer: str, expected_keywords: list[str]) -> tuple[float, list[str]]:
    answer_norm = normalize(answer)
    keywords = [kw for kw in expected_keywords if kw]
    if not keywords:
        return 0.0, []
    hits = [kw for kw in keywords if normalize(kw) in answer_norm]
    return round(len(hits) / len(keywords), 4), hits


def answer_length_score(answer: str) -> float:
    text = normalize(answer)
    if not text:
        return 0.0
    if "관련 내용을 명확히 확인할 수 없습니다" in text and len(text) < 260:
        return 0.2
    return 1.0 if len(text) >= 120 else round(len(text) / 120, 4)


def deterministic_score(answer: str, item: dict[str, Any]) -> dict[str, Any]:
    kw_score, hits = keyword_score(answer, item.get("expected_keywords", []))
    len_score = answer_length_score(answer)
    score = round((kw_score * 0.75) + (len_score * 0.25), 4)
    return {
        "score": score,
        "keyword_recall": kw_score,
        "length_score": len_score,
        "keyword_hits": hits,
        "passed": score >= 0.6,
    }


def llm_judge(graph_module: Any, answer: str, item: dict[str, Any]) -> dict[str, Any]:
    prompt = f"""
당신은 전월세 법률 RAG 답변 평가자입니다. 기대답변은 data/01_raw 원천 근거에서 만든 기준 답변입니다.
모델답변이 질문에 대해 기대답변의 핵심 법률/실무 의미를 충실히 담았는지 평가하세요.

점수 기준:
- 1.0: 핵심 결론과 조치가 대부분 일치하고 근거 없는 위험한 단정이 없음
- 0.7: 대체로 맞지만 일부 핵심 조건/절차가 빠짐
- 0.4: 관련은 있으나 질문 해결에 부족함
- 0.0: 틀리거나 무관함

JSON만 출력하세요. keys: score(float), passed(bool), reason(str)

[stage] {item.get("stage")}
[question] {item.get("question")}
[expected_answer] {item.get("expected_answer")}
[model_answer] {answer}
"""
    try:
        judged = graph_module._llm_json(prompt)
    except Exception as exc:
        return {"score": None, "passed": None, "reason": f"judge_error: {exc}"}
    score = judged.get("score")
    try:
        score = round(float(score), 4)
    except (TypeError, ValueError):
        score = None
    return {
        "score": score,
        "passed": bool(judged.get("passed")) if score is not None else None,
        "reason": judged.get("reason", ""),
    }


def select_items(items: list[dict[str, Any]], limit: int | None, stage: str | None) -> list[dict[str, Any]]:
    selected = [item for item in items if stage is None or item.get("stage") == stage]
    if limit is not None:
        selected = selected[:limit]
    return selected


def summarize(results: list[dict[str, Any]], score_key: str) -> dict[str, Any]:
    scored = [r for r in results if isinstance(r.get(score_key), (int, float))]
    if not scored:
        return {"count": 0, "accuracy": None, "average_score": None}
    passed = [r for r in scored if r.get(f"{score_key}_passed")]
    avg = sum(float(r[score_key]) for r in scored) / len(scored)
    return {
        "count": len(scored),
        "passed": len(passed),
        "accuracy": round(len(passed) / len(scored), 4),
        "average_score": round(avg, 4),
    }


def write_csv(path: Path, results: list[dict[str, Any]]) -> None:
    fields = [
        "id",
        "source_file",
        "stage",
        "topic",
        "question",
        "expected_answer",
        "answer",
        "deterministic_score",
        "deterministic_score_passed",
        "keyword_recall",
        "keyword_hits",
        "llm_score",
        "llm_score_passed",
        "llm_reason",
        "error",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in results:
            writer.writerow({key: row.get(key, "") for key in fields})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    parser.add_argument("--limit", type=int, default=None, help="평가할 문항 수 제한")
    parser.add_argument("--stage", choices=["pre", "post"], default=None)
    parser.add_argument("--llm-judge", action="store_true", help="OpenAI LLM으로 의미 일치도도 평가")
    parser.add_argument("--sleep", type=float, default=0.0, help="문항 사이 대기 시간")
    args = parser.parse_args()

    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    items = select_items(dataset["items"], args.limit, args.stage)
    graph_module = load_graph_module()

    results = []
    for idx, item in enumerate(items, start=1):
        print(f"[{idx}/{len(items)}] {item['stage']} {item['id']}")
        result = {
            "id": item["id"],
            "source_file": item["source_file"],
            "stage": item["stage"],
            "topic": item["topic"],
            "question": item["question"],
            "expected_answer": item["expected_answer"],
            "expected_keywords": item.get("expected_keywords", []),
        }
        try:
            answer = graph_module.run_turn(
                thread_id=f"eval-{item['id']}",
                question=item["question"],
                stage=item["stage"],
                has_document=False,
            )
            result["answer"] = answer
            det = deterministic_score(answer, item)
            result.update(
                {
                    "deterministic_score": det["score"],
                    "deterministic_score_passed": det["passed"],
                    "keyword_recall": det["keyword_recall"],
                    "length_score": det["length_score"],
                    "keyword_hits": det["keyword_hits"],
                }
            )
            if args.llm_judge:
                judged = llm_judge(graph_module, answer, item)
                result.update(
                    {
                        "llm_score": judged["score"],
                        "llm_score_passed": judged["passed"],
                        "llm_reason": judged["reason"],
                    }
                )
        except Exception as exc:
            result["error"] = repr(exc)
            result["answer"] = ""
            result["deterministic_score"] = 0.0
            result["deterministic_score_passed"] = False
        results.append(result)
        if args.sleep:
            time.sleep(args.sleep)

    report = {
        "dataset": str(args.dataset.relative_to(ROOT) if args.dataset.is_relative_to(ROOT) else args.dataset),
        "graph": str(GRAPH_PATH.relative_to(ROOT)),
        "evaluated_count": len(results),
        "deterministic": summarize(results, "deterministic_score"),
        "llm_judge": summarize(results, "llm_score") if args.llm_judge else None,
        "by_stage": {},
        "results": results,
    }
    for stage in ["pre", "post"]:
        stage_results = [r for r in results if r["stage"] == stage]
        report["by_stage"][stage] = {
            "deterministic": summarize(stage_results, "deterministic_score"),
            "llm_judge": summarize(stage_results, "llm_score") if args.llm_judge else None,
        }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(args.csv, results)
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
