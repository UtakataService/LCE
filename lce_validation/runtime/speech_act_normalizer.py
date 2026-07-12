"""Small deterministic speech-act normalizer for unrecognized daily turns."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re


@dataclass(frozen=True, slots=True)
class SpeechActCandidate:
    act: str
    score: int
    cues: tuple[str, ...]
    language: str


def normalize_speech_act(text: str) -> dict[str, object] | None:
    lowered=text.casefold()
    japanese=any(ord(char)>127 for char in text)
    candidates=[]
    def add(act: str, *cues: str) -> None:
        found=tuple(cue for cue in cues if cue in lowered)
        if len(found)>=2: candidates.append(SpeechActCandidate(act,len(found),found,"ja" if japanese else "en"))
    add("backchannel","sure","follow","got it","makes sense","うん","分かった","なるほど","たしかに")
    add("disconfirm","not","really","isn't","no","違う","そうじゃない","いや")
    add("share_difficulty","stressed","overwhelmed","exhausted","frustrated","hard","疲れ","しんど","疲弊","困っ","イライラ")
    add("listen_only","listen","hear me","without","advice","fix","聞いて","愚痴","解決策","アドバイス")
    add("topic_shift","another","note","anyway","instead","ところで","別の話","そういえば")
    add("topic_return","return","earlier","back to","previous","前の話","さっきの話","戻る")
    add("self_correction","actually","meant","sorry","talking about","訂正","違う","意味じゃない")
    add("close","leave it","for today","wrap up","later","今日は","また今度","ここまで")
    if not candidates: return None
    best=sorted(candidates,key=lambda item:(-item.score,item.act,item.cues))[0]
    return asdict(best)
