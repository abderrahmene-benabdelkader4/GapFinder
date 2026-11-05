"""Groq wrapper built for real use: tolerant JSON parsing/repair, retries with the server's own wait hints, friendly errors,
automatic fallback when JSON mode fails, model discovery. Errors are typed so the UI can tell the researcher what to do."""
import os, re, json, time

USAGE = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "truncated": 0, "retries": 0}
_sleep = time.sleep                                               # patched in tests

class LLMError(Exception): pass
class LLMConfigError(LLMError): pass       # missing / rejected API key
class LLMModelError(LLMError): pass        # model not found or retired
class LLMRateLimit(LLMError): pass         # daily/long limit: stop, progress is saved, resume later
class LLMTooLarge(LLMError): pass          # single request exceeds the model limits

def available(): return bool(os.getenv("GROQ_API_KEY"))
def model(): return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

def _client():
    from groq import Groq
    kw = dict(api_key=os.environ["GROQ_API_KEY"], max_retries=0, timeout=float(os.getenv("GROQ_TIMEOUT", "90")))   # retries are handled here, with the server's hints
    if os.getenv("GROQ_BASE_URL"): kw["base_url"] = os.environ["GROQ_BASE_URL"]
    return Groq(**kw)

def _info(e):
    body = getattr(e, "body", None)
    if isinstance(body, dict): body = body.get("error", body)
    return getattr(e, "status_code", None), (body if isinstance(body, dict) else {}), str(e)

def _wait_hint(e, msg):
    try:
        h = e.response.headers.get("retry-after")
        if h: return float(h)
    except Exception: pass
    m = re.search(r"try again in\s*(?:(\d+)h)?\s*(?:(\d+)m(?!s))?\s*(?:([\d.]+)s)?\s*(?:([\d.]+)ms)?", msg)
    if m and any(m.groups()): h, mi, s, ms = (float(x) if x else 0.0 for x in m.groups()); return h * 3600 + mi * 60 + s + ms / 1000
    return None

def _call(messages, json_mode, max_tokens, model_name=None):
    c = _client(); m = model_name or model(); use_json = json_mode
    for attempt in range(8):
        try:
            kw = dict(model=m, messages=messages, temperature=0, max_tokens=max_tokens)
            if use_json: kw["response_format"] = {"type": "json_object"}
            r = c.chat.completions.create(**kw); u = getattr(r, "usage", None); USAGE["calls"] += 1
            USAGE["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0; USAGE["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
            ch = r.choices[0]; return ch.message.content or "", ch.finish_reason
        except Exception as e:
            code, body, msg = _info(e); name = type(e).__name__; low = msg.lower()
            if code in (401, 403) or name in ("AuthenticationError", "PermissionDeniedError"): raise LLMConfigError("Groq rejected the API key. Check it in Settings (keys start with 'gsk_').")
            if code == 404 or body.get("code") in ("model_not_found", "model_decommissioned") or ("model" in low and ("decommissioned" in low or "does not exist" in low or "not found" in low)):
                raise LLMModelError(f"The model '{m}' is not available on your Groq account (retired or renamed). Open Settings and pick another model.")
            if code == 400 and body.get("code") == "json_validate_failed":
                if body.get("failed_generation"): return body["failed_generation"], "failed_generation"
                use_json = False; continue
            if code == 400 and use_json and "json" in low: use_json = False; continue                 # this model has no JSON mode: ask in the prompt instead
            if code == 413 or "request too large" in low: raise LLMTooLarge("The request is larger than the model's per-minute token limit. Use a smaller chunk size or a model with a higher limit.")
            if code == 429 or name == "RateLimitError":
                w = _wait_hint(e, msg) or min(2 ** attempt, 30)
                if w > 180: raise LLMRateLimit(f"Groq usage limit reached (wait about {int(w // 60)} min). Progress is saved: press Resume later, or switch model in Settings.")
                USAGE["retries"] += 1; _sleep(w + 0.5); continue
            if code in (500, 502, 503, 504) or name in ("APIConnectionError", "APITimeoutError", "InternalServerError"): USAGE["retries"] += 1; _sleep(min(2 ** attempt, 20)); continue
            raise LLMError(f"Groq error {code}: {msg[:300]}")
    raise LLMError("Groq did not answer after several retries (network or service problem).")

def parse_json(text):
    t = (text or "").strip(); t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I).strip()
    for cand in (t, (re.search(r"\{.*\}", t, re.S) or [None])[0] if re.search(r"\{.*\}", t, re.S) else None):
        if cand:
            try: obj = json.loads(cand); return obj if isinstance(obj, dict) else {"_value": obj}
            except ValueError: pass
    import json_repair                                             # truncated or slightly malformed output
    obj = json_repair.loads(t)
    if isinstance(obj, dict): return obj
    raise ValueError("model reply is not a JSON object")

def chat_json(system, user, max_tokens=1800):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    for attempt in range(2):
        text, finish = _call(msgs, True, max_tokens)
        if finish == "length": USAGE["truncated"] += 1
        try: return parse_json(text)
        except ValueError:
            msgs = msgs + [{"role": "assistant", "content": text[:2000]}, {"role": "user", "content": "That was not valid JSON. Reply again with ONE JSON object only, no prose, no code fences."}]
    raise LLMError("The model did not return valid JSON twice in a row. Try a larger model in Settings.")

def chat_text(system, user, max_tokens=400): return _call([{"role": "system", "content": system}, {"role": "user", "content": user}], False, max_tokens)[0].strip()

BAD = ("whisper", "guard", "tts", "playai", "orpheus", "embed", "safeguard", "vision-preview")
def list_models(): return sorted(m.id for m in _client().models.list().data)
def pick_model(ids):
    """Prefer a large instruct model; never pick speech/guard models."""
    ok = [i for i in ids if not any(b in i.lower() for b in BAD)]
    for pref in ("llama-3.3-70b-versatile", "gpt-oss-120b", "70b", "gpt-oss-20b", "versatile", "instant", "8b"):
        hit = next((i for i in ok if pref in i.lower()), None)
        if hit: return hit
    return ok[0] if ok else None

def check():
    """Used by Settings: returns dict(ok, message, model, models)."""
    if not available(): return dict(ok=False, message="No Groq API key set.", model=None, models=[])
    try:
        ids = list_models(); m = model()
        if m not in ids: alt = pick_model(ids); return dict(ok=False, message=f"Model '{m}' is not available. Suggested: {alt}", model=alt, models=ids)
        chat_text("Reply with one word.", "Say OK.", 5); return dict(ok=True, message="Groq works.", model=m, models=ids)
    except LLMError as e: return dict(ok=False, message=str(e), model=None, models=[])
    except Exception as e: return dict(ok=False, message=f"{type(e).__name__}: {str(e)[:200]}", model=None, models=[])
