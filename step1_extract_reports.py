#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 1 — Unified CM360 v5 & DV360 Report Extraction (supports 'site' and 'device' modes)."""

import argparse
import datetime
import io
import json
import os
import time
import urllib.request
from pathlib import Path

import pandas as pd
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from common import (
    CM360_SCOPES,
    DEFAULT_CTV_PLATFORMS,
    DEFAULT_NON_CTV_PLATFORMS,
    DV360_SCOPES,
    execute_with_retry,
    get_mode,
    load_config,
    load_credentials,
    resolve_path,
)

REACH_METRICS_FULL = [
    "impressions",
    "impressionsCoviewed",
    "clicks",
    "mediaCost",
    "dv360Cost",
    "uniqueReachImpressionReach",
    "uniqueReachImpressionReachCoviewed",
    "uniqueReachAverageImpressionFrequency",
    "uniqueReachAverageImpressionFrequencyCoviewed",
    "uniqueReachClickReach",
    "uniqueReachTotalReach",
    "uniqueReachTotalReachCoviewed",
]
REACH_OVERLAP_METRICS = [
    "impressions",
    "clicks",
    "mediaCost",
    "uniqueReachExclusiveImpressionReach",
    "uniqueReachExclusiveImpressionReachPercent",
    "uniqueReachDuplicateImpressionReach",
    "uniqueReachDuplicateImpressionReachPercent",
    "uniqueReachExclusiveTotalReach",
    "uniqueReachExclusiveTotalReachPercent",
    "uniqueReachDuplicateTotalReach",
    "uniqueReachDuplicateTotalReachPercent",
    "totalConversions",
    "totalConversionsRevenue",
    "activityViewThroughConversions",
    "activityClickThroughConversions",
]


def _download_cm360_file(service, report_id: str, file_id: str, dest_path: Path) -> int:
    req = service.files().get_media(reportId=report_id, fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req, chunksize=10 * 1024 * 1024)
    done = False
    while not done:
        _, done = dl.next_chunk()
    dest_path.write_bytes(buf.getvalue())
    return dest_path.stat().st_size


def _p2c_spec(key, prefix, slug, ts, start_date, end_date, fl_config_id, act_ids, device_enriched: bool):
    conv_dims = [
        {"name": "conversionId", "sortOrder": "ASCENDING"},
        {"name": "activity", "sortOrder": "ASCENDING"},
        {"name": "activityId", "sortOrder": "ASCENDING"},
        {"name": "activityTime", "sortOrder": "ASCENDING"},
        {"name": "floodlightAttributionType", "sortOrder": "ASCENDING"},
        {"name": "daysSinceFirstInteraction", "sortOrder": "ASCENDING"},
        {"name": "pathLength", "sortOrder": "ASCENDING"},
    ]
    inter_dims = [
        {"name": "interactionTime", "sortOrder": "ASCENDING"},
        {"name": "interactionNumber", "sortOrder": "ASCENDING"},
        {"name": "interactionType", "sortOrder": "ASCENDING"},
        {"name": "site", "sortOrder": "ASCENDING"},
        {"name": "campaign", "sortOrder": "ASCENDING"},
        {"name": "campaignId", "sortOrder": "ASCENDING"},
        {"name": "placement", "sortOrder": "ASCENDING"},
        {"name": "placementId", "sortOrder": "ASCENDING"},
    ]
    if device_enriched:
        conv_dims.append({"name": "platformType", "sortOrder": "ASCENDING"})
        inter_dims.extend([
            {"name": "ad", "sortOrder": "ASCENDING"},
            {"name": "adId", "sortOrder": "ASCENDING"},
        ])
    return {
        "key": key,
        "filename": f"{prefix}_{ts}_cm360_{key}.csv",
        "body": {
            "name": f"CTV_{slug}_{key}_{ts}",
            "type": "PATH_TO_CONVERSION",
            "format": "CSV",
            "pathToConversionCriteria": {
                "dateRange": {"startDate": start_date, "endDate": end_date},
                "floodlightConfigId": {"dimensionName": "floodlightConfigId", "value": fl_config_id, "matchType": "EXACT"},
                "activityFilters": [{"dimensionName": "activity", "id": aid, "matchType": "EXACT"} for aid in act_ids],
                "conversionDimensions": conv_dims,
                "perInteractionDimensions": inter_dims,
                "metricNames": ["totalConversions", "totalConversionsRevenue"],
                "reportProperties": {
                    "maximumClickInteractions": 100,
                    "maximumImpressionInteractions": 100,
                    "pivotOnInteractionPath": False,
                    "includeUnattributedCookieConversions": False,
                    "includeUnattributedIPConversions": False,
                },
            },
        },
    }


def _reach_spec(key, prefix, slug, ts, start_date, end_date, dims, metrics, filters):
    return {
        "key": key,
        "filename": f"{prefix}_{ts}_cm360_{key}.csv",
        "body": {
            "name": f"CTV_{slug}_{key}_{ts}",
            "type": "REACH",
            "format": "CSV",
            "reachCriteria": {
                "dateRange": {"startDate": start_date, "endDate": end_date},
                "dimensions": [{"name": d} for d in dims],
                "metricNames": metrics,
                "dimensionFilters": filters,
            },
        },
    }


def _std_spec(key, prefix, slug, ts, start_date, end_date, dims, metrics, filters):
    return {
        "key": key,
        "filename": f"{prefix}_{ts}_cm360_{key}.csv",
        "body": {
            "name": f"CTV_{slug}_{key}_{ts}",
            "type": "STANDARD",
            "format": "CSV",
            "criteria": {
                "dateRange": {"startDate": start_date, "endDate": end_date},
                "dimensions": [{"name": d} for d in dims],
                "metricNames": metrics,
                "dimensionFilters": filters,
            },
        },
    }


def _build_cm360_specs(cfg: dict, mode: str, ts: str) -> list[dict]:
    slug = cfg["case_slug"]
    cm_cfg = cfg["cm360"]
    sd, ed = cfg["date_window"]["start_date"], cfg["date_window"]["end_date"]
    adv_id, camp_id = str(cm_cfg["advertiser_id"]), str(cm_cfg["campaign_id"])
    fl_id = str(cm_cfg["floodlight_config_id"])
    act_ids = [str(x) for x in cm_cfg["purchase_activity_ids"]]
    camp_filters = [
        {"dimensionName": "advertiser", "id": adv_id, "matchType": "EXACT"},
        {"dimensionName": "campaign", "id": camp_id, "matchType": "EXACT"},
    ]

    if mode == "site":
        p = "NEW"
        return [
            _std_spec(
                "std_site_cost_conv", p, slug, ts, sd, ed,
                ["campaign", "campaignId", "site", "placement", "placementId"],
                ["impressions", "clicks", "dv360Cost", "dv360CostUsd", "mediaCost", "totalConversions",
                 "totalConversionsRevenue", "activityViewThroughConversions", "activityClickThroughConversions",
                 "videoFirstQuartileCompletions", "videoMidpoints", "videoThirdQuartileCompletions", "videoCompletions"],
                camp_filters,
            ),
            _std_spec(
                "std_floodlight_activities", p, slug, ts, sd, ed,
                ["campaign", "campaignId", "site", "eventPlatformType", "activityGroup", "activity", "activityId"],
                ["totalConversions", "totalConversionsRevenue", "activityViewThroughConversions",
                 "activityClickThroughConversions", "activityViewThroughRevenue", "activityClickThroughRevenue"],
                camp_filters,
            ),
            _reach_spec("reach_campaign_total", p, slug, ts, sd, ed, ["campaign"], REACH_METRICS_FULL, camp_filters),
            _reach_spec("reach_site_coviewed", p, slug, ts, sd, ed, ["campaign", "site"], REACH_METRICS_FULL, camp_filters),
            _reach_spec("reach_site_overlap", p, slug, ts, sd, ed, ["campaign", "site"], REACH_OVERLAP_METRICS, camp_filters),
            _p2c_spec("p2c_14d", p, slug, ts, sd, ed, fl_id, act_ids, device_enriched=False),
        ]

    p = "NEWDEV"
    ctv_plats = cfg.get("ctv_platform_types", DEFAULT_CTV_PLATFORMS)
    non_ctv_plats = cfg.get("non_ctv_platform_types", DEFAULT_NON_CTV_PLATFORMS)
    ctv_f = [{"dimensionName": "platformType", "id": str(x["id"]), "matchType": "EXACT"} for x in ctv_plats]
    non_f = [{"dimensionName": "platformType", "id": str(x["id"]), "matchType": "EXACT"} for x in non_ctv_plats]
    return [
        _std_spec(
            "std_device_site_placement_ad", p, slug, ts, sd, ed,
            ["campaign", "campaignId", "site", "placement", "placementId", "ad", "adId", "platformType"],
            ["impressions", "clicks", "dv360Cost", "dv360CostUsd", "mediaCost", "totalConversions",
             "totalConversionsRevenue", "activityViewThroughConversions", "activityClickThroughConversions"],
            camp_filters,
        ),
        _std_spec(
            "std_advertiser_device_map", p, slug, ts, sd, ed,
            ["campaign", "campaignId", "site", "placement", "placementId", "platformType"],
            ["impressions", "clicks"],
            [{"dimensionName": "advertiser", "id": adv_id, "matchType": "EXACT"}],
        ),
        _std_spec(
            "std_device_floodlights", p, slug, ts, sd, ed,
            ["campaign", "campaignId", "site", "placement", "placementId", "platformType", "activityGroup", "activity", "activityId"],
            ["totalConversions", "totalConversionsRevenue", "activityViewThroughConversions",
             "activityClickThroughConversions", "activityViewThroughRevenue", "activityClickThroughRevenue"],
            camp_filters,
        ),
        _std_spec(
            "std_event_platform_floodlights", p, slug, ts, sd, ed,
            ["campaign", "campaignId", "site", "eventPlatformType", "activityGroup", "activity", "activityId"],
            ["totalConversions", "totalConversionsRevenue", "activityViewThroughConversions",
             "activityClickThroughConversions", "activityViewThroughRevenue", "activityClickThroughRevenue"],
            camp_filters,
        ),
        _reach_spec("reach_campaign_total", p, slug, ts, sd, ed, ["campaign"], REACH_METRICS_FULL, camp_filters),
        _reach_spec("reach_by_platform", p, slug, ts, sd, ed, ["platformType"], REACH_METRICS_FULL, camp_filters),
        _reach_spec("reach_ctv_devices_block", p, slug, ts, sd, ed, ["campaign"], REACH_METRICS_FULL, camp_filters + ctv_f),
        _reach_spec("reach_nonctv_devices_block", p, slug, ts, sd, ed, ["campaign"], REACH_METRICS_FULL, camp_filters + non_f),
        _reach_spec("reach_site_by_platform", p, slug, ts, sd, ed, ["site", "platformType"], REACH_METRICS_FULL, camp_filters),
        _reach_spec("reach_site_ctv_devices", p, slug, ts, sd, ed, ["site"], REACH_METRICS_FULL, camp_filters + ctv_f),
        _reach_spec("reach_site_nonctv_devices", p, slug, ts, sd, ed, ["site"], REACH_METRICS_FULL, camp_filters + non_f),
        _reach_spec("reach_site_all_coviewed", p, slug, ts, sd, ed, ["site"], REACH_METRICS_FULL, camp_filters),
        _reach_spec("reach_site_overlap_all", p, slug, ts, sd, ed, ["site"], REACH_OVERLAP_METRICS, camp_filters),
        _p2c_spec("p2c_14d_device_enriched", p, slug, ts, sd, ed, fl_id, act_ids, device_enriched=True),
    ]


def _extract_dv360_optional(dv_cfg: dict, mode: str, slug: str, sd: str, ed: str, ts: str, raw_dir: Path) -> dict | None:
    if not dv_cfg.get("enabled"):
        return None
    try:
        dv_creds = load_credentials(dv_cfg.get("token_dv360_path", "token_dv360.json"), scopes=DV360_SCOPES)
    except FileNotFoundError:
        print("  [DV360] Token DV360 ausente — seguindo em modo 100% CM360 (DV360 Cost / Media Cost).")
        return None

    dbm = build("doubleclickbidmanager", "v2", credentials=dv_creds)
    dv4 = build("displayvideo", "v4", credentials=dv_creds)
    sy, sm, sday = [int(x) for x in sd.split("-")]
    ey, em, eday = [int(x) for x in ed.split("-")]
    base_gb = ["FILTER_ADVERTISER_CURRENCY", "FILTER_MEDIA_PLAN", "FILTER_INSERTION_ORDER", "FILTER_LINE_ITEM"]
    candidates = [base_gb + ["FILTER_DEVICE_TYPE"], base_gb] if mode in ("device", "both") else [base_gb]

    q_created, used_gb = None, base_gb
    for gb in candidates:
        try:
            q_created = dbm.queries().create(body={
                "metadata": {
                    "title": f"CTV_{slug}_dv360_{mode}_{ts}",
                    "dataRange": {
                        "range": "CUSTOM_DATES",
                        "customStartDate": {"year": sy, "month": sm, "day": sday},
                        "customEndDate": {"year": ey, "month": em, "day": eday},
                    },
                    "format": "CSV",
                },
                "params": {
                    "type": "STANDARD",
                    "groupBys": gb,
                    "filters": [{"type": "FILTER_ADVERTISER", "value": str(dv_cfg["advertiser_id"])}],
                    "metrics": ["METRIC_IMPRESSIONS", "METRIC_CLICKS", "METRIC_REVENUE_ADVERTISER", "METRIC_MEDIA_COST_ADVERTISER"],
                },
                "schedule": {"frequency": "ONE_TIME"},
            }).execute()
            used_gb = gb
            break
        except Exception as e:
            print(f"  [DV360] groupBys {gb} recusado ({e}), tentando fallback...")

    qid = q_created["queryId"]
    rep_run = execute_with_retry(lambda: dbm.queries().run(queryId=qid, body={}))
    rep_id = rep_run["key"]["reportId"]
    print(f"  [DV360] Query disparada: queryId={qid}, reportId={rep_id}")

    raw_dv = raw_dir / f"DV_{ts}_raw.csv"
    while True:
        r_stat = dbm.queries().reports().get(queryId=qid, reportId=rep_id).execute()
        state = r_stat.get("metadata", {}).get("status", {}).get("state", "")
        if state == "DONE":
            urllib.request.urlretrieve(r_stat["metadata"]["googleCloudStoragePath"], str(raw_dv))
            break
        if state == "FAILED":
            raise RuntimeError(f"Relatório DV360 falhou: {r_stat}")
        time.sleep(5)

    clean_lines = []
    for line in raw_dv.read_text(encoding="utf-8", errors="replace").splitlines(True):
        if not line.strip() or line.startswith(",,,,"):
            break
        clean_lines.append(line)
    df_dv = pd.read_csv(io.StringIO("".join(clean_lines)), dtype=str)
    if dv_cfg.get("campaign_id") and "Campaign ID" in df_dv.columns:
        df_dv = df_dv[df_dv["Campaign ID"] == str(dv_cfg["campaign_id"])].copy()

    adv_str = str(dv_cfg["advertiser_id"])
    for col, out_col, resource, param in [
        ("Insertion Order ID", "IO Name", dv4.advertisers().insertionOrders(), "insertionOrderId"),
        ("Line Item ID", "Line Item Name", dv4.advertisers().lineItems(), "lineItemId"),
    ]:
        if col in df_dv.columns:
            names = {}
            for obj_id in df_dv[col].dropna().unique():
                try:
                    names[str(obj_id)] = resource.get(**{"advertiserId": adv_str, param: str(obj_id)}).execute().get("displayName", "")
                except Exception:
                    names[str(obj_id)] = ""
            df_dv[out_col] = df_dv[col].map(names)

    out_name = f"DV_{ts}_dv360_enriched.csv"
    out_path = raw_dir / out_name
    df_dv.to_csv(out_path, index=False, encoding="utf-8")
    raw_dv.unlink(missing_ok=True)
    key_name = "cost_by_io_li_device" if mode in ("device", "both") else "cost_by_io_li"
    return {key_name: {"queryId": qid, "reportId": rep_id, "groupBys": used_gb, "path": f"raw_reports/{out_name}", "rows": int(len(df_dv))}}


def extract_reports(config_path: str, mode_override: str | None = None) -> str:
    cfg = load_config(config_path, mode_override=mode_override)
    mode = get_mode(cfg)
    cm_cfg = cfg["cm360"]
    sd, ed = cfg["date_window"]["start_date"], cfg["date_window"]["end_date"]
    out_dir = Path(cfg["output_dir"])
    raw_dir = out_dir / "raw_reports"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")

    print("=" * 70)
    print(f"[ETAPA 1 - MODO {mode.upper()}] Extraindo Relatórios CM360/DV360: {cfg['brand_name']}")
    print(f"Campanha CM360: {cm_cfg['campaign_name']} (ID: {cm_cfg['campaign_id']}) | {sd} a {ed}")
    print("=" * 70)

    cm_creds = load_credentials(cm_cfg.get("token_reporting_path", "token.json"), scopes=CM360_SCOPES)
    cm_service = build("dfareporting", "v5", credentials=cm_creds)
    profile_id = str(cm_cfg["profile_id"])

    specs = _build_cm360_specs(cfg, mode, ts)
    pending = {}
    for spec in specs:
        k = spec["key"]
        created = execute_with_retry(lambda b=spec["body"]: cm_service.reports().insert(profileId=profile_id, body=b))
        rid = created["id"]
        time.sleep(0.3)
        rf = execute_with_retry(lambda r=rid: cm_service.reports().run(profileId=profile_id, reportId=r))
        fid = rf["id"]
        print(f"  [CM360 DISPARADO] {k}: reportId={rid}, fileId={fid}")
        pending[k] = {"reportId": rid, "fileId": fid, "filename": spec["filename"], "status": "PROCESSING"}
        time.sleep(0.3)

    manifest = {
        "case_slug": cfg["case_slug"],
        "identification_mode": mode,
        "generated_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "date_window": {"start_date": sd, "end_date": ed},
        "cm360_reports": {},
        "dv360_reports": _extract_dv360_optional(cfg.get("dv360", {}), mode, cfg["case_slug"], sd, ed, ts, raw_dir) or {},
    }

    start_poll = time.time()
    while True:
        waiting = []
        for k, info in pending.items():
            if info["status"] == "DONE":
                continue
            f_stat = execute_with_retry(lambda r=info["reportId"], f=info["fileId"]: cm_service.files().get(reportId=r, fileId=f))
            st = f_stat.get("status", "")
            if st == "REPORT_AVAILABLE":
                dest = raw_dir / info["filename"]
                sz = _download_cm360_file(cm_service, info["reportId"], info["fileId"], dest)
                info["status"] = "DONE"
                manifest["cm360_reports"][k] = {
                    "reportId": info["reportId"],
                    "fileId": info["fileId"],
                    "path": f"raw_reports/{info['filename']}",
                    "bytes": sz,
                }
                print(f"  [CM360 BAIXADO em {int(time.time() - start_poll)}s] {k} ({sz:,} bytes)")
            elif st in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"Relatório CM360 {k} ({info['reportId']}) falhou: {st}")
            else:
                waiting.append(f"{k}({st})")
        if not waiting:
            break
        print(f"  ... [{int(time.time() - start_poll)}s] aguardando: {', '.join(waiting)}")
        time.sleep(15)

    m_name = "extraction_manifest_device.json" if mode in ("device", "both") else "extraction_manifest.json"
    m_path = out_dir / m_name
    m_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ETAPA 1 CONCLUÍDA] Manifesto salvo em: {m_path}")
    return str(m_path)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Extração unificada de relatórios CM360 e DV360")
    p.add_argument("--config", required=True, help="Caminho para o JSON de configuração")
    p.add_argument("--mode", choices=["both", "site", "device"], default=None, help="Sobrescrever modo (both | site | device)")
    a = p.parse_args()
    extract_reports(a.config, mode_override=a.mode)
