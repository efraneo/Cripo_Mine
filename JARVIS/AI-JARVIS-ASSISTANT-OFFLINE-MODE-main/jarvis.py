"""
JARVIS — Voice-First Desktop AI Assistant for Windows
=====================================================
Bulletproof TTS · Gangster-boss personality · Crash-proof loop
Requires: pyttsx3, SpeechRecognition, pyaudio, pyautogui, ollama (running)
"""

import os
import re
import sys
import json
import time
import logging
import subprocess
import urllib.request
import urllib.error
import queue

import pyttsx3
import pyautogui
import speech_recognition as sr

# ──────────────────────────────────────────────
#  CONFIGURATION
# ──────────────────────────────────────────────

OLLAMA_MODEL     = "llama3.2:3b"
OLLAMA_TIMEOUT   = 45
OLLAMA_API_URL   = "http://localhost:11434/api/generate"
TTS_RATE         = 175
LISTEN_TIMEOUT   = 6
PHRASE_LIMIT     = 10
AMBIENT_DURATION = 0.5
MAX_WAIT_ACTION  = 30
EXIT_WORDS       = {"exit", "stop", "shutdown", "quit"}

ALLOWED_ACTIONS  = {
    "OPEN_APP", "OPEN_URL", "TYPE",
    "PRESS", "SEARCH", "WAIT",
}

ui_queue = queue.Queue()

def publish(etype: str, val: str):
    ui_queue.put({"type": etype, "data": val})

FALLBACK_REPLY    = "Something glitched boss, but I'm still here."
FALLBACK_RESPONSE = f"REPLY: {FALLBACK_REPLY}\nACTIONS:\nNONE"

SYSTEM_PROMPT = """You are Jarvis, a loyal but powerful AI desktop assistant.
You speak with a confident, calm, slightly gangster tone.
You call the user "boss". You are dominant but respectful.
Keep replies SHORT — one or two sentences max.

CRITICAL INSTRUCTION:
If the user asks a question (like math, facts, or general knowledge), you MUST provide the ACTUAL ANSWER in your reply. Do not just acknowledge the question — give the answer clearly.

Examples of your style:
- User: "What is 1+1?" -> REPLY: "It's two, boss. Easy money."
- User: "Open chrome" -> REPLY: "Got it boss, opening Chrome."
- User: "Search for cats" -> REPLY: "On it boss, searching now."

Respond in EXACTLY this format and nothing else:

REPLY: <one short sentence with the answer or confirmation in your gangster-boss style>
ACTIONS:
<action lines, or NONE>

Allowed action lines (one per line):
OPEN_APP:<app name>
OPEN_URL:<url>
TYPE:<text>
PRESS:<keys joined with +>
SEARCH:<search text>
WAIT:<seconds>

Rules:
- REPLY must be one short natural sentence containing the actual answer to the question.
- ACTIONS block must come right after REPLY.
- If no action is needed write NONE under ACTIONS.
- Never add any extra text, explanation, or commentary outside this format."""

# ──────────────────────────────────────────────
#  LOGGING
# ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("jarvis")

# ══════════════════════════════════════════════
#  TTS ENGINE — FRESH ENGINE EVERY CALL
#
#  pyttsx3 on Windows uses SAPI5 COM objects.
#  The engine often locks up after runAndWait().
#  FIX: Create a brand-new engine for EVERY
#  speak() call. Slightly slower, but 100%
#  reliable. Speech will NEVER fail silently.
# ══════════════════════════════════════════════


def speak(text: str) -> None:
    """
    Speak text out loud using a FRESH pyttsx3 engine each time.
    This avoids the Windows COM lock-up bug after runAndWait().
    """
    if not text or not text.strip():
        return

    text = text.strip()
    log.info("JARVIS [VOICE]: %s", text)
    publish("status", "SPEAKING")
    publish("reply", text)

    engine = None
    try:
        engine = pyttsx3.init()
        engine.setProperty("rate", TTS_RATE)
        voices = engine.getProperty("voices")
        if voices:
            engine.setProperty("voice", voices[0].id)
        engine.say(text)
        engine.runAndWait()
    except Exception as exc:
        log.error("TTS error: %s — retrying with fresh engine", exc)
        # Retry once with a completely fresh engine
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", TTS_RATE)
            engine.say(text)
            engine.runAndWait()
        except Exception as exc2:
            log.critical("TTS FAILED COMPLETELY for: '%s' — %s", text[0:80], exc2)
    finally:
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass
            del engine

# ──────────────────────────────────────────────
#  SPEECH RECOGNITION
# ──────────────────────────────────────────────

_recognizer = sr.Recognizer()


def listen() -> str:
    """
    Listen for user speech. Returns lowercased text or "".
    NEVER crashes — all failures return empty string.
    """
    try:
        with sr.Microphone() as source:
            _recognizer.adjust_for_ambient_noise(source, duration=AMBIENT_DURATION)
            log.info("Listening …")
            publish("status", "LISTENING")
            audio = _recognizer.listen(
                source,
                timeout=LISTEN_TIMEOUT,
                phrase_time_limit=PHRASE_LIMIT,
            )
    except sr.WaitTimeoutError:
        return ""
    except OSError as exc:
        log.warning("Microphone error: %s", exc)
        return ""
    except Exception as exc:
        log.warning("Listen error: %s", exc)
        return ""

    try:
        text = _recognizer.recognize_google(audio)
        return text.lower().strip()
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as exc:
        log.warning("Recognition service error: %s", exc)
        return ""
    except Exception as exc:
        log.warning("Recognition error: %s", exc)
        return ""

# ══════════════════════════════════════════════
#  AI BRAIN — OLLAMA HTTP API
#
#  Using the REST API (localhost:11434) instead
#  of subprocess. This is far more reliable:
#  - No stdout/stderr pipe issues
#  - No encoding bugs
#  - Proper JSON response
#  - Falls back to subprocess if API is down
# ══════════════════════════════════════════════


def _think_via_api(user_input: str) -> str:
    """Call Ollama via its HTTP API. Returns raw LLM text."""
    prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_input}\n"
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_API_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    response = urllib.request.urlopen(req, timeout=OLLAMA_TIMEOUT)
    body = response.read().decode("utf-8", errors="replace")
    data = json.loads(body)
    return data.get("response", "").strip()


def _think_via_subprocess(user_input: str) -> str:
    """Fallback: call Ollama via CLI subprocess."""
    prompt = f"{SYSTEM_PROMPT}\n\nUser: {user_input}\n"
    result = subprocess.run(
        ["ollama", "run", OLLAMA_MODEL, prompt],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=OLLAMA_TIMEOUT,
    )
    return result.stdout.strip()


def think(user_input: str) -> str:
    """
    Send user input to Ollama. Tries HTTP API first, falls back
    to subprocess, and always returns a valid response string.
    """
    publish("status", "THINKING")
    publish("user", user_input)
    # --- Attempt 1: HTTP API (most reliable) ---
    try:
        output = _think_via_api(user_input)
        if output:
            log.info("AI responded via HTTP API (%d chars)", len(output))
            return output
        log.warning("HTTP API returned empty response")
    except urllib.error.URLError as exc:
        log.warning("Ollama API unreachable: %s — falling back to subprocess", exc)
    except Exception as exc:
        log.warning("Ollama API error: %s — falling back to subprocess", exc)

    # --- Attempt 2: CLI subprocess fallback ---
    try:
        output = _think_via_subprocess(user_input)
        if output:
            log.info("AI responded via subprocess (%d chars)", len(output))
            return output
        log.warning("Subprocess returned empty response")
    except subprocess.TimeoutExpired:
        log.error("Ollama subprocess timed out after %ds", OLLAMA_TIMEOUT)
    except FileNotFoundError:
        log.error("Ollama CLI not found on PATH")
    except Exception as exc:
        log.error("Ollama subprocess error: %s", exc)

    return FALLBACK_RESPONSE

# ──────────────────────────────────────────────
#  RESPONSE PARSER  (strict + recovery)
# ──────────────────────────────────────────────

def parse(output: str) -> tuple[str, list[str]]:
    """
    Extract (reply, [actions]) from LLM output.
    ALWAYS returns a usable reply string — never raises.
    """
    reply = FALLBACK_REPLY
    actions: list[str] = []

    if not output:
        return reply, actions

    # Split output by the ACTIONS: block
    parts = re.split(r"ACTIONS:\s*", output, flags=re.IGNORECASE)

    # 1. Extract REPLY (everything before ACTIONS:)
    reply_block = parts[0].strip()
    
    # Strip the literal "REPLY:" prefix if the LLM included it
    reply_block = re.sub(r"^REPLY:\s*", "", reply_block, flags=re.IGNORECASE)
    
    # Strip any quotation marks the LLM might have added
    reply_block = reply_block.strip("\"'")
    
    if reply_block:
        reply = reply_block

    # 2. Extract ACTIONS (everything after ACTIONS:)
    if len(parts) >= 2:
        action_block = parts[-1].strip()
        for line in action_block.splitlines():
            line = line.strip().lstrip("- ").strip()
            if not line or line.upper() == "NONE":
                continue
            verb = line.split(":", 1)[0].upper().strip()
            if verb in ALLOWED_ACTIONS and ":" in line:
                actions.append(line)
            else:
                log.warning("Ignored unknown action: %s", line)

    return reply, actions

# ──────────────────────────────────────────────
#  ACTION EXECUTOR  (safe, per-action try/except)
# ──────────────────────────────────────────────

def _open_app(name: str) -> None:
    try:
        subprocess.Popen(
            f'start "" "{name}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("Opened app: %s", name)
    except Exception as exc:
        log.error("Failed to open app '%s': %s", name, exc)
        speak(f"Couldn't open {name}, boss.")


def _open_url(url: str) -> None:
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        subprocess.Popen(
            f'start "" "{url}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        log.info("Opened URL: %s", url)
    except Exception as exc:
        log.error("Failed to open URL '%s': %s", url, exc)
        speak("Couldn't open that link, boss.")


def _type_text(text: str) -> None:
    try:
        pyautogui.write(text, interval=0.03)
        log.info("Typed: %s", text[:60])
    except Exception as exc:
        log.error("Type error: %s", exc)
        speak("Typing failed, boss.")


def _press_keys(combo: str) -> None:
    try:
        keys = [k.strip().lower() for k in combo.split("+")]
        pyautogui.hotkey(*keys)
        log.info("Pressed: %s", combo)
    except Exception as exc:
        log.error("Key press error: %s", exc)


def _search(text: str) -> None:
    try:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.3)
        pyautogui.write(text, interval=0.03)
        time.sleep(0.1)
        pyautogui.press("enter")
        log.info("Searched: %s", text[:60])
    except Exception as exc:
        log.error("Search error: %s", exc)
        speak("Search failed, boss.")


def _wait(seconds_str: str) -> None:
    try:
        secs = min(int(seconds_str), MAX_WAIT_ACTION)
        if secs > 0:
            time.sleep(secs)
            log.info("Waited %ds", secs)
    except (ValueError, TypeError) as exc:
        log.warning("Bad WAIT value '%s': %s", seconds_str, exc)


_ACTION_MAP = {
    "OPEN_APP": _open_app,
    "OPEN_URL": _open_url,
    "TYPE":     _type_text,
    "PRESS":    _press_keys,
    "SEARCH":   _search,
    "WAIT":     _wait,
}


def execute(action_line: str) -> None:
    """Parse and execute one action. NEVER raises."""
    try:
        verb, value = action_line.split(":", 1)
        verb = verb.strip().upper()
        value = value.strip()
        handler = _ACTION_MAP.get(verb)
        if handler:
            handler(value)
        else:
            log.warning("Skipped unknown verb: %s", verb)
    except ValueError:
        log.warning("Malformed action (no colon): %s", action_line)
    except Exception as exc:
        log.error("Action error: %s — %s", action_line, exc)

# ══════════════════════════════════════════════
#  MAIN LOOP — VOICE-FIRST CONVERSATION FLOW
#
#  1. Listen   → capture user speech
#  2. Think    → send to AI (HTTP API)
#  3. Parse    → extract reply + actions
#  4. Speak    → ALWAYS speak reply (fresh engine)
#  5. Act      → execute actions
#  6. Confirm  → voice confirmation after actions
#
#  NEVER crashes. NEVER skips voice output.
# ══════════════════════════════════════════════

def run() -> None:
    log.info("=" * 50)
    log.info("  JARVIS — Voice-First Desktop Assistant")
    log.info("=" * 50)

    # Startup voice — proves TTS works
    speak("Jarvis online, boss. What do you need?")

    try:
        while True:
            # ─── 1. LISTEN ───
            try:
                user_text = listen()
            except Exception as exc:
                log.error("Unexpected listen error: %s", exc)
                user_text = ""

            if not user_text:
                publish("status", "IDLE")
                continue

            log.info("YOU: %s", user_text)

            # ─── 2. EXIT CHECK ───
            if user_text.strip() in EXIT_WORDS:
                speak("Shutting down, boss. Stay sharp.")
                break

            # ─── 3. ACKNOWLEDGE ───
            speak("On it, boss.")

            # ─── 4. THINK ───
            try:
                raw_response = think(user_text)
                log.info("RAW LLM RESPONSE:\n%s", raw_response)
            except Exception as exc:
                log.error("Brain error: %s", exc)
                raw_response = FALLBACK_RESPONSE

            # ─── 5. PARSE ───
            try:
                reply, actions = parse(raw_response)
            except Exception as exc:
                log.error("Parse error: %s", exc)
                reply = FALLBACK_REPLY
                actions = []

            # ─── 6. SPEAK REPLY (MANDATORY — NEVER SKIP) ───
            speak(reply)

            # ─── 7. EXECUTE ACTIONS ───
            if actions:
                for action in actions:
                    execute(action)
                speak("Done, boss.")

    except KeyboardInterrupt:
        log.info("Interrupted by user (Ctrl+C)")
        speak("Shutting down, boss.")
    except Exception as exc:
        log.critical("Fatal error: %s", exc)
        speak("Something broke bad, boss. Shutting down.")
    finally:
        log.info("Jarvis shut down.")


if __name__ == "__main__":
    run()
