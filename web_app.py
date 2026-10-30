#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CTV Compass — Hosted Web Portal & API Server for Executive CTV Measurement (CM360)."""

import datetime
import io
import json
import os
import secrets
import shutil
import sys
import tempfile
import threading
import time
import urllib.parse
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from common import (
    CM360_SCOPES,
    DEFAULT_CTV_PLATFORMS,
    DEFAULT_NON_CTV_PLATFORMS,
    classify_product_tag,
    classify_tag,
    fmt_curr,
    fmt_dec,
    fmt_pct,
    norm_slug,
    resolve_path,
)
from step1_extract_reports import extract_reports
from step2_compute_methodology import compute_methodology
from step3_generate_html import generate_html_report

# pyplot state isn't thread-safe across concurrent renders
_PLOT_LOCK = threading.Lock()
_STATE_LOCK = threading.Lock()
_OAUTH_STATES: dict[str, dict] = {}
_SESSIONS: dict[str, dict] = {}
_JOBS: dict[str, dict] = {}
_THREAD_LOCAL = threading.local()


class _JobAwareStdout(io.TextIOBase):
    def __init__(self, wrapped):
        self._wrapped = wrapped

    def write(self, s: str) -> int:
        self._wrapped.write(s)
        cb = getattr(_THREAD_LOCAL, "log_cb", None)
        if cb and s:
            cb(s)
        return len(s)

    def flush(self):
        self._wrapped.flush()


sys.stdout = _JobAwareStdout(sys.__stdout__)


def _gc_stale_state():
    now = time.time()
    with _STATE_LOCK:
        for k in [k for k, v in _OAUTH_STATES.items() if now - v["ts"] > 600]:
            _OAUTH_STATES.pop(k, None)
        for k in [k for k, v in _SESSIONS.items() if now - v["ts"] > 43200]:
            _SESSIONS.pop(k, None)
        for k in [k for k, v in _JOBS.items() if now - v["ts"] > 7200 and v["status"] in ("done", "error")]:
            job = _JOBS.pop(k, None)
            if job and job.get("work_dir"):
                shutil.rmtree(job["work_dir"], ignore_errors=True)


def _load_oauth_web_config() -> dict | None:
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    csec = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if cid and csec:
        return {
            "web": {
                "client_id": cid,
                "client_secret": csec,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        }
    cs_path = resolve_path(os.environ.get("GOOGLE_CLIENT_SECRETS_FILE", "client_secrets.json"), must_exist=True)
    if cs_path.exists():
        raw = json.loads(cs_path.read_text(encoding="utf-8"))
        if "web" in raw or "installed" in raw:
            return {"web": raw.get("web") or raw.get("installed")}
    return None


def _load_server_credentials():
    raw_env = os.environ.get("CM360_CREDENTIALS_JSON", "").strip()
    if raw_env:
        info = json.loads(raw_env)
        if info.get("type") == "service_account":
            return service_account.Credentials.from_service_account_info(info, scopes=CM360_SCOPES)
        creds = Credentials.from_authorized_user_info(info, scopes=info.get("scopes") or CM360_SCOPES)
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        return creds

    cred_file = os.environ.get("CM360_CREDENTIALS_FILE", "").strip()
    if not cred_file and os.environ.get("ALLOW_LOCAL_TOKEN", "").lower() in ("1", "true", "yes"):
        cred_file = "token.json"
    if cred_file:
        p = resolve_path(cred_file, must_exist=True)
        if p.exists():
            info = json.loads(p.read_text(encoding="utf-8"))
            if info.get("type") == "service_account":
                return service_account.Credentials.from_service_account_file(str(p), scopes=CM360_SCOPES)
            creds = Credentials.from_authorized_user_file(str(p), scopes=info.get("scopes") or CM360_SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                p.write_text(creds.to_json(), encoding="utf-8")
            return creds
    return None


def _creds_to_worker_file(creds, dest: Path):
    if isinstance(creds, service_account.Credentials):
        raw_env = os.environ.get("CM360_CREDENTIALS_JSON", "").strip()
        if raw_env:
            dest.write_text(raw_env, encoding="utf-8")
        else:
            src = resolve_path(os.environ.get("CM360_CREDENTIALS_FILE", ""), must_exist=True)
            shutil.copyfile(src, dest)
    else:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
        dest.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(dest, 0o600)


def _attach_job_logger(job: dict):
    buf = [""]

    def _on_chunk(chunk: str):
        text = buf[0] + chunk.replace("\r", "\n")
        parts = text.split("\n")
        buf[0] = parts[-1]
        with _STATE_LOCK:
            for line in parts[:-1]:
                if line.strip():
                    job["logs"].append(line.strip())
                    job["logs"] = job["logs"][-80:]

    _THREAD_LOCAL.log_cb = _on_chunk


def _run_pipeline_job(job_id: str, creds, payload: dict):
    job = _JOBS[job_id]
    _attach_job_logger(job)
    work_dir = Path(job["work_dir"])
    tok_path = work_dir / "worker_token.json"
    try:
        _creds_to_worker_file(creds, tok_path)
        raw_mode = str(payload.get("mode", "both")).strip().lower()
        mode = raw_mode if raw_mode in ("both", "site", "device") else "both"
        camp_id = str(payload["campaign_id"])
        slug = f"camp_{camp_id}_{mode}"
        out_dir = work_dir / "output"
        act_map = payload["activities"]
        prod_map = payload.get("product_activities") or {}

        cfg = {
            "case_slug": slug,
            "brand_name": payload.get("brand_name") or payload["campaign_name"],
            "agency_name": payload.get("agency_name") or "Agência",
            "identification_mode": mode,
            "cm360": {
                "profile_id": str(payload["profile_id"]),
                "account_id": str(payload.get("account_id", "")),
                "advertiser_id": str(payload["advertiser_id"]),
                "floodlight_config_id": str(payload["fl_config_id"]),
                "campaign_id": camp_id,
                "campaign_name": payload["campaign_name"],
                "brand_keyword_normalized": norm_slug(payload["campaign_name"]),
                "token_reporting_path": str(tok_path),
                "purchase_activity_ids": list(act_map.keys()),
                "purchase_activity_labels": act_map,
                "product_activity_ids": list(prod_map.keys()),
                "product_activity_labels": prod_map,
            },
            "dv360": {"enabled": False},
            "date_window": {"start_date": payload["start_date"], "end_date": payload["end_date"]},
            "output_dir": str(out_dir),
        }
        if mode in ("both", "device"):
            cfg["ctv_platform_types"] = DEFAULT_CTV_PLATFORMS
            cfg["non_ctv_platform_types"] = DEFAULT_NON_CTV_PLATFORMS

        cfg_path = work_dir / "config.json"
        cfg_path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")

        job["step"] = "1/3 — Extraindo relatórios oficiais no CM360 (1 a 4 min)..."
        extract_reports(str(cfg_path))
        tok_path.unlink(missing_ok=True)

        job["step"] = "2/3 — Calculando alcance incremental e validando as 5 travas matemáticas..."
        res_path = compute_methodology(str(cfg_path))

        job["step"] = "3/3 — Renderizando infográficos e apresentação executiva..."
        with _PLOT_LOCK:
            html_path = generate_html_report(str(cfg_path))

        res = json.loads(Path(res_path).read_text(encoding="utf-8"))
        mode_lbl = mode.upper()
        extra_note = ""
        if mode == "both":
            res_site = json.loads((out_dir / "methodology_results.json").read_text(encoding="utf-8"))
            naming_ok = bool(res_site["meta"].get("naming_detected", len(res_site.get("ctv_channels", [])) > 0))
            b_dev = res["ctv_block_consolidated"]
            if naming_ok:
                blk = res_site["ctv_block_consolidated"]
                mode_lbl = "UNIFICADO: SITE + VALIDAÇÃO DEVICE TYPE"
                extra_note = f" | Validação Device TV+STB: {fmt_curr(b_dev['cost'])} → {fmt_dec(b_dev['total_attributed_conversions'], 1)} comp. ({fmt_curr(b_dev['total_attributed_revenue'])})"
            else:
                blk = b_dev
                mode_lbl = "VALIDAÇÃO AUTOMÁTICA POR DEVICE TYPE (SEM 'CTV' NO NOME DO SITE)"
        else:
            blk = res["ctv_block_consolidated"]

        roas_val = blk.get("roas_attributed") or 0.0
        with _STATE_LOCK:
            job["html_path"] = html_path
            job["filename"] = Path(html_path).name
            job["summary"] = {
                "brand_name": cfg["brand_name"],
                "mode": mode_lbl,
                "extra_note": extra_note,
                "cost": fmt_curr(blk["cost"]),
                "cost_share": fmt_pct(blk["cost_share_pct"]),
                "conversions": fmt_dec(blk["total_attributed_conversions"], 1),
                "conv_share": fmt_pct(blk["share_campaign_attributed_pct"]),
                "revenue": fmt_curr(blk["total_attributed_revenue"]),
                "roas": f"{fmt_dec(roas_val)}x",
                "roas_positive": bool(roas_val > 1.0),
            }
            job["step"] = "Concluído!"
            job["status"] = "done"
    except Exception as exc:
        with _STATE_LOCK:
            job["error"] = str(exc)
            job["step"] = "Falha na execução"
            job["status"] = "error"
    finally:
        tok_path.unlink(missing_ok=True)
        _THREAD_LOCAL.log_cb = None


INDEX_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CTV Compass — Mensuração Executiva de CTV (CM360)</title>
<link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@500;700&family=Roboto:wght@400;500;700&family=Roboto+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --blue: #1A73E8; --blue-bg: #E8F0FE; --green: #137333; --green-bg: #E6F4EA;
    --yellow-bg: #FEF7E0; --yellow-border: #F9AB00; --red: #C5221F; --red-bg: #FCE8E6;
    --bg: #F8F9FA; --card: #FFFFFF; --ink: #202124; --muted: #5F6368; --border: #DADCE0;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Roboto', sans-serif; background: var(--bg); color: var(--ink); line-height: 1.5; padding-bottom: 60px; }
  .top-stripe { height: 4px; background: linear-gradient(90deg, #4285F4 0 25%, #EA4335 25% 50%, #FBBC04 50% 75%, #34A853 75% 100%); }
  header { background: var(--card); border-bottom: 1px solid var(--border); padding: 14px 32px; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
  .title-wrap h1 { font-family: 'Google Sans', sans-serif; font-size: 20px; font-weight: 700; }
  .title-wrap p { font-size: 13px; color: var(--muted); }
  .container { max-width: 1020px; margin: 26px auto; padding: 0 20px; display: flex; flex-direction: column; gap: 20px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 14px; padding: 24px 28px; box-shadow: 0 1px 3px rgba(60,64,67,0.08); }
  .card h2 { font-family: 'Google Sans', sans-serif; font-size: 17px; margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
  .card p.sub { font-size: 13.5px; color: var(--muted); margin-bottom: 18px; }
  .step-pill { display: inline-flex; width: 24px; height: 24px; border-radius: 50%; background: var(--blue-bg); color: var(--blue); font-size: 12px; font-weight: 700; align-items: center; justify-content: center; }
  .grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  @media (max-width: 760px) { .grid-2 { grid-template-columns: 1fr; } }
  label { display: block; font-size: 12px; font-weight: 700; color: var(--muted); margin-bottom: 6px; text-transform: uppercase; letter-spacing: 0.04em; }
  input[type="text"], input[type="date"], select { width: 100%; padding: 10px 12px; border: 1px solid var(--border); border-radius: 8px; font-size: 14px; background: #FFF; color: var(--ink); }
  input:focus, select:focus { outline: 2px solid var(--blue); border-color: transparent; }
  .btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; padding: 10px 20px; border-radius: 999px; font-family: 'Google Sans', sans-serif; font-size: 13.5px; font-weight: 700; border: 1px solid var(--border); background: #FFF; color: var(--ink); cursor: pointer; text-decoration: none; }
  .btn.primary { background: var(--blue); color: #FFF; border-color: var(--blue); }
  .btn.primary:disabled { opacity: 0.55; cursor: not-allowed; }
  .btn.green { background: var(--green); color: #FFF; border-color: var(--green); }
  .tag-list { max-height: 210px; overflow-y: auto; border: 1px solid var(--border); border-radius: 10px; padding: 10px 14px; display: flex; flex-direction: column; gap: 8px; background: #FAFAFA; }
  .tag-item { display: flex; align-items: center; gap: 10px; font-size: 13.5px; cursor: pointer; font-weight: 400; text-transform: none; letter-spacing: 0; color: var(--ink); margin: 0; }
  .tag-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; background: var(--green-bg); color: var(--green); }
  .banner { padding: 13px 16px; border-radius: 10px; font-size: 13.5px; margin-bottom: 14px; }
  .banner.warn { background: var(--yellow-bg); border-left: 4px solid var(--yellow-border); }
  .banner.err { background: var(--red-bg); border-left: 4px solid var(--red); color: var(--red); }
  .banner.ok { background: var(--green-bg); border-left: 4px solid var(--green); color: var(--green); }
  .log-box { background: #202124; color: #E8EAED; font-family: 'Roboto Mono', monospace; font-size: 12px; padding: 14px; border-radius: 10px; max-height: 200px; overflow-y: auto; margin-top: 12px; white-space: pre-wrap; }
  .kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 14px 0; }
  @media (max-width: 760px) { .kpi-grid { grid-template-columns: 1fr 1fr; } }
  .kpi { background: var(--bg); border: 1px solid var(--border); border-radius: 10px; padding: 14px; }
  .kpi .k-lbl { font-size: 11.5px; color: var(--muted); font-weight: 700; text-transform: uppercase; }
  .kpi .k-val { font-family: 'Google Sans', sans-serif; font-size: 20px; font-weight: 700; color: var(--blue); margin-top: 4px; }
  .kpi .k-sub { font-size: 12px; color: var(--muted); margin-top: 2px; }
  iframe.preview { width: 100%; height: 650px; border: 1px solid var(--border); border-radius: 12px; margin-top: 16px; background: #FFF; }
  .hidden { display: none !important; }
</style>
</head>
<body>
<div class="top-stripe"></div>
<header>
  <div class="title-wrap">
    <h1>CTV Compass</h1>
    <p>Mensuração Executiva de CTV no CM360 (Standard + Unique Reach + Path to Conversion — Site &amp; Device Type)</p>
  </div>
  <div id="authHeader"></div>
</header>

<div class="container">
  <div id="unconfiguredCard" class="card hidden">
    <h2>Configuração da API CM360 no Servidor</h2>
    <p class="sub">Esta instância não possui credenciais da API do Campaign Manager 360 configuradas no ambiente.</p>
    <div class="banner warn">
      Defina <b>GOOGLE_CLIENT_ID</b> e <b>GOOGLE_CLIENT_SECRET</b> (OAuth 2.0 Web Client)
      ou <b>CM360_CREDENTIALS_JSON</b> / <b>CM360_CREDENTIALS_FILE</b> (Service Account) e reinicie o serviço.
      Consulte o <b>README.md</b> para instruções de configuração.
    </div>
  </div>

  <div id="loginCard" class="card hidden" style="text-align:center;padding:44px 28px;">
    <h2 style="justify-content:center;font-size:22px;">Autenticação CM360</h2>
    <p class="sub" style="max-width:520px;margin:8px auto 24px;">Autentique-se com uma conta Google que possua User Profile ativo no Campaign Manager 360.</p>
    <a class="btn primary" href="/auth/login">Entrar com Google</a>
  </div>

  <div id="appWorkspace" class="hidden">
    <div class="card">
      <h2><span class="step-pill">1</span> Escolher Campanha</h2>
      <p class="sub">Selecione a conta e a campanha do CM360. O período oficial e o anunciante são preenchidos automaticamente.</p>
      <div class="grid-2">
        <div>
          <label for="profileSelect">Conta / Perfil CM360</label>
          <select id="profileSelect"></select>
        </div>
        <div>
          <label for="searchInput">Filtrar Campanha por Nome ou ID</label>
          <input type="text" id="searchInput" placeholder="Digite parte do nome ou ID da campanha...">
        </div>
      </div>
      <div style="margin-bottom:16px;">
        <label for="campaignSelect">Campanha Encontrada</label>
        <select id="campaignSelect"></select>
      </div>
      <div class="grid-2">
        <div>
          <label for="brandInput">Nome da Marca / Título no Slide</label>
          <input type="text" id="brandInput">
        </div>
        <div>
          <label for="agencyInput">Nome da Agência</label>
          <input type="text" id="agencyInput" value="Agência">
        </div>
      </div>
      <div class="grid-2" style="margin-bottom:0;">
        <div>
          <label for="modeSelect">Critério de Identificação de CTV</label>
          <select id="modeSelect">
            <option value="both" selected>Visão Dupla: Naming do Site + Validação por Device Type (Recomendado)</option>
            <option value="site">Apenas Naming do Site (veículos com 'CTV' no nome)</option>
            <option value="device">Apenas Device Type (Smart TV e Set-top Box)</option>
          </select>
        </div>
        <div class="grid-2" style="margin-bottom:0;">
          <div>
            <label for="startInput">Data Início</label>
            <input type="date" id="startInput">
          </div>
          <div>
            <label for="endInput">Data Fim</label>
            <input type="date" id="endInput">
          </div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:20px;">
      <h2><span class="step-pill">2</span> Revisar Tags Floodlight (Compra &amp; Visualização de Produto)</h2>
      <p class="sub">Selecione <b>1 tag transacional oficial de compra</b> e <b>1 tag de visualização de produto por plataforma</b> (Web, Android e iOS) para apurar o funil <code>CVR Produto → Compra</code> (com fallback automático caso não existam tags de produto).</p>
      <div class="grid-2" style="margin-bottom:0;">
        <div>
          <label>1. Tags de Compra Oficial (1 por Plataforma)</label>
          <div id="tagsContainer" class="tag-list">Carregando conversões da campanha...</div>
        </div>
        <div>
          <label>2. Tags de Visualização de Produto — Denominador do CVR (Opcional)</label>
          <div id="prodTagsContainer" class="tag-list">Carregando tags de produto...</div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top:20px;">
      <h2><span class="step-pill">3</span> Executar Pipeline</h2>
      <p class="sub">Extrai os relatórios no CM360, valida as invariantes matemáticas e gera o relatório HTML.</p>
      <div id="errorBanner" class="banner err hidden"></div>
      <button id="runBtn" class="btn primary" onclick="startJob()">Gerar Relatório</button>

      <div id="progressArea" class="hidden" style="margin-top:18px;">
        <div id="stepLabel" style="font-weight:700;color:var(--blue);font-size:14px;">Iniciando...</div>
        <div id="logBox" class="log-box"></div>
      </div>

      <div id="resultArea" class="hidden" style="margin-top:22px;">
        <div class="banner ok" id="roasBanner"></div>
        <div class="kpi-grid" id="kpiGrid"></div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;">
          <a id="downloadBtn" class="btn green" href="#">Baixar HTML</a>
          <a id="openTabBtn" class="btn" href="#" target="_blank" rel="noopener">Abrir em Nova Aba / Imprimir PDF</a>
        </div>
        <iframe id="reportPreview" class="preview"></iframe>
      </div>
    </div>
  </div>
</div>

<script>
let searchTimer = null;

function esc(s) {
  return String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function apiGet(url) {
  const r = await fetch(url);
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || 'Erro na requisição');
  return d;
}

async function initApp() {
  try {
    const boot = await apiGet('/api/bootstrap');
    if (boot.auth_mode === 'unconfigured') {
      document.getElementById('unconfiguredCard').classList.remove('hidden');
      return;
    }
    if (!boot.authenticated) {
      document.getElementById('loginCard').classList.remove('hidden');
      return;
    }
    if (boot.auth_mode === 'oauth_web') {
      document.getElementById('authHeader').innerHTML = '<a class="btn" href="/auth/logout" style="padding:7px 16px;font-size:12.5px;">Sair</a>';
    } else {
      document.getElementById('authHeader').innerHTML = '<span style="font-size:12.5px;color:var(--green);font-weight:700;">API CM360 Conectada</span>';
    }
    document.getElementById('appWorkspace').classList.remove('hidden');

    const pSel = document.getElementById('profileSelect');
    pSel.innerHTML = boot.profiles.map(p => `<option value="${esc(p.profileId)}">${esc(p.accountName || 'Conta')} — ${esc(p.userName || '')} (${esc(p.profileId)})</option>`).join('');
    pSel.onchange = () => loadCampaigns();

    document.getElementById('searchInput').oninput = () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(loadCampaigns, 350);
    };
    document.getElementById('campaignSelect').onchange = () => loadCampaignDetails();
    await loadCampaigns();
  } catch (e) {
    const err = document.getElementById('errorBanner');
    err.textContent = e.message;
    err.classList.remove('hidden');
    document.getElementById('appWorkspace').classList.remove('hidden');
  }
}

async function loadCampaigns() {
  const profId = document.getElementById('profileSelect').value;
  const q = encodeURIComponent(document.getElementById('searchInput').value.trim());
  const cSel = document.getElementById('campaignSelect');
  cSel.innerHTML = '<option value="">Buscando campanhas no CM360...</option>';
  const data = await apiGet(`/api/campaigns?profile_id=${profId}&q=${q}`);
  if (!data.campaigns.length) {
    cSel.innerHTML = '<option value="">Nenhuma campanha encontrada</option>';
    document.getElementById('tagsContainer').innerHTML = '<i>Nenhuma campanha selecionada.</i>';
    document.getElementById('prodTagsContainer').innerHTML = '<i>Nenhuma campanha selecionada.</i>';
    return;
  }
  cSel.innerHTML = data.campaigns.map(c => `<option value="${esc(c.id)}">${esc(c.name)} (${esc(c.startDate || '')} a ${esc(c.endDate || '')})</option>`).join('');
  await loadCampaignDetails();
}

async function loadCampaignDetails() {
  const profId = document.getElementById('profileSelect').value;
  const campId = document.getElementById('campaignSelect').value;
  if (!campId) return;
  const tagsBox = document.getElementById('tagsContainer');
  const prodBox = document.getElementById('prodTagsContainer');
  tagsBox.innerHTML = 'Carregando tags Floodlight do anunciante...';
  prodBox.innerHTML = 'Carregando tags de produto...';
  const d = await apiGet(`/api/campaign_details?profile_id=${profId}&campaign_id=${campId}`);
  window._currentCampMeta = d;
  document.getElementById('brandInput').value = d.campaign_name;
  document.getElementById('startInput').value = d.start_date;
  document.getElementById('endInput').value = d.end_date;
  if (!d.activities.length) {
    tagsBox.innerHTML = '<i>Nenhuma tag Floodlight encontrada para este anunciante.</i>';
    prodBox.innerHTML = '<i>Nenhuma tag Floodlight encontrada para este anunciante.</i>';
    return;
  }
  const purcList = [...d.activities].sort((a, b) => (b.recommended ? 1 : 0) - (a.recommended ? 1 : 0) || a.name.localeCompare(b.name));
  tagsBox.innerHTML = purcList.map(a => `
    <label class="tag-item">
      <input type="checkbox" class="fl-check" value="${esc(a.id)}" data-label="${esc(a.label)}" ${a.recommended ? 'checked' : ''}>
      <span>${esc(a.name)}</span>
      ${a.recommended ? '<span class="tag-badge">Recomendada</span>' : ''}
    </label>
  `).join('');
  const prodList = [...d.activities].sort((a, b) => (b.product_recommended ? 1 : 0) - (a.product_recommended ? 1 : 0) || a.name.localeCompare(b.name));
  prodBox.innerHTML = prodList.map(a => `
    <label class="tag-item">
      <input type="checkbox" class="fl-prod-check" value="${esc(a.id)}" data-label="${esc(a.product_label || a.label)}" ${a.product_recommended ? 'checked' : ''}>
      <span>${esc(a.name)}</span>
      ${a.product_recommended ? '<span class="tag-badge">Recomendada</span>' : ''}
    </label>
  `).join('');
}

async function startJob() {
  const err = document.getElementById('errorBanner');
  err.classList.add('hidden');
  const checks = Array.from(document.querySelectorAll('.fl-check:checked'));
  if (!checks.length) {
    err.textContent = 'Selecione pelo menos 1 tag Floodlight de compra no Passo 2.';
    err.classList.remove('hidden');
    return;
  }
  const activities = {};
  checks.forEach(c => { activities[c.value] = c.dataset.label; });
  const productActivities = {};
  Array.from(document.querySelectorAll('.fl-prod-check:checked')).forEach(c => {
    productActivities[c.value] = c.dataset.label;
  });
  const meta = window._currentCampMeta || {};
  const payload = {
    profile_id: document.getElementById('profileSelect').value,
    account_id: meta.account_id || '',
    advertiser_id: meta.advertiser_id || '',
    fl_config_id: meta.fl_config_id || '',
    campaign_id: document.getElementById('campaignSelect').value,
    campaign_name: meta.campaign_name || '',
    brand_name: document.getElementById('brandInput').value.trim(),
    agency_name: document.getElementById('agencyInput').value.trim(),
    mode: document.getElementById('modeSelect').value,
    start_date: document.getElementById('startInput').value,
    end_date: document.getElementById('endInput').value,
    activities: activities,
    product_activities: productActivities
  };

  document.getElementById('runBtn').disabled = true;
  document.getElementById('resultArea').classList.add('hidden');
  document.getElementById('progressArea').classList.remove('hidden');
  document.getElementById('logBox').textContent = '';
  document.getElementById('stepLabel').textContent = 'Iniciando processamento...';

  try {
    const r = await fetch('/api/jobs', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || 'Falha ao iniciar job');
    streamJob(d.job_id);
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove('hidden');
    document.getElementById('runBtn').disabled = false;
  }
}

function streamJob(jobId) {
  const stepEl = document.getElementById('stepLabel');
  const logEl = document.getElementById('logBox');
  const errEl = document.getElementById('errorBanner');
  const btnEl = document.getElementById('runBtn');

  const es = new EventSource(`/api/jobs/${jobId}/stream`);
  es.onmessage = (ev) => {
    const st = JSON.parse(ev.data);
    stepEl.textContent = st.step || '';
    logEl.textContent = (st.logs || []).join('\\n');
    logEl.scrollTop = logEl.scrollHeight;
    if (st.status === 'done') {
      es.close();
      btnEl.disabled = false;
      renderResult(jobId, st.summary);
    } else if (st.status === 'error') {
      es.close();
      btnEl.disabled = false;
      errEl.textContent = st.error || 'Erro durante a execução.';
      errEl.classList.remove('hidden');
    }
  };
  es.onerror = async () => {
    es.close();
    try {
      const st = await apiGet(`/api/jobs/${jobId}`);
      if (st.status === 'done') {
        btnEl.disabled = false;
        renderResult(jobId, st.summary);
      } else if (st.status === 'error') {
        btnEl.disabled = false;
        errEl.textContent = st.error;
        errEl.classList.remove('hidden');
      } else {
        setTimeout(() => streamJob(jobId), 2000);
      }
    } catch (_) {
      btnEl.disabled = false;
    }
  };
}

function renderResult(jobId, s) {
  const note = s.roas_positive
    ? ' — supera 1,0x de ROAS (gera mais receita atribuída do que o custo de mídia investido no veículo)'
    : '';
  document.getElementById('roasBanner').innerHTML = `<b>Concluído (${esc(s.brand_name)} — ${esc(s.mode)}).</b> Relatório validado${esc(note)}${esc(s.extra_note || '')}.`;
  document.getElementById('kpiGrid').innerHTML = `
    <div class="kpi"><div class="k-lbl">Investimento CTV</div><div class="k-val">${esc(s.cost)}</div><div class="k-sub">${esc(s.cost_share)} da campanha</div></div>
    <div class="kpi"><div class="k-lbl">Compras Atribuídas</div><div class="k-val">${esc(s.conversions)}</div><div class="k-sub">${esc(s.conv_share)} do total P2C</div></div>
    <div class="kpi"><div class="k-lbl">Receita Atribuída</div><div class="k-val">${esc(s.revenue)}</div><div class="k-sub">Unificada (Solo + Assistida + AOV)</div></div>
    <div class="kpi"><div class="k-lbl">ROAS Equivalente</div><div class="k-val">${esc(s.roas)}</div><div class="k-sub">Receita ÷ Custo CTV</div></div>
  `;
  document.getElementById('downloadBtn').href = `/api/jobs/${jobId}/report?download=1`;
  document.getElementById('openTabBtn').href = `/api/jobs/${jobId}/report`;
  document.getElementById('reportPreview').src = `/api/jobs/${jobId}/report`;
  document.getElementById('resultArea').classList.remove('hidden');
}

initApp();
</script>
</body>
</html>
"""


class CTVWebHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.__stdout__.write(f"[HTTP] {self.address_string()} - {fmt % args}\n")

    def _base_url(self) -> str:
        env_url = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
        if env_url:
            return env_url
        proto = self.headers.get("X-Forwarded-Proto", "http").split(",")[0].strip()
        host = self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "localhost:8080"
        return f"{proto}://{host}"

    def _session_id(self) -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        if not raw_cookie:
            return None
        jar = cookies.SimpleCookie()
        jar.load(raw_cookie)
        return jar["ctv_sid"].value if "ctv_sid" in jar else None

    def _resolve_auth(self):
        _gc_stale_state()
        oauth_cfg = _load_oauth_web_config()
        if oauth_cfg:
            sid = self._session_id()
            with _STATE_LOCK:
                sess = _SESSIONS.get(sid) if sid else None
            if not sess:
                return "oauth_web", None, None
            raw_sess = json.loads(sess["creds_json"])
            creds = Credentials.from_authorized_user_info(raw_sess, scopes=raw_sess.get("scopes") or CM360_SCOPES)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with _STATE_LOCK:
                    sess["creds_json"] = creds.to_json()
                    sess["ts"] = time.time()
            return "oauth_web", creds, sid
        srv_creds = _load_server_credentials()
        if srv_creds:
            return "server_credentials", srv_creds, "server_shared"
        return "unconfigured", None, None

    def _send_json(self, code: int, data: dict, extra_headers: list[tuple[str, str]] | None = None):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or []):
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, set_cookie: str | None = None):
        self.send_response(302)
        self.send_header("Location", location)
        if set_cookie:
            self.send_header("Set-Cookie", set_cookie)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/healthz":
            return self._send_json(200, {"ok": True})

        if path == "/":
            body = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/auth/login":
            oauth_cfg = _load_oauth_web_config()
            if not oauth_cfg:
                return self._redirect("/")
            redirect_uri = f"{self._base_url()}/auth/callback"
            if redirect_uri.startswith(("http://localhost", "http://127.0.0.1")):
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
            flow = Flow.from_client_config(oauth_cfg, scopes=CM360_SCOPES, redirect_uri=redirect_uri)
            auth_url, state = flow.authorization_url(access_type="offline", include_granted_scopes="true", prompt="consent")
            with _STATE_LOCK:
                _OAUTH_STATES[state] = {
                    "code_verifier": getattr(flow, "code_verifier", None),
                    "redirect_uri": redirect_uri,
                    "ts": time.time(),
                }
            return self._redirect(auth_url)

        if path == "/auth/callback":
            oauth_cfg = _load_oauth_web_config()
            state = (qs.get("state") or [""])[0]
            with _STATE_LOCK:
                st_info = _OAUTH_STATES.pop(state, None)
            if not oauth_cfg or not st_info:
                return self._send_json(400, {"error": "Sessão de login expirada ou inválida. Volte para / e tente novamente."})
            if st_info["redirect_uri"].startswith(("http://localhost", "http://127.0.0.1")):
                os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
            flow = Flow.from_client_config(oauth_cfg, scopes=CM360_SCOPES, state=state, redirect_uri=st_info["redirect_uri"])
            if st_info.get("code_verifier"):
                flow.code_verifier = st_info["code_verifier"]
            flow.fetch_token(authorization_response=f"{self._base_url()}{self.path}")
            sid = secrets.token_urlsafe(32)
            with _STATE_LOCK:
                _SESSIONS[sid] = {"creds_json": flow.credentials.to_json(), "ts": time.time()}
            secure_flag = "; Secure" if st_info["redirect_uri"].startswith("https://") else ""
            cookie_hdr = f"ctv_sid={sid}; HttpOnly; Path=/; SameSite=Lax; Max-Age=43200{secure_flag}"
            return self._redirect("/", set_cookie=cookie_hdr)

        if path == "/auth/logout":
            sid = self._session_id()
            if sid:
                with _STATE_LOCK:
                    _SESSIONS.pop(sid, None)
            return self._redirect("/", set_cookie="ctv_sid=; HttpOnly; Path=/; Max-Age=0")

        if path == "/api/bootstrap":
            mode, creds, _ = self._resolve_auth()
            if mode == "unconfigured" or not creds:
                return self._send_json(200, {"auth_mode": mode, "authenticated": False, "profiles": []})
            try:
                cm = build("dfareporting", "v5", credentials=creds)
                profs = cm.userProfiles().list().execute().get("items", [])
                return self._send_json(200, {"auth_mode": mode, "authenticated": True, "profiles": profs})
            except Exception as exc:
                return self._send_json(403, {"error": f"Falha ao consultar perfis do CM360: {exc}"})

        if path == "/api/campaigns":
            _, creds, _ = self._resolve_auth()
            if not creds:
                return self._send_json(401, {"error": "Não autenticado."})
            prof_id = (qs.get("profile_id") or [""])[0].strip()
            query = (qs.get("q") or [""])[0].strip()
            cm = build("dfareporting", "v5", credentials=creds)
            if query.isdigit():
                try:
                    c = cm.campaigns().get(profileId=prof_id, id=query).execute()
                    return self._send_json(200, {"campaigns": [c]})
                except Exception:
                    pass
            q_slug = norm_slug(query)
            matched, page_token, pages = [], None, 0
            while pages < 6:
                resp = cm.campaigns().list(
                    profileId=prof_id, archived=False, maxResults=500, sortField="ID", sortOrder="DESCENDING", pageToken=page_token
                ).execute()
                for c in resp.get("campaigns", []):
                    if not q_slug or q_slug in norm_slug(c.get("name", "")):
                        matched.append({
                            "id": str(c["id"]),
                            "name": c.get("name", ""),
                            "startDate": c.get("startDate", ""),
                            "endDate": c.get("endDate", ""),
                        })
                page_token = resp.get("nextPageToken")
                pages += 1
                if not page_token or len(matched) >= 50:
                    break
            return self._send_json(200, {"campaigns": matched[:50]})

        if path == "/api/campaign_details":
            _, creds, _ = self._resolve_auth()
            if not creds:
                return self._send_json(401, {"error": "Não autenticado."})
            prof_id = (qs.get("profile_id") or [""])[0].strip()
            camp_id = (qs.get("campaign_id") or [""])[0].strip()
            cm = build("dfareporting", "v5", credentials=creds)
            prof = cm.userProfiles().get(profileId=prof_id).execute()
            camp = cm.campaigns().get(profileId=prof_id, id=camp_id).execute()
            adv_id = str(camp.get("advertiserId"))
            adv = cm.advertisers().get(profileId=prof_id, id=adv_id).execute()
            fl_cfg_id = str(adv.get("floodlightConfigurationId", adv_id))
            acts = cm.floodlightActivities().list(profileId=prof_id, floodlightConfigurationId=fl_cfg_id).execute().get("floodlightActivities", [])
            items = []
            for a in acts:
                aid, aname = str(a.get("id")), a.get("name", "")
                rec, lbl = classify_tag(aname)
                prec, plbl = classify_product_tag(aname)
                items.append({
                    "id": aid,
                    "name": aname,
                    "recommended": rec,
                    "label": lbl,
                    "product_recommended": prec,
                    "product_label": plbl,
                })
            items.sort(key=lambda x: (0 if x["recommended"] else 1, x["name"].lower()))
            today_iso = datetime.date.today().isoformat()
            return self._send_json(200, {
                "account_id": str(prof.get("accountId", "")),
                "advertiser_id": adv_id,
                "advertiser_name": adv.get("name", ""),
                "fl_config_id": fl_cfg_id,
                "campaign_id": camp_id,
                "campaign_name": camp.get("name", ""),
                "start_date": camp.get("startDate", today_iso),
                "end_date": min(camp.get("endDate", today_iso), today_iso),
                "activities": items,
            })

        if path.startswith("/api/jobs/"):
            _, creds, owner = self._resolve_auth()
            if not creds:
                return self._send_json(401, {"error": "Não autenticado."})
            parts = path.strip("/").split("/")
            job_id = parts[2] if len(parts) >= 3 else ""
            action = parts[3] if len(parts) >= 4 else "status"
            with _STATE_LOCK:
                job = _JOBS.get(job_id)
            if not job or job["owner"] != owner:
                return self._send_json(404, {"error": "Estudo não encontrado."})

            if action == "status":
                with _STATE_LOCK:
                    snap = {k: job.get(k) for k in ("status", "step", "logs", "summary", "error")}
                return self._send_json(200, snap)

            if action == "stream":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                try:
                    while True:
                        with _STATE_LOCK:
                            snap = {k: job.get(k) for k in ("status", "step", "logs", "summary", "error")}
                        self.wfile.write(f"data: {json.dumps(snap, ensure_ascii=False)}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        if snap["status"] in ("done", "error"):
                            break
                        time.sleep(1.0)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                return

            if action == "report":
                html_path = job.get("html_path")
                if not html_path or not Path(html_path).exists():
                    return self._send_json(404, {"error": "Relatório ainda não disponível."})
                content = Path(html_path).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                if (qs.get("download") or ["0"])[0] == "1":
                    self.send_header("Content-Disposition", f'attachment; filename="{job["filename"]}"')
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        self._send_json(404, {"error": "Rota não encontrada."})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        _gc_stale_state()

        if parsed.path == "/api/jobs":
            _, creds, owner = self._resolve_auth()
            if not creds:
                return self._send_json(401, {"error": "Não autenticado."})
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not payload.get("profile_id") or not payload.get("campaign_id") or not payload.get("activities"):
                return self._send_json(400, {"error": "Selecione o perfil, a campanha e pelo menos 1 tag Floodlight."})

            job_id = secrets.token_urlsafe(12)
            work_dir = tempfile.mkdtemp(prefix=f"ctv_web_{job_id}_")
            with _STATE_LOCK:
                _JOBS[job_id] = {
                    "owner": owner, "work_dir": work_dir, "status": "running", "step": "Iniciando...",
                    "logs": [], "summary": None, "error": None, "html_path": None, "filename": None, "ts": time.time(),
                }
            threading.Thread(target=_run_pipeline_job, args=(job_id, creds, payload), daemon=True).start()
            return self._send_json(202, {"job_id": job_id})

        self._send_json(404, {"error": "Rota não encontrada."})


def run_server(host: str = "0.0.0.0", port: int | None = None):
    listen_port = port or int(os.environ.get("PORT", "8080"))
    srv = ThreadingHTTPServer((host, listen_port), CTVWebHandler)
    print(f"[CTV Compass] Servidor ativo em http://{host}:{listen_port}")
    srv.serve_forever()


if __name__ == "__main__":
    run_server()
