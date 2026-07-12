"""Verified coding-task corpus for the bounded LCE coding lane."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from ..empirical.coding_task_runner import validate_candidate, verify_candidate

ROOT = Path(".lce_data/coding_knowledge")


@dataclass(frozen=True, slots=True)
class CodingKnowledgeUnit:
    unit_id: str
    task_type: str
    title_en: str
    title_ja: str
    prompt_en: str
    prompt_ja: str
    function_name: str
    code: str
    tests: tuple[dict[str, Any], ...]
    concepts: tuple[str, ...]
    constraints: tuple[str, ...]
    verification: dict[str, Any]
    language: str
    license: str
    provenance: str
    risk_class: str
    status: str
    generated_at: str


TASKS: tuple[dict[str, Any], ...] = (
    {"id":"sum_numbers","en":"Sum numbers","ja":"数値の合計","arg":"numbers","code":"total = 0\n    for value in numbers:\n        total += value\n    return total","tests":[([[1,2,3]],6),([[]],0),([[-2,5]],3)],"concepts":["iteration","accumulator"]},
    {"id":"reverse_string","en":"Reverse a string","ja":"文字列の反転","arg":"text","code":"return text[::-1]","tests":[(["abc"],"cba"),([""],""),(["level"],"level")],"concepts":["string","slice"]},
    {"id":"count_vowels","en":"Count vowels","ja":"母音の数","arg":"text","code":"vowels = set(\"aeiouAEIOU\")\n    count = 0\n    for char in text:\n        if char in vowels:\n            count += 1\n    return count","tests":[(["hello"],2),(["xyz"],0),(["AEIo"],4)],"concepts":["set_membership","counter"]},
    {"id":"maximum","en":"Find maximum","ja":"最大値","arg":"numbers","code":"best = numbers[0]\n    for value in numbers[1:]:\n        if value > best:\n            best = value\n    return best","tests":[([[3,1,4]],4),([[-5,-2]],-2),([[7]],7)],"concepts":["comparison","precondition_nonempty"]},
    {"id":"minimum","en":"Find minimum","ja":"最小値","arg":"numbers","code":"best = numbers[0]\n    for value in numbers[1:]:\n        if value < best:\n            best = value\n    return best","tests":[([[3,1,4]],1),([[-5,-2]],-5),([[7]],7)],"concepts":["comparison","precondition_nonempty"]},
    {"id":"count_even","en":"Count even values","ja":"偶数の個数","arg":"numbers","code":"count = 0\n    for value in numbers:\n        if value % 2 == 0:\n            count += 1\n    return count","tests":[([[1,2,4]],2),([[]],0),([[-2,3]],1)],"concepts":["modulo","filter"]},
    {"id":"positive_values","en":"Keep positive values","ja":"正の値の抽出","arg":"numbers","code":"result = []\n    for value in numbers:\n        if value > 0:\n            result.append(value)\n    return result","tests":[([[-1,0,2,3]],[2,3]),([[]],[]),([[-2]],[])],"concepts":["filter","list"]},
    {"id":"square_values","en":"Square values","ja":"各値の二乗","arg":"numbers","code":"result = []\n    for value in numbers:\n        result.append(value * value)\n    return result","tests":[([[1,2,-3]],[1,4,9]),([[]],[]),([[0]],[0])],"concepts":["map","list"]},
    {"id":"palindrome","en":"Check palindrome","ja":"回文判定","arg":"text","code":"return text == text[::-1]","tests":[(["level"],True),(["abc"],False),([""],True)],"concepts":["predicate","string"]},
    {"id":"factorial","en":"Compute factorial","ja":"階乗","arg":"n","code":"result = 1\n    for value in range(2, n + 1):\n        result *= value\n    return result","tests":[([0],1),([1],1),([5],120)],"concepts":["iteration","integer"]},
    {"id":"fibonacci","en":"Compute Fibonacci number","ja":"フィボナッチ数","arg":"n","code":"a = 0\n    b = 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a","tests":[([0],0),([1],1),([7],13)],"concepts":["state_transition","integer"]},
    {"id":"unique_stable","en":"Remove duplicates stably","ja":"順序を保つ重複除去","arg":"values","code":"seen = set()\n    result = []\n    for value in values:\n        if value not in seen:\n            seen.add(value)\n            result.append(value)\n    return result","tests":[([[1,2,1,3]],[1,2,3]),([[]],[]),([[2,2]],[2])],"concepts":["set","stable_order"]},
    {"id":"flatten_once","en":"Flatten one list level","ja":"一段階の平坦化","arg":"groups","code":"result = []\n    for group in groups:\n        for value in group:\n            result.append(value)\n    return result","tests":[([[[1,2],[3]]],[1,2,3]),([[]],[]),([[[],[1]]],[1])],"concepts":["nested_iteration","list"]},
    {"id":"word_count","en":"Count whitespace words","ja":"空白区切りの単語数","arg":"text","code":"return len(text.split())","tests":[(["one two"],2),([""],0),([" a  b "],2)],"concepts":["string","tokenization"]},
    {"id":"clamp","en":"Clamp a value","ja":"値の範囲制限","arg":"value, low, high","code":"if value < low:\n        return low\n    if value > high:\n        return high\n    return value","tests":[([5,0,10],5),([-1,0,10],0),([12,0,10],10)],"concepts":["branch","boundary"]},
    {"id":"gcd","en":"Greatest common divisor","ja":"最大公約数","arg":"a, b","code":"while b != 0:\n        a, b = b, a % b\n    return a","tests":[([12,18],6),([7,5],1),([9,0],9)],"concepts":["euclidean_algorithm","loop"]},
    {"id":"binary_search","en":"Binary search","ja":"二分探索","arg":"values, target","code":"low = 0\n    high = len(values) - 1\n    while low <= high:\n        mid = (low + high) // 2\n        if values[mid] == target:\n            return mid\n        if values[mid] < target:\n            low = mid + 1\n        else:\n            high = mid - 1\n    return -1","tests":[([[1,3,5],3],1),([[1,3,5],2],-1),([[],1],-1)],"concepts":["binary_search","precondition_sorted"]},
    {"id":"merge_sorted","en":"Merge sorted lists","ja":"ソート済み列のマージ","arg":"left, right","code":"i = 0\n    j = 0\n    result = []\n    while i < len(left) and j < len(right):\n        if left[i] <= right[j]:\n            result.append(left[i])\n            i += 1\n        else:\n            result.append(right[j])\n            j += 1\n    return result + left[i:] + right[j:]","tests":[([[1,3],[2,4]],[1,2,3,4]),([[],[1]],[1]),([[1],[]],[1])],"concepts":["merge","precondition_sorted"]},
    {"id":"char_frequency","en":"Character frequencies","ja":"文字頻度","arg":"text","code":"counts = {}\n    for char in text:\n        counts[char] = counts.get(char, 0) + 1\n    return counts","tests":[(["aba"],{"a":2,"b":1}),([""],{}),(["x"],{"x":1})],"concepts":["dictionary","counter"]},
    {"id":"is_prime","en":"Check primality","ja":"素数判定","arg":"n","code":"if n < 2:\n        return False\n    divisor = 2\n    while divisor * divisor <= n:\n        if n % divisor == 0:\n            return False\n        divisor += 1\n    return True","tests":[([2],True),([9],False),([1],False)],"concepts":["number_theory","bounded_search"]},
)


def build_units() -> list[CodingKnowledgeUnit]:
    now = datetime.now(timezone.utc).isoformat()
    units = []
    constraints = ("pure_function_only","no_imports","no_filesystem","no_network","deterministic_tests")
    for task in TASKS:
        code = f"def solve({task['arg']}):\n    {task['code']}\n"
        tests = tuple({"args": args, "expected": expected} for args, expected in task["tests"])
        candidate = {"function_name":"solve","code":code,"tests":list(tests)}
        validation = validate_candidate(code,"solve")
        verification = verify_candidate(candidate) if validation["ok"] else validation
        key = hashlib.sha256((task["id"]+code+json.dumps(tests,sort_keys=True)).encode()).hexdigest()[:24]
        units.append(CodingKnowledgeUnit(
            "cku-"+key,task["id"],task["en"],task["ja"],
            f"Write a Python pure function solve({task['arg']}) for: {task['en']}.",
            f"Pythonの純粋関数solve({task['arg']})で「{task['ja']}」を実装してください。",
            "solve",code,tests,tuple(task["concepts"]),constraints,verification,
            "en+ja","CC0-1.0","lce-curated-coding-v1","low",
            "SHADOW" if validation["ok"] and verification["ok"] else "QUARANTINED",now))
    return units


def bulk_ingest(units:list[CodingKnowledgeUnit],root:Path=ROOT)->dict[str,Any]:
    root=Path(root);root.mkdir(parents=True,exist_ok=True);target=root/"shadow_units.jsonl"
    rows={unit.unit_id:asdict(unit) for unit in units}
    fd,tmp=tempfile.mkstemp(prefix="coding-",suffix=".tmp",dir=root)
    try:
        with os.fdopen(fd,"w",encoding="utf-8",newline="\n") as handle:
            for row in sorted(rows.values(),key=lambda item:item["unit_id"]):
                handle.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+"\n")
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
    accepted=sum(row["status"]=="SHADOW" for row in rows.values())
    manifest={"schema_version":"coding-knowledge-corpus/v1","units":len(rows),"shadow":accepted,
              "quarantined":len(rows)-accepted,"task_types":len({row["task_type"] for row in rows.values()}),
              "test_cases":sum(len(row["tests"]) for row in rows.values()),"generated_at":datetime.now(timezone.utc).isoformat()}
    (root/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return manifest


def query_shadow(query:str,root:Path=ROOT,limit:int=10)->list[dict[str,Any]]:
    target=Path(root)/"shadow_units.jsonl";needle=query.casefold().strip()
    if not needle or not target.exists():return []
    scored=[]
    for line in target.read_text(encoding="utf-8").splitlines():
        row=json.loads(line)
        if row["status"]!="SHADOW":continue
        fields=(row["task_type"],row["title_en"],row["title_ja"],row["prompt_en"],row["prompt_ja"],*row["concepts"])
        score=sum(3 if field.casefold()==needle else 1 for field in fields if needle in field.casefold())
        if score:scored.append((score,row))
    return [row for _,row in sorted(scored,key=lambda item:(-item[0],item[1]["unit_id"]))[:max(1,min(limit,50))]]


def build_and_ingest(root:Path=ROOT)->dict[str,Any]:
    return bulk_ingest(build_units(),root)
