#!/usr/bin/env python3
"""Da RoastBox - API key setup (GUI).

A small desktop window for entering the API keys Da RoastBox talks to
directly: OpenAI, OpenRouter, ElevenLabs, Stripe, and Google sign-in. Each
key has a Verify button that makes one real, lightweight call to that
provider so you know immediately whether it works. Save writes straight into
backend/.env and persists there - nothing else needs to be running first.

Needs nothing beyond a stock Python install (Tkinter + the standard library
only, no pip install required), so it works before you have set up the
backend's virtual environment.

Run it:
    python install.py

Then start the app:
    python server.py
"""
from __future__ import annotations

import base64
import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
import urllib.error
import urllib.request
from pathlib import Path
from tkinter import messagebox, ttk
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
ENV_PATH = BACKEND / ".env"
ENV_EXAMPLE = BACKEND / ".env.example"
MAKE_ENV = ROOT / "scripts" / "make_env.py"

TIMEOUT = 8


# --------------------------------------------------------------------- .env
# No python-dotenv dependency here on purpose: install.py must run with a
# bare "python install.py" before any pip install has happened.
def ensure_env_file() -> None:
    if ENV_PATH.exists():
        return
    if MAKE_ENV.exists():
        subprocess.run([sys.executable, str(MAKE_ENV)], check=False)
    if ENV_PATH.exists():
        return
    # Last-resort fallback if the generator script is missing or failed.
    import secrets

    lines = []
    if ENV_EXAMPLE.exists():
        lines = [ln for ln in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
                 if not ln.strip().startswith(("MONGO_URL=", "DB_NAME=", "JWT_SECRET="))]
    lines += ["", "MONGO_URL=embedded", "DB_NAME=roastbox", f"JWT_SECRET={secrets.token_hex(32)}"]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_env(path: Path = ENV_PATH) -> dict:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, val = s.partition("=")
        key = key.strip()
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        values[key] = val
    return values


def write_env_value(key: str, value: str) -> None:
    """Set one KEY=value in backend/.env, preserving every other line."""
    ensure_env_file()
    text = ENV_PATH.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    needs_quotes = any(c in value for c in (" ", "#")) and not (
        len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'"
    )
    new_value = f'"{value}"' if needs_quotes else value
    out_line = f"{key}={new_value}"
    replaced = False
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith("#") or "=" not in s:
            continue
        existing_key = s.split("=", 1)[0].strip()
        if existing_key == key:
            lines[i] = out_line
            replaced = True
            break
    if not replaced:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(out_line)
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- verifiers
# Each returns (status, message). status is one of "ok", "bad", "warn".
def _get(url: str, headers: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _post_json(url: str, headers: dict, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={**headers, "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            status, body = resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        status, body = exc.code, exc.read()
    try:
        parsed = json.loads(body.decode("utf-8", errors="replace")) if body else {}
    except json.JSONDecodeError:
        parsed = {}
    return status, parsed


def _configured_model(key: str, fallback: str) -> str:
    """The model id this app will actually use, straight from backend/.env."""
    return (read_env().get(key, "") or "").strip() or fallback


def _chat_probe(url: str, headers: dict, model: str) -> tuple[int, dict]:
    """One minimal real completion request - the hidden test call itself."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with only the single word: ok"}],
        "max_tokens": 5,
    }
    return _post_json(url, headers, payload)


def _quota_exhausted(payload: dict) -> bool:
    """True when a 429 means "no billing credits", not "slow down".

    OpenAI and OpenRouter both reuse HTTP 429 for genuine rate limiting
    *and* for an empty/unfunded account; those need completely different
    advice, so the error body's code/type has to be inspected rather than
    just the status code.
    """
    err = payload.get("error") or {}
    code = str(err.get("code") or "").lower()
    err_type = str(err.get("type") or "").lower()
    message = str(err.get("message") or "").lower()
    needles = ("insufficient_quota", "credit_balance_exhausted", "billing_not_active", "no credits")
    return any(n in code or n in err_type or n in message for n in needles)


def verify_openai(key: str) -> tuple[str, str]:
    # The model Da RoastBox actually falls back to on OpenAI, not just any model.
    model = _configured_model("ROAST_OPENAI_FREE_MODEL", "gpt-4o-mini")
    try:
        status, payload = _chat_probe(
            "https://api.openai.com/v1/chat/completions", {"Authorization": f"Bearer {key}"}, model)
    except Exception as exc:  # noqa: BLE001
        return "warn", f"Could not reach OpenAI ({exc.__class__.__name__}). Saved, not verified."
    if status == 200:
        text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        if text.strip():
            return "ok", f"Valid - OpenAI generated a real reply with {model}."
        return "warn", f"OpenAI returned HTTP 200 for {model} but no reply text; could not confirm."
    if status == 401:
        return "bad", "OpenAI rejected this key (401 Unauthorized)."
    if status == 429:
        if _quota_exhausted(payload):
            return "warn", ("Valid key, but this OpenAI account has no billing credits. Add credits at "
                             "platform.openai.com/settings/organization/billing, or skip OpenAI and rely on "
                             "OpenRouter (jokes) + ElevenLabs (voice) instead.")
        return "warn", f"Valid-looking key, but OpenAI rate-limited the test call to {model} - try again shortly."
    if status == 404:
        return "warn", f"OpenAI accepted the key but rejected model '{model}' (404). Check ROAST_OPENAI_FREE_MODEL."
    err = (payload.get("error") or {}).get("message", "")
    return "warn", f"OpenAI returned HTTP {status} for {model}{(': ' + err) if err else ''}; could not confirm."


def verify_openrouter(key: str) -> tuple[str, str]:
    # Probe both models this app actually dispatches to on the free tier: the
    # script writer and the (separate, vision-capable) photo analysis model.
    writer_model = _configured_model("ROAST_WRITER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
    vision_model = _configured_model("ROAST_VISION_OPENROUTER_FREE_MODEL", "openrouter/free")
    headers = {"Authorization": f"Bearer {key}", "HTTP-Referer": "https://da-roastbox.local",
               "X-Title": "Da RoastBox key setup"}
    results = {}
    for label, model in (("writer", writer_model), ("vision", vision_model)):
        try:
            status, payload = _chat_probe("https://openrouter.ai/api/v1/chat/completions", headers, model)
        except Exception as exc:  # noqa: BLE001
            return "warn", f"Could not reach OpenRouter ({exc.__class__.__name__}). Saved, not verified."
        results[label] = (status, payload, model)

    writer_status, writer_payload, _ = results["writer"]
    if writer_status in (401, 403):
        return "bad", "OpenRouter rejected this key (401/403 Unauthorized)."

    def _ok(status: int, payload: dict) -> bool:
        text = ((payload.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        return status == 200 and bool(text.strip())

    writer_ok = _ok(*results["writer"][:2])
    vision_ok = _ok(*results["vision"][:2])
    if writer_ok and vision_ok:
        return "ok", f"Valid - OpenRouter generated real replies with {writer_model} and {vision_model}."
    if writer_ok and not vision_ok:
        v_status, v_payload, v_model = results["vision"]
        err = (v_payload.get("error") or {}).get("message", "")
        return "warn", (f"Writer model {writer_model} works, but the photo-analysis model {v_model} "
                        f"returned HTTP {v_status}{(': ' + err) if err else ''}. Jokes will work; photos may not.")
    status, payload, model = results["writer"]
    if status == 429:
        if _quota_exhausted(payload):
            return "warn", ("Valid key, but this OpenRouter account has no credits. Add credits at "
                             "openrouter.ai/settings/credits, or pick a free (':free'-suffixed) model.")
        return "warn", f"Valid-looking key, but OpenRouter rate-limited the test call to {model} - try again shortly."
    err = (payload.get("error") or {}).get("message", "")
    return "warn", f"OpenRouter returned HTTP {status} for {model}{(': ' + err) if err else ''}; could not confirm."


def verify_elevenlabs(key: str) -> tuple[str, str]:
    try:
        status, body = _get("https://api.elevenlabs.io/v1/user", {"xi-api-key": key})
    except Exception as exc:  # noqa: BLE001
        return "warn", f"Could not reach ElevenLabs ({exc.__class__.__name__}). Saved, not verified."
    if status == 200:
        return "ok", "Valid - ElevenLabs accepted this key."
    if status == 401:
        return "bad", "ElevenLabs rejected this key (401 Unauthorized)."
    return "warn", f"ElevenLabs returned HTTP {status}; could not confirm."


def verify_stripe(key: str) -> tuple[str, str]:
    token = base64.b64encode(f"{key}:".encode("ascii")).decode("ascii")
    try:
        status, body = _get("https://api.stripe.com/v1/balance",
                             {"Authorization": f"Basic {token}"})
    except Exception as exc:  # noqa: BLE001
        return "warn", f"Could not reach Stripe ({exc.__class__.__name__}). Saved, not verified."
    if status == 200:
        mode = "TEST mode" if key.startswith(("sk_test_", "rk_test_")) else "LIVE mode"
        return "ok", f"Valid - Stripe accepted this key ({mode})."
    if status == 401:
        return "bad", "Stripe rejected this key (401 Unauthorized)."
    return "warn", f"Stripe returned HTTP {status}; could not confirm."


def verify_stripe_webhook(secret: str) -> tuple[str, str]:
    if secret.startswith("whsec_") and len(secret) >= 16:
        return "ok", "Looks like a Stripe webhook secret. Stripe only confirms this when it sends a real webhook."
    return "warn", "Stripe webhook secrets normally start with 'whsec_'. Saved as entered."


def verify_google_id(client_id: str) -> tuple[str, str]:
    if client_id.endswith(".apps.googleusercontent.com"):
        return "ok", "Looks like a Google OAuth client ID."
    return "warn", "Google client IDs usually end with '.apps.googleusercontent.com'. Saved as entered."


def verify_google_secret(client_id: str, client_secret: str) -> tuple[str, str]:
    if not client_id:
        return "warn", "Enter the matching Google client ID above, then verify again."
    data = urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": "da-roastbox-key-check",
        "redirect_uri": "http://localhost",
    }).encode("ascii")
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    try:
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = resp.read()
        except urllib.error.HTTPError as exc:
            body = exc.read()
        payload = json.loads(body.decode("utf-8", errors="replace"))
    except Exception as exc:  # noqa: BLE001
        return "warn", f"Could not reach Google ({exc.__class__.__name__}). Saved, not verified."
    error = payload.get("error", "")
    if error == "invalid_client":
        return "bad", "Google rejected this client ID/secret pair."
    if error:
        # invalid_grant / redirect_uri_mismatch / etc: Google validated the
        # client credentials themselves before rejecting our fake code.
        return "ok", "Valid - Google recognises this client ID/secret pair."
    return "warn", "Unexpected response from Google; could not confirm."


# ------------------------------------------------------------------- fields
# key, label, placeholder, verify(values) -> (status, message)
FIELDS = [
    ("OPENAI_API_KEY", "OpenAI API key", "sk-...",
     lambda v: verify_openai(v["OPENAI_API_KEY"])),
    ("OPENROUTER_API_KEY", "OpenRouter API key", "sk-or-...",
     lambda v: verify_openrouter(v["OPENROUTER_API_KEY"])),
    ("ELEVENLABS_API_KEY", "ElevenLabs API key", "",
     lambda v: verify_elevenlabs(v["ELEVENLABS_API_KEY"])),
    ("STRIPE_API_KEY", "Stripe secret key", "sk_live_... or sk_test_...",
     lambda v: verify_stripe(v["STRIPE_API_KEY"])),
    ("STRIPE_WEBHOOK_SECRET", "Stripe webhook signing secret", "whsec_...",
     lambda v: verify_stripe_webhook(v["STRIPE_WEBHOOK_SECRET"])),
    ("GOOGLE_CLIENT_ID", "Google OAuth client ID", "....apps.googleusercontent.com",
     lambda v: verify_google_id(v["GOOGLE_CLIENT_ID"])),
    ("GOOGLE_CLIENT_SECRET", "Google OAuth client secret", "",
     lambda v: verify_google_secret(v["GOOGLE_CLIENT_ID"], v["GOOGLE_CLIENT_SECRET"])),
]

OPTIONAL_FIELDS = [
    ("BLOB_READ_WRITE_TOKEN", "Vercel Blob read/write token (optional media storage)"),
    ("EMERGENT_LLM_KEY", "Emergent gateway key (optional, legacy fallback)"),
]

STATUS_COLORS = {"ok": "#1a7f37", "bad": "#c21807", "warn": "#9a6700", "": "#666666"}
STATUS_ICON = {"ok": "\u2713", "bad": "\u2717", "warn": "\u26A0", "": ""}


class KeyRow:
    def __init__(self, parent: ttk.Frame, row: int, key: str, label: str, placeholder: str,
                 verifier, get_values, on_saved) -> None:
        self.key = key
        self.verifier = verifier
        self.get_values = get_values
        self.on_saved = on_saved

        ttk.Label(parent, text=label, width=30).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)

        self.shown = tk.BooleanVar(value=False)
        self.var = tk.StringVar()
        self.entry = ttk.Entry(parent, textvariable=self.var, width=38, show="\u2022")
        self.entry.grid(row=row, column=1, sticky="we", padx=(0, 4), pady=4)
        if placeholder:
            self._placeholder = placeholder

        self.toggle_btn = ttk.Button(parent, text="\U0001F441", width=3, command=self._toggle)
        self.toggle_btn.grid(row=row, column=2, padx=2)

        self.verify_btn = ttk.Button(parent, text="Verify", command=self.verify)
        self.verify_btn.grid(row=row, column=3, padx=2)

        self.save_btn = ttk.Button(parent, text="Save", command=self.save)
        self.save_btn.grid(row=row, column=4, padx=2)

        self.status_var = tk.StringVar(value="not set")
        self.status_label = ttk.Label(parent, textvariable=self.status_var, width=46, foreground="#666666")
        self.status_label.grid(row=row + 1, column=1, columnspan=4, sticky="w", padx=(0, 4))

    def _toggle(self) -> None:
        self.shown.set(not self.shown.get())
        self.entry.configure(show="" if self.shown.get() else "\u2022")

    def set_value(self, value: str) -> None:
        self.var.set(value)
        if value:
            self.status_var.set("saved in backend/.env - click Verify to check it")
            self.status_label.configure(foreground=STATUS_COLORS[""])

    def value(self) -> str:
        return self.var.get().strip()

    def _set_status(self, status: str, message: str) -> None:
        icon = STATUS_ICON.get(status, "")
        self.status_var.set((icon + " " + message).strip())
        self.status_label.configure(foreground=STATUS_COLORS.get(status, "#666666"))

    def verify(self) -> None:
        value = self.value()
        if not value:
            self._set_status("warn", "Nothing entered yet.")
            return
        self.verify_btn.configure(state="disabled")
        self._set_status("", "Checking...")

        def work():
            try:
                status, message = self.verifier(self.get_values())
            except Exception as exc:  # noqa: BLE001
                status, message = "warn", f"Could not verify ({exc.__class__.__name__})."
            self.result_queue.put((self._set_status, (status, message)))
            self.result_queue.put((self.verify_btn.configure, {"state": "normal"}))

        self._run_async(work)

    def save(self) -> None:
        value = self.value()
        write_env_value(self.key, value)
        if value:
            self._set_status("", "Saved to backend/.env.")
        else:
            self._set_status("", "Cleared in backend/.env.")
        self.on_saved(self.key)

    def _run_async(self, fn) -> None:
        threading.Thread(target=fn, daemon=True).start()


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("Da RoastBox - API Key Setup")
        root.minsize(760, 560)

        self.queue: "queue.Queue" = queue.Queue()

        header = ttk.Frame(root, padding=(16, 14, 16, 4))
        header.pack(fill="x")
        ttk.Label(header, text="Da RoastBox - API Key Setup", font=("TkDefaultFont", 14, "bold")).pack(anchor="w")
        ttk.Label(
            header,
            text=("Enter the keys for the services this app talks to directly. Verify makes a quick,\n"
                  f"real check against that provider. Save writes straight into {ENV_PATH.relative_to(ROOT)} "
                  "and sticks around across restarts."),
            justify="left",
        ).pack(anchor="w", pady=(4, 0))

        body = ttk.Frame(root, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        existing = read_env()
        self.rows: list[KeyRow] = []
        row_index = 0
        for key, label, placeholder, verifier in FIELDS:
            row = KeyRow(body, row_index, key, label, placeholder, verifier, self._current_values, self._on_saved)
            row.result_queue = self.queue
            row.set_value(existing.get(key, ""))
            self.rows.append(row)
            row_index += 2
            if key == "GOOGLE_CLIENT_SECRET":
                # The single most common Google sign-in failure (Error 400:
                # redirect_uri_mismatch) is simply never adding this exact
                # URI in Google Cloud Console. Verify can't catch it - Google
                # only checks the redirect_uri during the real sign-in
                # request, not this key check - so spell it out up front.
                #
                # The redirect_uri Google actually sees is computed by the
                # *browser* from the page it is sitting on - i.e. the
                # frontend's own port (frontend/.env PORT, default 3000) -
                # never backend/.env's PORT (that's the separate API process,
                # default 8001, and the browser never navigates there).
                frontend_env = read_env(ROOT / "frontend" / ".env")
                port = (frontend_env.get("PORT") or "3000").strip() or "3000"
                hint = (
                    f"In Google Cloud Console \u2192 Credentials \u2192 this OAuth client, add under "
                    f"\"Authorized redirect URIs\":  http://127.0.0.1:{port}/auth-complete.html\n"
                    f"and under \"Authorized JavaScript origins\":  http://127.0.0.1:{port}\n"
                    f"(this is the port the app's web page itself loads on - NOT the API port - and "
                    f"must match the address bar exactly, including the port - \"localhost\" and "
                    f"\"127.0.0.1\" are NOT interchangeable to Google)."
                )
                ttk.Label(body, text=hint, wraplength=680, justify="left", foreground="#555") \
                    .grid(row=row_index, column=0, columnspan=5, sticky="w", pady=(0, 8))
                row_index += 1

        ttk.Separator(body, orient="horizontal").grid(
            row=row_index, column=0, columnspan=5, sticky="we", pady=10)
        row_index += 1

        self.show_optional = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            body, text="Show optional/advanced fields (Vercel Blob, Emergent gateway)",
            variable=self.show_optional, command=lambda: self._toggle_optional(body, row_index),
        ).grid(row=row_index, column=0, columnspan=5, sticky="w")
        row_index += 1
        self._optional_start_row = row_index
        self._optional_widgets: list[tk.Widget] = []

        footer = ttk.Frame(root, padding=(16, 4, 16, 16))
        footer.pack(fill="x")
        ttk.Button(footer, text="Verify All", command=self.verify_all).pack(side="left")
        ttk.Button(footer, text="Save All", command=self.save_all).pack(side="left", padx=8)
        ttk.Button(footer, text="Close", command=root.destroy).pack(side="right")

        self.status_var = tk.StringVar(value=f"Reading/writing {ENV_PATH}")
        ttk.Label(root, textvariable=self.status_var, padding=(16, 0, 16, 10), foreground="#666").pack(anchor="w")

        self.root.after(100, self._poll_queue)

    def _toggle_optional(self, body: ttk.Frame, start_row: int) -> None:
        for w in self._optional_widgets:
            w.destroy()
        self._optional_widgets = []
        if not self.show_optional.get():
            return
        existing = read_env()
        r = start_row
        for key, label in OPTIONAL_FIELDS:
            lbl = ttk.Label(body, text=label, width=30)
            lbl.grid(row=r, column=0, sticky="w", pady=4)
            var = tk.StringVar(value=existing.get(key, ""))
            entry = ttk.Entry(body, textvariable=var, width=38)
            entry.grid(row=r, column=1, sticky="we", pady=4)

            def make_save(k=key, v=var):
                def _save():
                    write_env_value(k, v.get().strip())
                    messagebox.showinfo("Saved", f"{k} saved to backend/.env")
                return _save

            btn = ttk.Button(body, text="Save", command=make_save())
            btn.grid(row=r, column=4, padx=2)
            self._optional_widgets += [lbl, entry, btn]
            r += 1

    def _current_values(self) -> dict:
        return {row.key: row.value() for row in self.rows}

    def _on_saved(self, key: str) -> None:
        self.status_var.set(f"Saved {key} to backend/.env just now.")

    def verify_all(self) -> None:
        for row in self.rows:
            if row.value():
                row.verify()

    def save_all(self) -> None:
        count = 0
        for row in self.rows:
            write_env_value(row.key, row.value())
            count += 1
        self.status_var.set(f"Saved {count} field(s) to backend/.env.")
        messagebox.showinfo("Saved", "All keys were saved to backend/.env.\n\nYou can close this window and run:\n    python server.py")

    def _poll_queue(self) -> None:
        try:
            while True:
                fn, args = self.queue.get_nowait()
                if isinstance(args, dict):
                    fn(**args)
                else:
                    fn(*args)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)


def main() -> int:
    ensure_env_file()
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print("Could not open a desktop window (no display available).", file=sys.stderr)
        print(f"Details: {exc}", file=sys.stderr)
        print("Edit backend/.env directly instead, or run this on a desktop session.", file=sys.stderr)
        return 1
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
