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


def read_env() -> dict:
    values: dict[str, str] = {}
    if not ENV_PATH.exists():
        return values
    for line in ENV_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
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


def verify_openai(key: str) -> tuple[str, str]:
    try:
        status, body = _get("https://api.openai.com/v1/models",
                             {"Authorization": f"Bearer {key}"})
    except Exception as exc:  # noqa: BLE001
        return "warn", f"Could not reach OpenAI ({exc.__class__.__name__}). Saved, not verified."
    if status == 200:
        return "ok", "Valid - OpenAI accepted this key."
    if status == 401:
        return "bad", "OpenAI rejected this key (401 Unauthorized)."
    return "warn", f"OpenAI returned HTTP {status}; could not confirm."


def verify_openrouter(key: str) -> tuple[str, str]:
    try:
        status, body = _get("https://openrouter.ai/api/v1/auth/key",
                             {"Authorization": f"Bearer {key}"})
    except Exception as exc:  # noqa: BLE001
        return "warn", f"Could not reach OpenRouter ({exc.__class__.__name__}). Saved, not verified."
    if status == 200:
        return "ok", "Valid - OpenRouter accepted this key."
    if status == 401:
        return "bad", "OpenRouter rejected this key (401 Unauthorized)."
    return "warn", f"OpenRouter returned HTTP {status}; could not confirm."


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
