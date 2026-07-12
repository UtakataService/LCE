"""Quality-gated SHADOW knowledge pilot and deterministic pre/post benchmark."""
from dataclasses import dataclass
import re
from .data_quality import DataQualityEvaluator, RawEvidence

@dataclass(frozen=True, slots=True)
class PilotRow:
    evidence: RawEvidence
    question: str
    answer: str
    topic: str

class ShadowKnowledgePilot:
    def __init__(self, evaluator: DataQualityEvaluator | None = None):
        self.evaluator=evaluator or DataQualityEvaluator(); self._rows=[]
    def ingest(self, rows):
        accepted=[]; rejected=[]
        for row in rows:
            report=self.evaluator.evaluate(row.evidence)
            (accepted if report.candidate_eligible else rejected).append((row,report))
        self._rows.extend(row for row,_ in accepted)
        return accepted,rejected
    @staticmethod
    def _terms(text):
        normalized=text.lower()
        words=set(re.findall(r"[a-z0-9_]+",normalized))
        cjk="".join(re.findall(r"[\u3040-\u30ff\u3400-\u9fff]",normalized))
        return words | {cjk[i:i+2] for i in range(max(0,len(cjk)-1))}
    def answer(self, question):
        q=self._terms(question); scored=[(len(q & self._terms(r.question)),r) for r in self._rows]
        score,row=max(scored,default=(0,None),key=lambda x:x[0])
        return {"answer": row.answer, "evidence_id": row.evidence.evidence_id, "abstained":False} if score>=2 else {"answer":None,"evidence_id":None,"abstained":True}

def benchmark(engine, cases):
    correct=abstained=0; by_language={}
    for language,question,expected in cases:
        out=engine.answer(question); ok=(out["answer"]==expected) if expected is not None else out["abstained"]
        correct+=int(ok); abstained+=int(out["abstained"]); by_language.setdefault(language,[0,0]); by_language[language][0]+=int(ok); by_language[language][1]+=1
    return {"total":len(cases),"correct":correct,"accuracy":correct/len(cases),"abstained":abstained,
            "by_language":{k:{"correct":v[0],"total":v[1]} for k,v in by_language.items()}}
