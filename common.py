#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared stdlib/pandas utilities, OAuth helpers, and PT-BR formatters for the CTV pipeline."""

import base64
import io
import json
import os
import re
import sys
import time
from pathlib import Path

import google.auth
import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.errors import HttpError

BASE_DIR = Path(__file__).resolve().parent

CM360_SCOPES = [
    "https://www.googleapis.com/auth/dfareporting",
    "https://www.googleapis.com/auth/dfatrafficking",
]
DV360_SCOPES = [
    "https://www.googleapis.com/auth/doubleclickbidmanager",
    "https://www.googleapis.com/auth/display-video",
]
DEFAULT_CTV_PLATFORMS = [
    {"id": "30004", "name": "Connected TV", "ui_label": "Smart TV / Connected TV"},
    {"id": "30006", "name": "Set top box", "ui_label": "Set-top Box"},
]
DEFAULT_NON_CTV_PLATFORMS = [
    {"id": "30000", "name": "Desktop"},
    {"id": "30001", "name": "Smartphone"},
    {"id": "30002", "name": "Tablet"},
    {"id": "30003", "name": "Mobile midrange: feature phone"},
    {"id": "30005", "name": "Unknown platform"},
]


def norm_slug(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def classify_tag(aname: str) -> tuple[bool, str]:
    low, nlow = str(aname or "").lower(), norm_slug(aname)
    if "in_app_purchase" in low and "ios" in low:
        return True, f"iOS ({aname})"
    if "in_app_purchase" in low and "android" in low:
        return True, f"Android ({aname})"
    if any(k in nlow for k in ("comprafeita", "purchase", "ordercomplete", "venda")) and "pixelunico" not in nlow:
        return True, f"Web ({aname})"
    return False, str(aname or "")


def resolve_path(raw_path, must_exist: bool = False) -> Path:
    if not raw_path:
        return Path("")
    p = Path(os.path.expandvars(os.path.expanduser(str(raw_path))))
    if p.is_absolute():
        return p
    cand = (BASE_DIR / p).resolve()
    if must_exist and not cand.exists():
        alt = (BASE_DIR.parent / p.name).resolve()
        if alt.exists():
            return alt
    return cand


def load_config(config_path, mode_override: str | None = None) -> dict:
    cfg_file = Path(config_path).resolve()
    with open(cfg_file, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if mode_override:
        cfg["identification_mode"] = mode_override
    cfg["_config_path"] = str(cfg_file)
    cfg["output_dir"] = str(resolve_path(cfg.get("output_dir", f"outputs/{cfg['case_slug']}")))
    return cfg


def get_mode(cfg: dict) -> str:
    raw = str(cfg.get("identification_mode", "both")).strip().lower()
    if raw == "both":
        return "both"
    return "device" if "device" in raw else "site"


def fmt_int(n) -> str:
    if n is None or pd.isna(n):
        return "—"
    return f"{int(round(float(n))):,d}".replace(",", ".")


def fmt_dec(val, decimals: int = 2, sign: bool = False) -> str:
    if val is None or pd.isna(val):
        return "—"
    fmt_str = f"{{:{'+' if sign else ''},.{decimals}f}}"
    return fmt_str.format(float(val)).replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_curr(val, sign: bool = False) -> str:
    if val is None or pd.isna(val):
        return "—"
    v = float(val)
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if v < 0:
        return f"-R$ {s}"
    return f"+R$ {s}" if (sign and v > 0) else f"R$ {s}"


def fmt_pct(val, decimals: int = 2, sign: bool = False) -> str:
    if val is None or pd.isna(val):
        return "—"
    return f"{fmt_dec(val, decimals=decimals, sign=sign)}%"


def img_to_b64(path) -> str:
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")


def clean_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def clean_id_str(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.replace(r"\.0$", "", regex=True)


def read_cm360_csv(path) -> pd.DataFrame:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    header_idx = next((i + 1 for i, l in enumerate(lines) if l.strip() == "Report Fields"), 0)
    body = [
        l for l in lines[header_idx:]
        if l.strip() and not l.startswith("Grand Total") and not l.startswith("A dash (-)")
    ]
    return pd.read_csv(io.StringIO("".join(body)), low_memory=False)


def read_p2c_csv(path) -> pd.DataFrame:
    if isinstance(path, (bytes, bytearray)):
        lines = path.decode("utf-8", errors="replace").splitlines(keepends=True)
        h_idx = next((i for i, l in enumerate(lines) if "Conversion ID" in l and "Total Conversions" in l), 0)
        df = pd.read_csv(io.StringIO("".join(lines[h_idx:])), low_memory=False).dropna(subset=["Conversion ID"])
    else:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            h_idx = next((i for i, l in enumerate(f) if l.startswith("Conversion ID,") or ("Conversion ID" in l and "Total Conversions" in l)), 0)
        df = pd.read_csv(path, skiprows=h_idx, low_memory=False).dropna(subset=["Conversion ID"])
    return df[~df["Conversion ID"].astype(str).str.contains("Grand Total|---")].copy()


def execute_with_retry(req_fn, retries: int = 5, base_sleep: float = 2.0):
    # CM360 v5 returns transient 500/503s when running multiple REACH/P2C reports concurrently
    for attempt in range(retries):
        try:
            return req_fn().execute()
        except HttpError as e:
            if e.resp.status in (429, 500, 502, 503, 504) and attempt < retries - 1:
                wait = base_sleep * (1.8 ** attempt)
                print(f"    [Retry {attempt + 1}/{retries}] HTTP {e.resp.status} transitório, aguardando {wait:.1f}s...")
                time.sleep(wait)
            else:
                raise


def is_colab() -> bool:
    return "google.colab" in sys.modules or bool(os.environ.get("COLAB_RELEASE_TAG"))


def load_credentials(token_path, client_secrets_path=None, scopes=None):
    req_scopes = scopes or CM360_SCOPES
    t_path = resolve_path(token_path, must_exist=True)
    if t_path.exists():
        raw = json.loads(t_path.read_text(encoding="utf-8"))
        if raw.get("type") == "service_account":
            return service_account.Credentials.from_service_account_file(str(t_path), scopes=req_scopes)
        creds = Credentials.from_authorized_user_file(str(t_path), scopes=raw.get("scopes") or req_scopes)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            t_path.parent.mkdir(parents=True, exist_ok=True)
            t_path.write_text(creds.to_json(), encoding="utf-8")
        return creds
    if client_secrets_path:
        cs_path = resolve_path(client_secrets_path, must_exist=True)
        if cs_path.exists():
            cs_raw = json.loads(cs_path.read_text(encoding="utf-8"))
            if cs_raw.get("type") == "service_account":
                return service_account.Credentials.from_service_account_file(str(cs_path), scopes=req_scopes)
            flow = InstalledAppFlow.from_client_secrets_file(str(cs_path), req_scopes)
            if is_colab():
                flow.redirect_uri = "http://localhost:8080/"
                auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
                print(f"\n1. Clique no link para autorizar sua conta Google:\n{auth_url}\n")
                redirect_resp = input("2. Após autorizar (mesmo se a página der erro de conexão localhost), copie a URL completa da barra de endereço e cole aqui: ").strip()
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
                flow.fetch_token(authorization_response=redirect_resp)
                creds = flow.credentials
            else:
                creds = flow.run_local_server(port=0)
            out_t = resolve_path(token_path)
            out_t.parent.mkdir(parents=True, exist_ok=True)
            out_t.write_text(creds.to_json(), encoding="utf-8")
            return creds
    if is_colab():
        quota_proj = os.environ.get("GOOGLE_CLOUD_QUOTA_PROJECT") or None
        creds, _ = google.auth.default(scopes=req_scopes, quota_project_id=quota_proj)
        return creds
    raise FileNotFoundError(
        f"Token OAuth não encontrado em '{token_path}'. Rode step0_setup_and_discover.py ou forneça client_secrets.json."
    )
