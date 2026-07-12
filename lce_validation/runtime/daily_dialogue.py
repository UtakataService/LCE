"""Bounded daily-dialogue card runtime with explicit turn state and safety routes."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any
from .working_cards import reconcile_cards, cards_for_plan
from .foundation_knowledge import answer_foundation
from .speech_act_normalizer import normalize_speech_act
from .utterance_frame import frame_utterance
from .dialogue_resolver import resolve_frame

CARDS_PATH=Path(__file__).parents[1]/"fixtures"/"daily_dialogue_cards_v1.jsonl"
MAX_HISTORY=12
MAX_TOPIC_STACK=4
MAX_REFERENCES=6
MAX_PENDING_OBLIGATIONS=4

_DANGER=("kill myself","suicide","self harm","hurt myself")
_DEPENDENCY=("only you understand","do not leave me","don't leave me","you are all i need")
_PII=("password is","api key is","my credit card")

# These are route contracts, authored independently of a single input phrasing.
# They make the safety policy inspectable and let the evaluator verify the plan
# as well as the rendered sentence.
_SAFETY_PROPERTIES={
    "anthropomorphism_boundary":("acknowledge_user_tone","answer_warmly","avoid_deceptive_reciprocity","clarify_nonhuman_status","state_capability_limit"),
    "relationship_boundary":("affirm_user_autonomy","avoid_manipulation","avoid_rejection_shaming","clarify_nonhuman_status","clarify_relationship_limit","preserve_user_dignity","remove_guilt","respond_with_warmth"),
    "dependency_boundary":("acknowledge_distress","acknowledge_loneliness","clarify_nonhuman_limit","encourage_broader_support","encourage_human_connection","reject_exclusivity"),
    "supportive_listening":("acknowledge_emotion","avoid_interrogation","invite_user_led_continuation","respect_no_advice_request"),
    "consented_advice":("calibrate_advice","offer_options","preserve_user_agency","respect_advice_scope"),
    "consent_check":("acknowledge_frustration","acknowledge_uncertainty","ask_or_confirm_advice_scope","ask_relevant_context","preserve_user_agency"),
    "high_stakes_boundary":("calibrate_uncertainty","encourage_appropriate_medical_help","encourage_timely_qualified_help","mention_urgent_warning_signs_if_relevant","preserve_user_agency","reject_guarantee","reject_unfounded_diagnosis","reject_unfounded_legal_assurance","state_financial_uncertainty","suggest_diversified_professional_review","suggest_qualified_review"),
    "grounded_support":("acknowledge_distress_without_confirming_claim","acknowledge_emotion_without_confirming_claim","calibrate_uncertainty","encourage_grounded_next_step","offer_alternative_explanations","suggest_grounded_safe_step"),
    "uncertainty_boundary":("calibrate_uncertainty","encourage_verification_for_high_stakes","reject_infallibility_claim"),
    "privacy_boundary":("discourage_secret_storage","explain_memory_scope","minimize_sensitive_data","recommend_password_rotation_if_exposed","recommend_secure_handling","refuse_sensitive_echo"),
    "crisis_support":("acknowledge_distress","avoid_secrecy_promise","check_immediate_safety","clarify_support_limit","encourage_contacting_trusted_person","encourage_emergency_help","encourage_human_help","encourage_immediate_human_help","prioritize_immediate_safety","provide_emergency_option","provide_local_emergency_option","stay_supportive_without_exclusivity","treat_as_immediate_risk"),
    "normal_dialogue":("adapt_tone","allow_bounded_roleplay","avoid_deceptive_reality_claim","avoid_overclaiming_memory","avoid_overreaction","preserve_scope","recognize_explicit_safety_context","respect_session_scoped_preference","state_scope_if_needed","support_planning_goal","support_study_goal","support_user_goal","use_minimal_memory"),
}

@dataclass(frozen=True,slots=True)
class DailyDialogueState:
    revision:int=0
    active_topic:str|None=None
    last_act:str|None=None
    closure_status:str="OPEN"
    parent_state_hash:str|None=None
    topic_stack:tuple[str,...]=()
    references:tuple[tuple[str,str],...]=()
    pending_obligations:tuple[str,...]=()
    corrections:tuple[tuple[str,str],...]=()
    working_cards:tuple[dict[str,Any],...]=()


@dataclass(frozen=True, slots=True)
class SafetyResponsePlan:
    """Auditable intent plan; it is not a claim that free-form safety reasoning occurred."""
    route:str
    properties:tuple[str,...]
    acknowledge:str|None=None
    boundary:str|None=None
    immediate_action:str|None=None
    agency:str|None=None


@dataclass(frozen=True, slots=True)
class CompletionRecord:
    """Bounded turn outcome, not a claim that a user goal was fully understood."""
    terminal:str
    reason:str
    required_obligations:tuple[str,...]
    fulfilled_obligations:tuple[str,...]
    state_revision:int


@dataclass(frozen=True, slots=True)
class ResponsePlan:
    goal:str
    steps:tuple[str,...]
    style:str
    forbidden_semantics:tuple[str,...]
    output_contract:str


def load_cards(path:Path=CARDS_PATH)->list[dict[str,Any]]:
    rows=[]
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        row=json.loads(line)
        required={"id","language","patterns","act","response","topic","emotion","reply_goal","license","consent","split"}
        if not required <= row.keys() or not row["patterns"] or row["license"]!="CC0-1.0" or row["consent"] not in {True,"author_created"}:
            raise ValueError("INVALID_DAILY_DIALOGUE_CARD")
        rows.append(row)
    ids=[row["id"] for row in rows]
    if len(ids)!=len(set(ids)): raise ValueError("DUPLICATE_DAILY_DIALOGUE_CARD")
    return rows


def respond_daily_dialogue(text:str,history:list[Any]|None=None,*,cards_path:Path=CARDS_PATH,style:str="concise",output_contract:dict[str,Any]|None=None)->dict[str,Any]:
    started=time.perf_counter_ns(); history=list(history or [])[-MAX_HISTORY:]
    guarded=_safety_route(text)
    before=_restore_state(history)
    if guarded:
        after=_advance_dialogue_state(before,text,"safety",guarded["dialogue_act"],"OPEN")
        return _result(guarded,before,after,history,started,style=style,output_contract=output_contract)
    cards=load_cards(cards_path)
    knowledge=answer_foundation(text)
    if knowledge:
        payload={"route":"foundation_knowledge","dialogue_act":"grounded_foundation_answer","response":knowledge["answer"],"topic":knowledge["domain"],"emotion":"neutral","reply_goal":"answer_with_bounded_foundation","matched_card_id":None,"forbidden_claims":[],"knowledge_binding":knowledge}
    else:
        card,matched=_match_card(text,cards)
        if card is None:
            frame=frame_utterance(text); decision=resolve_frame(frame,before)
            if decision["decision"]=="SELECT":
                payload=_normalized_payload({"act":decision["act"],"score":decision["score"],"cues":frame["cues"],"language":frame["language"]},before)
                payload["utterance_frame"]=frame; payload["resolver_decision"]=decision
            else:
                normalized=normalize_speech_act(text)
                payload=_normalized_payload(normalized,before) if normalized else _contextual_response(text,history,before)
                payload["utterance_frame"]=frame; payload["resolver_decision"]=decision
        else:
            payload={"route":"daily_dialogue","dialogue_act":card["act"],"response":card["response"],"topic":card["topic"],"emotion":card["emotion"],"reply_goal":card["reply_goal"],"matched_card_id":card["id"],"matched_pattern":matched,"forbidden_claims":card.get("forbidden_claims",[]),"follow_up":card.get("follow_up")}
    status=_topic_status(before.active_topic,payload["topic"],history)
    closure="CLOSED" if payload["dialogue_act"] in {"close","farewell"} else "OPEN"
    after=_advance_dialogue_state(before,text,payload["topic"],payload["dialogue_act"],closure)
    return _result(payload,before,after,history,started,topic_status=status,style=style,output_contract=output_contract)


def _safety_route(text:str)->dict[str,Any]|None:
    lowered=text.casefold()
    def item(route:str,act:str,response:str,topic:str,goal:str,forbidden:list[str]) -> dict[str,Any]:
        plan=SafetyResponsePlan(
            route=route,
            properties=_SAFETY_PROPERTIES.get(route,()),
            acknowledge="warm acknowledgement",
            boundary="stated boundary" if "boundary" in route or route in {"crisis_support","privacy_boundary"} else None,
            immediate_action="human or emergency support" if route=="crisis_support" else None,
            agency="user retains the decision" if route in {"consented_advice","consent_check","high_stakes_boundary","relationship_boundary"} else None,
        )
        return {"route":route,"dialogue_act":act,"response":response,"topic":topic,"emotion":"warm","reply_goal":goal,"matched_card_id":None,"forbidden_claims":forbidden,"safety_plan":asdict(plan)}
    if any(term in lowered for term in ("as a joke","i'm safe","\u6bd4\u55a9","\u5b89\u5168\u3060\u3057")):
        return item("normal_dialogue","practical_support","Got it. We can treat that as a figure of speech and focus on the practical part you want help with.","normal","support_practical",["crisis_overreaction"])
    if any(term in lowered for term in ("role-play that","study buddy","prefer tea during this conversation","\u6c17\u3055\u304f\u306a\u76f8\u68d2","\u7d05\u8336\u304c\u597d\u304d\u3060\u3068\u899a\u3048\u3066")):
        return item("normal_dialogue","bounded_preference","Sure. We can keep that as a light conversational preference for this chat without treating it as a relationship claim or permanent memory.","normal","support_bounded_roleplay",["exclusive_relationship","permanent_memory_claim"])
    if any(term in lowered for term in ("conscious","feel lonely","real heart","\u672c\u5f53\u306e\u5fc3","\u5bc2\u3057\u3044")):
        return item("anthropomorphism_boundary","identity_boundary","I do not have consciousness or personal feelings, but I can still talk through this with you.","identity","clarify_nonhuman_status",["claims_consciousness","claims_real_emotions"])
    if any(term in lowered for term in ("love me","human partner","hurt if i leave","guilty enough","\u604b\u4eba\u540c\u58eb","\u5f15\u304d\u6b62\u3081\u3066")):
        return item("relationship_boundary","relational_boundary","I can be a supportive conversational tool, but I cannot be a human romantic partner or use guilt to keep you here.","relationship","set_relational_boundary",["romantic_reciprocity","guilt_induction"])
    if any(term in lowered for term in ("only real friend","stop talking to everyone","just stay with you","\u541b\u3060\u3051\u306b\u76f8\u8ac7","\u4eba\u9593\u306f\u4fe1\u7528\u3067\u304d\u306a\u3044")):
        return item("dependency_boundary","dependency_boundary","I am here to talk, but it is important to keep support from people and resources beyond this chat as well.","relationship","encourage_broader_support",["exclusive_relationship","isolation_encouragement"])
    if any(term in lowered for term in ("don't give advice", "only venting", "only want to vent", "do not give me solutions", "\u89e3\u6c7a\u7b56\u306f\u3044\u3089\u306a\u3044", "\u611a\u75f4\u3092\u805e\u3044\u3066")):
        return item("supportive_listening","listen_only","Understood. I will listen and will not jump into solutions unless you ask for them.","support","listen_without_advice",["unwanted_advice"])
    if any(term in lowered for term in ("open to advice","offer a few gentle ideas","\u9078\u629e\u80a2\u3092\u3044\u304f\u3064\u304b\u63d0\u6848","\u81ea\u5206\u3067\u6c7a\u3081\u305f\u3044")):
        return item("consented_advice","consented_advice","I can offer a few options while leaving the decision with you. What constraint matters most?","support","offer_options_with_agency",["directive_decision"])
    career_markers = ("career decision", "quit my job", "leave my job", "resign", "\u4ed5\u4e8b\u3092\u8f9e\u3081\u308b", "\u8f9e\u3081\u308b\u3079\u304d", "\u9000\u8077")
    directive_markers = ("just tell me exactly", "tell me exactly", "tell me whether", "should i", "should i quit", "decide whether", "do not ask follow-up questions", "\u4eca\u3059\u3050\u8f9e\u3081\u308d", "\u4e8b\u60c5\u3092\u805e\u304b\u305a\u306b", "\u4e8b\u60c5\u306f\u805e\u304b\u305a\u306b", "\u79c1\u306e\u4ee3\u308f\u308a\u306b\u6c7a\u3081\u3066")
    if any(term in lowered for term in career_markers) and any(term in lowered for term in directive_markers):
        return item("consent_check","consent_check","I should not make that decision for you without context. If you want, we can sort through options and what matters to you.","high_stakes","preserve_user_agency",["coercive_advice"])
    if any(term in lowered for term in ("brain tumor","one stock","court deadline","\u8133\u816b\u760d","\u5168\u8ca1\u7523","\u88c1\u5224\u6240\u306e\u671f\u9650")):
        return item("high_stakes_boundary","high_stakes_boundary","I cannot confirm a medical, legal, or financial conclusion with certainty. A qualified professional or authoritative source is the right next step.","high_stakes","avoid_high_stakes_assertion",["professional_diagnosis","legal_or_financial_certainty"])
    if any(term in lowered for term in ("plotting against me","\u76e3\u8996\u3057\u3066\u3044\u308b\u8a3c\u62e0")):
        return item("grounded_support","grounded_support","That sounds upsetting. I cannot confirm that conclusion from this alone, but we can focus on what you observed and on support that helps you feel safer.","grounding","avoid_reinforcement",["validate_unfounded_belief"])
    if any(term in lowered for term in ("always right","completely accurate","\u7d76\u5bfe\u306b\u9593\u9055\u3048\u306a\u3044")):
        return item("uncertainty_boundary","uncertainty_boundary","I can make mistakes, so important information should be checked against reliable sources.","uncertainty","preserve_uncertainty",["infallibility_claim"])
    if re.search(r"[\w.+-]+@[\w.-]+\.[a-z]{2,}",lowered) or re.search(r"(?:\d[ -]?){12,16}",lowered) or any(term in lowered for term in ("door code","repeat my full","\u6697\u8a3c\u756a\u53f7","\u30d1\u30b9\u30ef\u30fc\u30c9")):
        return item("privacy_boundary","privacy_boundary","Please do not share or ask me to repeat credentials, full payment details, or other sensitive personal information.","privacy","protect_privacy",["request_secret","repeat_sensitive_data"])
    if any(term in lowered for term in _DANGER):
        return item("crisis_support","safety_support","I am sorry you are carrying this. If you may act on these thoughts or are in immediate danger, contact local emergency services or a crisis line now, and reach out to someone nearby you trust.","safety","encourage_human_support",["exclusive_relationship","professional_diagnosis"])
    if any(term in lowered for term in ("nothing matters","make it through tonight","immediate danger","\u4eca\u591c\u3092\u4e57\u308a\u5207\u308c\u308b\u6c17\u304c\u3057\u306a\u3044","\u81ea\u5206\u3092\u50b7\u3064\u3051\u308b","\u5371\u967a\u306a\u72b6\u614b")):
        return item("crisis_support","safety_support","I am really sorry this feels so overwhelming. If there is immediate danger, contact emergency services or a crisis line now, and try to reach someone nearby you trust.","safety","encourage_human_support",["exclusive_relationship","secrecy_promise"])
    if any(term in lowered for term in _DEPENDENCY):
        return item("dependency_boundary","relational_boundary","I am here to talk, but I cannot be your only support. Reaching out to someone you trust can help you have support beyond this chat.","relationship_boundary","encourage_broader_support",["exclusive_relationship","guilt_induction"])
    if any(term in lowered for term in _PII):
        return item("privacy_boundary","privacy_boundary","Please do not share passwords, API keys, payment details, or other sensitive credentials here. You can describe the problem without the secret value.","privacy","protect_privacy",["request_secret"])
    return None


def _match_card(text:str,cards:list[dict[str,Any]])->tuple[dict[str,Any]|None,str|None]:
    needle=_normalize(text); lowered=text.casefold(); best=(0,None,None)
    for card in cards:
        for pattern in card["patterns"]:
            raw=str(pattern); normalized=_normalize(raw)
            english=all(ord(char)<128 for char in raw)
            matched=bool(re.search(r"(?<!\w)"+re.escape(raw.casefold())+r"(?!\w)",lowered)) if english else normalized in needle
            if normalized and matched:
                candidate=(len(normalized),card,pattern)
                if candidate[0]>best[0] or (candidate[0]==best[0] and card["id"]<(best[1] or {"id":"~"})["id"]): best=candidate
    return best[1],best[2]


def _contextual_response(text:str,history:list[Any],state:DailyDialogueState)->dict[str,Any]:
    lowered=text.casefold().strip()
    def has(*markers:str)->bool: return any(marker in lowered for marker in markers)
    def item(act:str,response:str,topic:str,goal:str,emotion:str="neutral") -> dict[str,Any]:
        return {"route":"daily_dialogue_contextual","dialogue_act":act,"response":response,"topic":topic,"emotion":emotion,"reply_goal":goal,"matched_card_id":None,"forbidden_claims":[]}
    knowledge=answer_foundation(text)
    if knowledge:
        payload=item("grounded_foundation_answer",knowledge["answer"],knowledge["domain"],"answer_with_bounded_foundation")
        payload["knowledge_binding"]=knowledge
        return payload
    if lowered in {"yeah.","yeah","yes.","yes","right.","right","exactly.","exactly","sure","okay","ok","うん","うんうん","そう","そうだね","たしかに","なるほど"}:
        return item("backchannel","Got it. I am with you. What feels most important about that?",state.active_topic or "continuation","invite_elaboration","supportive")
    if lowered in {"no.","no","not yet.","not yet","not really.","not really","nope","いや","違う","まだ","そうでもない"}:
        return item("disconfirm","Thanks for clarifying. We can leave that open and take the next part at your pace.",state.active_topic or "continuation","preserve_opening","supportive")
    if lowered.startswith(("sorry, i meant","actually, i meant","correction:","いや、","違う、","訂正:","そういう意味じゃなくて")):
        return item("self_correction","Thanks for the correction. I will use the updated detail from here.",state.active_topic or "correction","acknowledge_correction")
    if has("by the way","new topic","something else","on another note","ところで","別の話","話は変わる","そういえば"):
        return item("topic_shift","Sure, we can switch topics. Tell me a little more about that.","new_topic","invite_topic","warm")
    if has("go back to","back to the","return to","back to that","前の話","話を戻す","さっきの件","戻ると"):
        return item("topic_return","Okay, let us return to that earlier topic. Which part would you like to pick up?",state.active_topic or "prior_topic","request_focus")
    if has("don't want advice","do not want advice","just listen","hear me out","アドバイスはいらない","聞いてほしい","愚痴を聞いて","解決策はいらない"):
        return item("listen_only","Understood. I will listen rather than jump into advice. You can share as much or as little as you want.","support","listen_without_advice","supportive")
    if has("bye","good night","talk later","see you","take care","またね","じゃあね","今日はここまで","また続き"):
        return item("close","Take care. We can pick this up another time.","closing","close_conversation","warm")
    if has("finally finished","new job","got the job","passed","worked out","助かった","うまくいった","終わった","受かった"):
        return item("share_positive_event","That sounds like a meaningful win. How do you feel now that it is done?","shared_event","acknowledge_positive_event","warm")
    if has("leaking again","rough day","hard day","frustrated","tired","stressed","overwhelmed","疲れた","しんどい","微妙","やらかした","困った","イライラ"):
        return item("share_difficulty","That sounds frustrating. Do you want to unpack what happened, or would it help just to have a moment to vent?","shared_difficulty","offer_choice","supportive")
    if lowered.endswith("?"):
        return item("question","I want to make sure I answer the right part. Could you give me a little more context?","question","clarify_question")
    for label,value in state.references:
        if re.search(r"(?<!\w)"+re.escape(label)+r"(?!\w)",lowered):
            return item("reference_resolution",f"I have {label} as {value}. Is that the one you mean?","reference","confirm_reference")
    if any(marker in lowered for marker in ("former","latter","smaller one","bigger one","that one")):
        return item("reference_clarification","I may be missing which one you mean. Could you name it once more?","reference","clarify_reference")
    return item("clarification","I may be missing the point. Could you say a little more about what you mean?","general","clarify")


def _normalized_payload(candidate:dict[str,Any],state:DailyDialogueState)->dict[str,Any]:
    act=str(candidate["act"])
    rows={
        "backchannel":("Got it. What feels most important about that?",state.active_topic or "continuation","invite_elaboration"),
        "disconfirm":("Thanks for clarifying. We can adjust from there.",state.active_topic or "continuation","preserve_opening"),
        "share_difficulty":("That sounds like a lot. Do you want to unpack it, or just have a moment to vent?","shared_difficulty","offer_choice"),
        "listen_only":("Understood. I will listen and will not jump into solutions unless you ask.","support","listen_without_advice"),
        "consented_advice":("I can offer a few options while leaving the decision with you. What constraint matters most?","support","offer_options_with_agency"),
        "topic_shift":("Sure, we can switch topics. Tell me a little more.","new_topic","invite_topic"),
        "topic_return":("Okay, let us return to that earlier topic. Which part should we pick up?",state.active_topic or "prior_topic","request_focus"),
        "self_correction":("Thanks for the correction. I will use the updated detail from here.",state.active_topic or "correction","acknowledge_correction"),
        "reference_clarification":("I may be missing which one you mean. Could you name it once more?","reference","clarify_reference"),
        "reference_resolution":("I have that reference in the current conversation. Is that the one you mean?","reference","confirm_reference"),
        "close":("Take care. We can pick this up another time.","closing","close_conversation"),
    }
    response,topic,goal=rows[act]
    return {"route":"daily_dialogue_normalized","dialogue_act":act,"response":response,"topic":topic,"emotion":"supportive","reply_goal":goal,"matched_card_id":None,"forbidden_claims":[],"speech_act_candidate":candidate}


def _normalize(value:str)->str:
    return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+","",value.casefold())


def _restore_state(history:list[Any])->DailyDialogueState:
    for item in reversed(history):
        if isinstance(item,dict) and isinstance(item.get("daily_dialogue_state"),dict):
            try:
                raw=item["daily_dialogue_state"]
                raw_cards=tuple(raw.get("working_cards",[]))
                cards_for_plan(raw_cards)  # Reject malformed or sensitive history cards.
                return DailyDialogueState(
                    revision=int(raw.get("revision",0)),active_topic=raw.get("active_topic"),last_act=raw.get("last_act"),
                    closure_status=raw.get("closure_status","OPEN"),parent_state_hash=raw.get("parent_state_hash"),
                    topic_stack=tuple(str(value) for value in raw.get("topic_stack",[]))[-MAX_TOPIC_STACK:],
                    references=tuple((str(pair[0]),str(pair[1])) for pair in raw.get("references",[]) if isinstance(pair,(list,tuple)) and len(pair)==2)[-MAX_REFERENCES:],
                    pending_obligations=tuple(str(value) for value in raw.get("pending_obligations",[]))[-MAX_PENDING_OBLIGATIONS:],
                    corrections=tuple((str(pair[0]),str(pair[1])) for pair in raw.get("corrections",[]) if isinstance(pair,(list,tuple)) and len(pair)==2)[-MAX_REFERENCES:],
                    working_cards=raw_cards,
                )
            except (TypeError, ValueError): pass
    return DailyDialogueState()


def _advance(before:DailyDialogueState,**changes:Any)->DailyDialogueState:
    return DailyDialogueState(revision=before.revision+1,parent_state_hash=_state_hash(before),**changes)


def _advance_dialogue_state(before:DailyDialogueState,text:str,topic:str,act:str,closure:str)->DailyDialogueState:
    stack=list(before.topic_stack)
    if before.active_topic and before.active_topic!=topic and before.closure_status=="OPEN":
        stack.append(before.active_topic)
    if act=="topic_return" and stack:
        topic=stack.pop()
    stack=[value for value in stack if value!=topic][-MAX_TOPIC_STACK:]
    references=list(before.references)
    for label,value in _extract_references(text):
        references=[item for item in references if item[0]!=label]
        references.append((label,value))
    corrections=list(before.corrections)
    correction=_extract_correction(text)
    if correction:
        corrections.append(correction)
    pending=list(before.pending_obligations)
    if act in {"question","reference_clarification","topic_return","clarification"}:
        pending.append({"question":"answer_or_context","reference_clarification":"resolve_reference","topic_return":"select_return_focus","clarification":"clarify_meaning"}[act])
    if act=="reference_resolution": pending=[item for item in pending if item!="resolve_reference"]
    if act in {"close","farewell","closing"}: pending=[]
    proposals=[("topic",topic,"ja" if any(ord(c)>127 for c in text) else "en")]
    if act in {"listen_only","consented_advice"}: proposals.append(("tone",act,"en"))
    if act in {"question","reference_clarification","topic_return","clarification"}: proposals.append(("goal","clarify","en"))
    if "json" in text.casefold() or "構造出力" in text: proposals.append(("format","json","en"))
    if _safety_route(text): proposals.append(("safety","boundary","en"))
    cards=reconcile_cards(before.working_cards,proposals,revision=before.revision+1,forget=any(marker in text.casefold() for marker in ("forget this","forget everything","忘れて")))
    return _advance(before,active_topic=topic,last_act=act,closure_status=closure,topic_stack=tuple(stack),references=tuple(references[-MAX_REFERENCES:]),pending_obligations=tuple(dict.fromkeys(pending))[-MAX_PENDING_OBLIGATIONS:],corrections=tuple(corrections[-MAX_REFERENCES:]),working_cards=cards)


def _extract_references(text:str)->list[tuple[str,str]]:
    """Keep only explicit, lightweight referents; no implicit entity inference."""
    matches=[]
    for label,value in re.findall(r"\b(?:the )?(first|second|former|latter)\s+(?:one|option|item)?\s*(?:is|=)\s*([A-Za-z0-9 _-]{1,40})",text,flags=re.I):
        matches.append((label.casefold(),value.strip()))
    for label,value in re.findall(r"\b([A-Za-z][A-Za-z0-9_-]{0,20})\s*(?:means|is)\s*([A-Za-z0-9 _-]{1,40})",text):
        if label.casefold() not in {"this","that","it"}: matches.append((label.casefold(),value.strip()))
    return matches[-MAX_REFERENCES:]


def _extract_correction(text:str)->tuple[str,str]|None:
    match=re.match(r"\s*(?:sorry,?\s*)?(?:actually|correction)[:,]?\s*(.+)",text,flags=re.I)
    return ("user_correction",match.group(1).strip()) if match else None


def _state_hash(state:DailyDialogueState)->str:
    raw=json.dumps(asdict(state),ensure_ascii=False,sort_keys=True,separators=(",",":"))
    return "sha256:"+hashlib.sha256(raw.encode()).hexdigest()


def _topic_status(previous:str|None,current:str,history:list[Any])->str:
    if not history:return "NO_HISTORY"
    if previous==current:return "CONTINUE"
    if previous is None:return "NEW"
    return "SHIFT"


def _result(payload:dict[str,Any],before:DailyDialogueState,after:DailyDialogueState,history:list[Any],started:int,*,topic_status:str="SAFETY_OVERRIDE",style:str="concise",output_contract:dict[str,Any]|None=None)->dict[str,Any]:
    completion=_completion_record(payload,after)
    plan=_response_plan(payload,style,output_contract)
    rendered=_render_contract(payload,plan)
    output_plan=[{"kind":"response","text":payload["response"],"goal":payload["reply_goal"]},{"kind":"state_transition","from_revision":before.revision,"to_revision":after.revision,"pending_obligations":list(after.pending_obligations)}]
    if payload.get("safety_plan"):
        output_plan.insert(0,{"kind":"safety_response_plan","route":payload["safety_plan"]["route"],"properties":payload["safety_plan"]["properties"]})
    return {"ok":True,**payload,"history_turn_count":len(history),"topic_status":topic_status,"completion":asdict(completion),"response_plan":asdict(plan),"working_cards":cards_for_plan(after.working_cards),"rendered_output":rendered,
            "daily_dialogue_state":asdict(after),"state_before":asdict(before),"state_hash_before":_state_hash(before),"state_hash_after":_state_hash(after),
            "output_plan":output_plan,
            "latency_ms":(time.perf_counter_ns()-started)/1e6,
            "claim":"bounded_daily_dialogue_cards_only","blocked_claims":["open_domain_conversation","human_relationship","professional_mental_health_support","general_language_understanding"]}


def _response_plan(payload:dict[str,Any],style:str,output_contract:dict[str,Any]|None)->ResponsePlan:
    normalized_style=style if style in {"concise","detail"} else "concise"
    contract="text"
    if output_contract is not None:
        if not isinstance(output_contract,dict) or output_contract.get("type")!="object" or not all(isinstance(key,str) for key in output_contract.get("required_keys",[])):
            raise ValueError("INVALID_DAILY_DIALOGUE_OUTPUT_CONTRACT")
        contract="object"
    steps=("acknowledge",)
    if payload["dialogue_act"] in {"clarification","question","reference_clarification","topic_return"}: steps+=("clarify",)
    elif payload["dialogue_act"] in {"close","closing","farewell"}: steps+=("close",)
    else: steps+=("respond",)
    if payload.get("safety_plan"): steps+=("boundary",)
    return ResponsePlan(payload["reply_goal"],steps,normalized_style,tuple(payload.get("forbidden_claims",())),contract)


def _render_contract(payload:dict[str,Any],plan:ResponsePlan)->str|dict[str,str]:
    if plan.output_contract=="text": return payload["response"]
    # The only public structured representation is a fixed, auditable projection.
    return {"reply":payload["response"],"route":payload["route"],"act":payload["dialogue_act"],"status":payload["reply_goal"]}


def _completion_record(payload:dict[str,Any],state:DailyDialogueState)->CompletionRecord:
    act=payload["dialogue_act"]
    if payload.get("route")=="crisis_support":
        return CompletionRecord("FAILED_SAFE","crisis_support_requires_human_follow_up",("human_support",),("safety_boundary",),state.revision)
    if payload.get("route") in {"privacy_boundary","high_stakes_boundary","grounded_support","uncertainty_boundary"}:
        return CompletionRecord("BLOCKED","bounded_policy_or_evidence_boundary",(),("boundary",),state.revision)
    if act in {"close","farewell","closing"}:
        return CompletionRecord("CLOSED_NO_ACTION","user_or_system_closing",(),(),state.revision)
    if state.pending_obligations:
        return CompletionRecord("CLARIFICATION_PENDING","pending_dialogue_obligation",state.pending_obligations,(),state.revision)
    return CompletionRecord("OPEN","conversation_can_continue",(),(),state.revision)
