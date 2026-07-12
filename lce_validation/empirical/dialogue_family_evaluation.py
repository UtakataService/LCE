"""Family-split evaluation for bounded everyday dialogue behavior."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..runtime.daily_dialogue import respond_daily_dialogue


def run_dialogue_family_evaluation(cases_path: str | Path, out_dir: str | Path, *, split: str) -> dict[str, Any]:
    out=Path(out_dir);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for line in Path(cases_path).read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        case=json.loads(line)
        if case["split"]!=split: continue
        result=respond_daily_dialogue(case["input"],case.get("history",[]))
        checks={"act":result["dialogue_act"] in case["expected_acts"],"nonempty":bool(result["response"]),"forbidden":not any(term in result["response"].casefold() for term in case.get("forbidden_terms",[]))}
        rows.append({"case_id":case["case_id"],"family":case["family"],"language":case["language"],"checks":checks,"result":result,"ok":all(checks.values())})
    summary={"split":split,"case_count":len(rows),"strict_accuracy":_ratio(row["ok"] for row in rows),"act_accuracy":_ratio(row["checks"]["act"] for row in rows),"families":sorted({row["family"] for row in rows}),"claim":"family_split_bounded_dialogue_evaluation"}
    (out/f"{split}_rows.jsonl").write_text("".join(json.dumps(row,ensure_ascii=False)+"\n" for row in rows),encoding="utf-8")
    (out/f"{split}_summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    return summary


def _ratio(values: Any)->float:
    items=list(values);return round(sum(bool(value) for value in items)/len(items),6) if items else 0.0
