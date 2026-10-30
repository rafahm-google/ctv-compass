#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 2 — Unified CTV Measurement Engine ('site' and 'device' modes) with 5 Mathematical Locks."""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from common import (
    clean_id_str,
    clean_num,
    fmt_curr,
    fmt_dec,
    fmt_int,
    fmt_pct,
    get_mode,
    load_config,
    norm_slug,
    read_cm360_csv,
    read_p2c_csv,
    resolve_path,
)

CTV_PLATFORM_NAMES = {"Connected TV", "Set top box"}
PURE_CTV_PLACEMENT_THRESHOLD = 0.95
MIN_MEANINGFUL_CTV_IMPS = 1000.0


def _report_file(out_dir: Path, raw_path: str) -> Path:
    p = Path(raw_path)
    if p.is_absolute() and p.exists():
        return p
    cand = out_dir / p
    if cand.exists():
        return cand
    fallback = out_dir / "raw_reports" / p.name
    if fallback.exists():
        return fallback
    raise FileNotFoundError(f"Arquivo de relatório não encontrado: {raw_path}")


def _scalar_num(row, col: str, default=0.0):
    v = clean_num(pd.Series([row.get(col)])).iloc[0]
    return default if pd.isna(v) else float(v)


def _parse_reach_totals(path: Path) -> tuple[float, float, float, float]:
    df = read_cm360_csv(path)
    if df.empty:
        return 0.0, 0.0, 1.0, 1.0
    r = df.iloc[0]
    return (
        _scalar_num(r, "Unique Reach: Impression Reach", 0.0),
        _scalar_num(r, "Unique Reach: Impression Reach (Co-Viewed)", 0.0),
        _scalar_num(r, "Unique Reach: Average Impression Frequency", 1.0),
        _scalar_num(r, "Unique Reach: Average Impression Frequency (Co-Viewed)", 1.0),
    )


def _parse_site_reach_map(path: Path, none_if_missing: bool = False) -> dict:
    df = read_cm360_csv(path)
    miss = None if none_if_missing else 0.0
    out = {}
    for _, r in df.iterrows():
        s = str(r["Site (CM360)"]).strip()
        out[s] = {
            "unique_reach": _scalar_num(r, "Unique Reach: Impression Reach", miss),
            "coviewed_reach": _scalar_num(r, "Unique Reach: Impression Reach (Co-Viewed)", miss),
            "avg_freq": _scalar_num(r, "Unique Reach: Average Impression Frequency", 1.0),
        }
    return out


def _parse_site_overlap_map(path: Path) -> dict:
    df = read_cm360_csv(path)
    out = {}
    for _, r in df.iterrows():
        s = str(r["Site (CM360)"]).strip()
        out[s] = {
            "excl": _scalar_num(r, "Unique Reach: Exclusive Impression Reach", 0.0),
            "excl_pct": _scalar_num(r, "Unique Reach: Exclusive Impression Reach Percent", None),
            "dupl": _scalar_num(r, "Unique Reach: Duplicate Impression Reach", 0.0),
            "dupl_pct": _scalar_num(r, "Unique Reach: Duplicate Impression Reach Percent", None),
        }
    return out


def _analyze_p2c(p2c_path: Path, camp_id: str, norm_kw: str, purchase_ids: list[int], classify_ctv_fn, strict_combo_nonctv: bool):
    df_raw = read_p2c_csv(p2c_path)
    df_raw["Activity ID"] = clean_num(df_raw["Activity ID"]).fillna(-1).astype(int)
    df_raw = df_raw[df_raw["Activity ID"].isin(purchase_ids)].copy()

    conv_totals = df_raw[df_raw["Interaction Number"].isna()].copy()
    conv_totals["Total Conversions"] = clean_num(conv_totals["Total Conversions"]).fillna(0.0)
    conv_totals["Total Revenue"] = clean_num(conv_totals["Total Revenue"]).fillna(0.0)

    paths_df = df_raw[df_raw["Interaction Number"].notna()].copy()
    paths_df["camp_id_str"] = clean_id_str(paths_df["Campaign ID"])
    paths_df["plc_id_str"] = clean_id_str(paths_df["Placement ID"]) if "Placement ID" in paths_df.columns else ""
    paths_df["ad_id_str"] = clean_id_str(paths_df["Ad ID"]) if "Ad ID" in paths_df.columns else ""
    paths_df["site_clean"] = paths_df["Site (CM360)"].fillna("").astype(str).str.strip()
    paths_df["norm_camp"] = paths_df["Campaign"].fillna("").map(norm_slug)
    paths_df["Interaction Number"] = clean_num(paths_df["Interaction Number"])
    paths_df = paths_df.sort_values(["Conversion ID", "Interaction Number"], ascending=[True, False])

    paths_df["is_target_camp"] = paths_df["camp_id_str"] == camp_id
    paths_df["is_other_agency"] = (paths_df["norm_camp"].str.contains(norm_kw, regex=False) | paths_df["is_target_camp"]) & (~paths_df["is_target_camp"])
    paths_df = classify_ctv_fn(paths_df)

    target_cids = set(paths_df[paths_df["is_target_camp"]]["Conversion ID"].unique())
    shared_cids = target_cids.intersection(set(paths_df[paths_df["is_other_agency"]]["Conversion ID"].unique()))

    target_conv_df = conv_totals[conv_totals["Conversion ID"].isin(target_cids)].copy()
    p2c_convs = float(target_conv_df["Total Conversions"].sum())
    p2c_rev = float(target_conv_df["Total Revenue"].sum())
    p2c_aov = (p2c_rev / p2c_convs) if p2c_convs > 0 else 0.0

    checkout_breakdown = []
    if "Platform Type" in target_conv_df.columns:
        target_conv_df["checkout_platform"] = target_conv_df["Platform Type"].fillna("Unknown platform").astype(str).str.strip()
        chk_grp = target_conv_df.groupby("checkout_platform", as_index=False).agg(
            conversions=("Total Conversions", "sum"), revenue=("Total Revenue", "sum")
        ).sort_values("conversions", ascending=False)
        checkout_breakdown = [
            {
                "platform_type": str(r["checkout_platform"]),
                "conversions": float(r["conversions"]),
                "share_pct": (float(r["conversions"]) / p2c_convs * 100.0) if p2c_convs > 0 else 0.0,
                "revenue": float(r["revenue"]),
            }
            for _, r in chk_grp.iterrows()
        ]

    target_touches = paths_df[paths_df["Conversion ID"].isin(target_cids)].copy()
    cid_stats = {}
    for cid, grp in target_touches.groupby("Conversion ID", sort=False):
        camp_grp = grp[grp["is_target_camp"]]
        ctv_all = set(grp[grp["is_ctv_touch"]]["site_clean"])
        ctv_camp = set(camp_grp[camp_grp["is_ctv_touch"]]["site_clean"])
        non_ctv_t_all = int((~grp["is_ctv_touch"]).sum())
        non_ctv_t_camp = int((~camp_grp["is_ctv_touch"]).sum())
        cid_stats[cid] = {
            "total_touches_all": len(grp),
            "unique_all_sites": set(grp["site_clean"]),
            "unique_camp_sites": set(camp_grp["site_clean"]),
            "ctv_sites_all": ctv_all,
            "ctv_sites_camp": ctv_camp,
            "non_ctv_sites_camp": set(camp_grp[~camp_grp["is_ctv_touch"]]["site_clean"]),
            "all_touches_are_ctv": non_ctv_t_all == 0 and len(grp) > 0,
            "non_ctv_touches_all": non_ctv_t_all,
            "non_ctv_touches_camp": non_ctv_t_camp,
        }

    for k, fn in [
        ("total_touches_all", lambda s: s["total_touches_all"]),
        ("non_ctv_touches_all", lambda s: s["non_ctv_touches_all"]),
        ("non_ctv_touches_camp", lambda s: s["non_ctv_touches_camp"]),
        ("has_any_ctv_all", lambda s: len(s["ctv_sites_all"]) > 0),
        ("has_any_ctv_camp", lambda s: len(s["ctv_sites_camp"]) > 0),
        ("has_non_ctv_camp", lambda s: s["non_ctv_touches_camp"] > 0),
    ]:
        target_conv_df[k] = target_conv_df["Conversion ID"].map(lambda c, f=fn: f(cid_stats[c]))

    def _cohort_metrics(df_sub, touch_col, fallback_aov):
        convs = float(df_sub["Total Conversions"].sum())
        rev = float(df_sub["Total Revenue"].sum())
        return {
            "conversions": convs,
            "revenue": rev,
            "aov": (rev / convs) if convs > 0 else fallback_aov,
            "avg_non_ctv_touches": float(df_sub[touch_col].mean()) if len(df_sub) > 0 else 0.0,
        }

    ctrl_all = _cohort_metrics(target_conv_df[(~target_conv_df["has_any_ctv_all"]) & (target_conv_df["total_touches_all"] > 1)], "non_ctv_touches_all", p2c_aov)
    ctrl_camp = _cohort_metrics(target_conv_df[(~target_conv_df["has_any_ctv_camp"]) & (target_conv_df["non_ctv_touches_camp"] > 1)], "non_ctv_touches_camp", p2c_aov)

    combo_mask = target_conv_df["has_any_ctv_camp"] & (target_conv_df["total_touches_all"] > 1)
    if strict_combo_nonctv:
        combo_mask = combo_mask & (target_conv_df["non_ctv_touches_all"] > 0)
    combo_all = _cohort_metrics(target_conv_df[combo_mask], "non_ctv_touches_all", p2c_aov)
    combo_camp = _cohort_metrics(target_conv_df[target_conv_df["has_any_ctv_camp"] & target_conv_df["has_non_ctv_camp"]], "non_ctv_touches_camp", combo_all["aov"])

    blk_lift_val = (
        max(0.0, (combo_camp["aov"] - ctrl_camp["aov"]) / combo_camp["aov"] * 100.0)
        if combo_camp["conversions"] >= 5
        else (max(0.0, (combo_all["aov"] - ctrl_all["aov"]) / combo_all["aov"] * 100.0) if combo_all["aov"] > 0 else 0.0)
    )
    if combo_all["conversions"] >= 5 and ctrl_all["avg_non_ctv_touches"] > 0:
        blk_lift_efic = max(0.0, (ctrl_all["avg_non_ctv_touches"] - combo_all["avg_non_ctv_touches"]) / ctrl_all["avg_non_ctv_touches"] * 100.0)
    elif not strict_combo_nonctv and combo_camp["conversions"] > 0 and ctrl_camp["avg_non_ctv_touches"] > 0:
        blk_lift_efic = max(0.0, (ctrl_camp["avg_non_ctv_touches"] - combo_camp["avg_non_ctv_touches"]) / ctrl_camp["avg_non_ctv_touches"] * 100.0)
    else:
        blk_lift_efic = 0.0

    return {
        "paths_df": paths_df,
        "target_touches": target_touches,
        "target_cids": target_cids,
        "shared_cids": shared_cids,
        "target_conv_df": target_conv_df,
        "cid_stats": cid_stats,
        "p2c_journeys": len(target_cids),
        "p2c_conversions": p2c_convs,
        "p2c_revenue": p2c_rev,
        "p2c_aov": p2c_aov,
        "checkout_breakdown": checkout_breakdown,
        "ctrl_all": ctrl_all,
        "ctrl_camp": ctrl_camp,
        "combo_all": combo_all,
        "combo_camp": combo_camp,
        "blk_lift_val": blk_lift_val,
        "blk_lift_efic": blk_lift_efic,
    }


def _value_channel(solo_convs: float, solo_rev: float, intersecao_compras: float, lift_efic_pct: float,
                   aov_with_ctv: float, base_ctrl_aov: float, cost: float, p2c_total_convs: float) -> dict:
    aov_delta_brl = max(0.0, aov_with_ctv - base_ctrl_aov)
    effective_base_aov = min(base_ctrl_aov, aov_with_ctv)
    assisted_convs = intersecao_compras * (lift_efic_pct / 100.0)
    tot_convs = solo_convs + assisted_convs
    base_rev = assisted_convs * effective_base_aov
    prem_rev = assisted_convs * aov_delta_brl
    tot_rev = solo_rev + base_rev + prem_rev
    return {
        "aov_valuation": aov_with_ctv,
        "base_ctrl_aov": base_ctrl_aov,
        "aov_delta_brl": aov_delta_brl,
        "assisted_conversions": assisted_convs,
        "total_attributed_conversions": tot_convs,
        "share_campaign_attributed_pct": (tot_convs / p2c_total_convs * 100.0) if p2c_total_convs > 0 else 0.0,
        "assisted_base_revenue": base_rev,
        "aov_premium_revenue": prem_rev,
        "total_attributed_revenue": tot_rev,
        "cpa_attributed": (cost / tot_convs) if (cost > 0 and tot_convs > 0) else None,
        "roas_attributed": (tot_rev / cost) if cost > 0 else None,
    }


def _summarize_dv360(dv_cfg: dict, manifest: dict, out_dir: Path) -> dict:
    dv_reports = manifest.get("dv360_reports", {})
    key = "cost_by_io_li_device" if "cost_by_io_li_device" in dv_reports else ("cost_by_io_li" if "cost_by_io_li" in dv_reports else None)
    if not (dv_cfg.get("enabled") and key):
        return {"enabled": False, "total_revenue_adv": 0.0, "total_media_cost": 0.0}
    try:
        dv_path = _report_file(out_dir, dv_reports[key]["path"])
    except FileNotFoundError:
        return {"enabled": False, "total_revenue_adv": 0.0, "total_media_cost": 0.0}

    df_dv = pd.read_csv(dv_path)
    for col in ["Impressions", "Clicks", "Revenue (Adv Currency)", "Media Cost (Advertiser Currency)"]:
        if col in df_dv.columns:
            df_dv[col] = clean_num(df_dv[col]).fillna(0.0)
    out = {
        "enabled": True,
        "total_revenue_adv": float(df_dv["Revenue (Adv Currency)"].sum()) if "Revenue (Adv Currency)" in df_dv.columns else 0.0,
        "total_media_cost": float(df_dv["Media Cost (Advertiser Currency)"].sum()) if "Media Cost (Advertiser Currency)" in df_dv.columns else 0.0,
        "total_impressions": float(df_dv["Impressions"].sum()) if "Impressions" in df_dv.columns else 0.0,
    }
    if "IO Name" in df_dv.columns:
        out["ios"] = df_dv.groupby(["Insertion Order ID", "IO Name"], as_index=False).agg(
            impressions=("Impressions", "sum"), clicks=("Clicks", "sum"),
            revenue_adv=("Revenue (Adv Currency)", "sum"), media_cost=("Media Cost (Advertiser Currency)", "sum"),
        ).sort_values("revenue_adv", ascending=False).to_dict(orient="records")
    if "Device Type" in df_dv.columns:
        out["by_device_type"] = df_dv.groupby("Device Type", as_index=False).agg(
            impressions=("Impressions", "sum"), clicks=("Clicks", "sum"), revenue_adv=("Revenue (Adv Currency)", "sum"),
        ).sort_values("revenue_adv", ascending=False).to_dict(orient="records")
    return out


def _compute_site_mode(cfg: dict, manifest: dict, out_dir: Path) -> str:
    cm_cfg = cfg["cm360"]
    camp_id = str(cm_cfg["campaign_id"])
    camp_name = cm_cfg["campaign_name"]
    norm_kw = cm_cfg.get("brand_keyword_normalized") or norm_slug(camp_name)
    purchase_ids = [int(x) for x in cm_cfg["purchase_activity_ids"]]
    sd, ed = cfg["date_window"]["start_date"], cfg["date_window"]["end_date"]

    rpts = manifest["cm360_reports"]
    std_key = "std_site_cost_conv" if "std_site_cost_conv" in rpts else "std_device_site_placement_ad"
    fl_key = "std_floodlight_activities" if "std_floodlight_activities" in rpts else "std_device_floodlights"
    cov_key = "reach_site_coviewed" if "reach_site_coviewed" in rpts else "reach_site_all_coviewed"
    ovl_key = "reach_site_overlap" if "reach_site_overlap" in rpts else "reach_site_overlap_all"
    p2c_key = "p2c_14d" if "p2c_14d" in rpts else "p2c_14d_device_enriched"

    df_cost = read_cm360_csv(_report_file(out_dir, rpts[std_key]["path"]))
    df_cost = df_cost[clean_id_str(df_cost["Campaign ID"]) == camp_id].copy()
    for col in ["Impressions", "Clicks", "DV360 Cost (Account Currency)", "Media Cost"]:
        if col in df_cost.columns:
            df_cost[col] = clean_num(df_cost[col]).fillna(0.0)

    df_fl = read_cm360_csv(_report_file(out_dir, rpts[fl_key]["path"]))
    df_fl["Activity ID"] = clean_num(df_fl["Activity ID"]).fillna(-1).astype(int)
    df_fl = df_fl[(clean_id_str(df_fl["Campaign ID"]) == camp_id) & (df_fl["Activity ID"].isin(purchase_ids))].copy()
    for col in ["Total Conversions", "Total Revenue", "View-through Conversions", "Click-through Conversions"]:
        if col in df_fl.columns:
            df_fl[col] = clean_num(df_fl[col]).fillna(0.0)

    df_sites = pd.merge(
        df_cost.groupby("Site (CM360)", as_index=False).agg(
            impressions=("Impressions", "sum"), clicks=("Clicks", "sum"),
            dv360_cost=("DV360 Cost (Account Currency)", "sum"), media_cost=("Media Cost", "sum"),
        ),
        df_fl.groupby("Site (CM360)", as_index=False).agg(
            std_conversions=("Total Conversions", "sum"), std_revenue=("Total Revenue", "sum"),
            std_vt_conversions=("View-through Conversions", "sum"), std_ct_conversions=("Click-through Conversions", "sum"),
        ),
        on="Site (CM360)", how="outer",
    ).fillna(0.0)
    df_sites["effective_cost"] = np.where(df_sites["dv360_cost"] > 0, df_sites["dv360_cost"], df_sites["media_cost"])
    df_sites["is_ctv"] = df_sites["Site (CM360)"].astype(str).str.lower().str.contains("ctv")

    camp_reach_dev, camp_reach_cov, camp_freq, camp_freq_cov = _parse_reach_totals(
        _report_file(out_dir, rpts["reach_campaign_total"]["path"])
    )
    cov_map = _parse_site_reach_map(_report_file(out_dir, rpts[cov_key]["path"]), none_if_missing=True)
    ovl_map = _parse_site_overlap_map(_report_file(out_dir, rpts[ovl_key]["path"]))

    def _site_classifier(df_p):
        df_p["is_ctv_touch"] = df_p["site_clean"].str.lower().str.contains("ctv")
        return df_p

    p2c = _analyze_p2c(
        _report_file(out_dir, rpts[p2c_key]["path"]),
        camp_id, norm_kw, purchase_ids, _site_classifier, strict_combo_nonctv=False,
    )
    cid_stats, t_conv_df = p2c["cid_stats"], p2c["target_conv_df"]
    ctrl_all, ctrl_camp, combo_all, combo_camp = p2c["ctrl_all"], p2c["ctrl_camp"], p2c["combo_all"], p2c["combo_camp"]

    std_tot_cost = float(df_sites["effective_cost"].sum())
    std_tot_imps = float(df_sites["impressions"].sum())
    std_tot_clicks = float(df_sites["clicks"].sum())
    std_tot_convs = float(df_sites["std_conversions"].sum())
    std_tot_rev = float(df_sites["std_revenue"].sum())

    ctv_channels = []
    for s in sorted(df_sites[df_sites["is_ctv"]]["Site (CM360)"].tolist()):
        row_s = df_sites[df_sites["Site (CM360)"] == s].iloc[0]
        s_cost, s_imps, s_clicks = float(row_s["effective_cost"]), float(row_s["impressions"]), float(row_s["clicks"])
        c_info, o_info = cov_map.get(s, {}), ovl_map.get(s, {})
        excl_1p, dupl_1p = o_info.get("excl", 0.0), o_info.get("dupl", 0.0)
        u_reach = c_info.get("unique_reach") or ((excl_1p + dupl_1p) if (excl_1p + dupl_1p) > 0 else 0.0)
        c_reach = c_info.get("coviewed_reach") or u_reach
        cov_factor = (c_reach / u_reach) if u_reach > 0 else 1.0
        dupl_pct_site = o_info.get("dupl_pct") if o_info.get("dupl_pct") is not None else ((dupl_1p / u_reach * 100.0) if u_reach > 0 else 0.0)
        excl_pct_site = o_info.get("excl_pct") if o_info.get("excl_pct") is not None else ((excl_1p / u_reach * 100.0) if u_reach > 0 else 0.0)
        ovl_pct_camp = (dupl_1p / camp_reach_dev * 100.0) if camp_reach_dev > 0 else 0.0
        excl_pct_camp = (excl_1p / camp_reach_dev * 100.0) if camp_reach_dev > 0 else 0.0
        intersecao_compras = p2c["p2c_conversions"] * (ovl_pct_camp / 100.0)

        cids_s = [c for c in p2c["target_cids"] if s in cid_stats[c]["ctv_sites_camp"]]
        df_solo = t_conv_df[t_conv_df["Conversion ID"].isin([c for c in cids_s if len(cid_stats[c]["unique_all_sites"]) == 1 and s in cid_stats[c]["unique_all_sites"]])]
        df_c_all = t_conv_df[t_conv_df["Conversion ID"].isin([c for c in cids_s if len(cid_stats[c]["unique_all_sites"]) > 1])]
        df_c_camp = t_conv_df[t_conv_df["Conversion ID"].isin([c for c in cids_s if len(cid_stats[c]["unique_camp_sites"]) > 1])]

        solo_convs, solo_rev = float(df_solo["Total Conversions"].sum()), float(df_solo["Total Revenue"].sum())
        c_all_convs, c_all_rev = float(df_c_all["Total Conversions"].sum()), float(df_c_all["Total Revenue"].sum())
        c_all_aov = (c_all_rev / c_all_convs) if c_all_convs > 0 else combo_all["aov"]
        c_all_touches = float(df_c_all["non_ctv_touches_all"].mean()) if len(df_c_all) > 0 else combo_all["avg_non_ctv_touches"]

        c_camp_convs, c_camp_rev = float(df_c_camp["Total Conversions"].sum()), float(df_c_camp["Total Revenue"].sum())
        c_camp_aov = (c_camp_rev / c_camp_convs) if c_camp_convs > 0 else c_all_aov
        c_camp_touches = float(df_c_camp["non_ctv_touches_camp"].mean()) if len(df_c_camp) > 0 else c_all_touches

        lift_efic = (
            max(0.0, (ctrl_all["avg_non_ctv_touches"] - c_all_touches) / ctrl_all["avg_non_ctv_touches"] * 100.0)
            if (c_all_convs >= 5 and ctrl_all["avg_non_ctv_touches"] > 0)
            else p2c["blk_lift_efic"]
        )
        base_ctrl_aov = ctrl_camp["aov"] if ctrl_camp["conversions"] >= 5 else ctrl_all["aov"]
        if c_camp_convs >= 5:
            aov_with_ctv = c_camp_aov
            lift_val_spec = max(0.0, (c_camp_aov - base_ctrl_aov) / c_camp_aov * 100.0)
        elif c_all_convs >= 5:
            aov_with_ctv = c_all_aov
            lift_val_spec = max(0.0, (c_all_aov - base_ctrl_aov) / c_all_aov * 100.0)
        else:
            aov_with_ctv = combo_camp["aov"] if combo_camp["conversions"] >= 5 else combo_all["aov"]
            lift_val_spec = p2c["blk_lift_val"]

        val = _value_channel(solo_convs, solo_rev, intersecao_compras, lift_efic, aov_with_ctv, base_ctrl_aov, s_cost, p2c["p2c_conversions"])
        ctv_channels.append({
            "site": s,
            "cost": s_cost,
            "cost_share_pct": (s_cost / std_tot_cost * 100.0) if std_tot_cost > 0 else 0.0,
            "impressions": s_imps,
            "clicks": s_clicks,
            "cpm": (s_cost / (s_imps / 1000.0)) if s_imps > 0 else 0.0,
            "ecpm_coview": (s_cost / ((s_imps * cov_factor) / 1000.0)) if s_imps > 0 else 0.0,
            "std_conversions": float(row_s["std_conversions"]),
            "std_vt_conversions": float(row_s["std_vt_conversions"]),
            "std_ct_conversions": float(row_s["std_ct_conversions"]),
            "std_revenue": float(row_s["std_revenue"]),
            "std_share_pct": (float(row_s["std_conversions"]) / std_tot_convs * 100.0) if std_tot_convs > 0 else 0.0,
            "unique_reach": u_reach,
            "coviewed_reach": c_reach,
            "coview_factor": cov_factor,
            "avg_freq": c_info.get("avg_freq") or 1.0,
            "exclusive_reach_1plus": excl_1p,
            "exclusive_pct_site": excl_pct_site,
            "exclusive_pct_campaign": excl_pct_camp,
            "duplicate_reach_1plus": dupl_1p,
            "duplicate_pct_site": dupl_pct_site,
            "overlap_pct_campaign": ovl_pct_camp,
            "intersecao_compras_1plus": intersecao_compras,
            "p2c_solo_conversions": solo_convs,
            "p2c_solo_revenue": solo_rev,
            "p2c_combo_all_conversions": c_all_convs,
            "p2c_combo_all_revenue": c_all_rev,
            "p2c_combo_all_aov": c_all_aov,
            "p2c_combo_all_nonctv_touches": c_all_touches,
            "p2c_combo_camp_conversions": c_camp_convs,
            "p2c_combo_camp_aov": c_camp_aov,
            "p2c_combo_camp_nonctv_touches": c_camp_touches,
            "lift_lente1_valor_pct": lift_val_spec,
            "lift_lente1_specific_pct": lift_val_spec,
            "lift_lente2_efic_pct": lift_efic,
            **val,
        })

    ctv_channels.sort(key=lambda x: (x["duplicate_reach_1plus"], x["cost"]), reverse=True)
    blk_cost = sum(c["cost"] for c in ctv_channels)
    blk_tot_convs = sum(c["total_attributed_conversions"] for c in ctv_channels)
    blk_tot_rev = sum(c["total_attributed_revenue"] for c in ctv_channels)

    all_sites = [
        {
            "site": str(r["Site (CM360)"]),
            "is_ctv": bool(r["is_ctv"]),
            "cost": float(r["effective_cost"]),
            "cost_share_pct": (float(r["effective_cost"]) / std_tot_cost * 100.0) if std_tot_cost > 0 else 0.0,
            "impressions": float(r["impressions"]),
            "clicks": float(r["clicks"]),
            "std_conversions": float(r["std_conversions"]),
            "std_vt_conversions": float(r["std_vt_conversions"]),
            "std_ct_conversions": float(r["std_ct_conversions"]),
            "std_revenue": float(r["std_revenue"]),
            "unique_reach": cov_map.get(str(r["Site (CM360)"]), {}).get("unique_reach"),
            "coviewed_reach": cov_map.get(str(r["Site (CM360)"]), {}).get("coviewed_reach"),
            "exclusive_reach_1plus": ovl_map.get(str(r["Site (CM360)"]), {}).get("excl", 0.0),
            "duplicate_reach_1plus": ovl_map.get(str(r["Site (CM360)"]), {}).get("dupl", 0.0),
        }
        for _, r in df_sites.sort_values("effective_cost", ascending=False).iterrows()
    ]

    # Mathematical Locks 1 & 2
    for c in ctv_channels:
        assert blk_cost + 1e-6 >= c["cost"], f"Trava 1 violada em custo: {c['site']}"
        assert blk_tot_convs + 1e-6 >= c["total_attributed_conversions"], f"Trava 1 violada em conversões: {c['site']}"
    assert abs(sum(x["cost"] for x in all_sites) - std_tot_cost) < 0.05, "Trava 2 violada na soma de sites!"

    results = {
        "meta": {
            "case_slug": cfg["case_slug"],
            "brand_name": cfg["brand_name"],
            "agency_name": cfg["agency_name"],
            "identification_mode": "site",
            "naming_detected": bool(len(ctv_channels) > 0),
            "campaign_id": camp_id,
            "campaign_name": camp_name,
            "advertiser_id": str(cm_cfg["advertiser_id"]),
            "purchase_activity_labels": cm_cfg.get("purchase_activity_labels", {}),
            "start_date": sd,
            "end_date": ed,
            "generated_at_utc": manifest["generated_at_utc"],
        },
        "campaign_totals": {
            "std_cost": std_tot_cost,
            "std_impressions": std_tot_imps,
            "std_clicks": std_tot_clicks,
            "std_conversions": std_tot_convs,
            "std_vt_conversions": float(df_sites["std_vt_conversions"].sum()),
            "std_ct_conversions": float(df_sites["std_ct_conversions"].sum()),
            "std_revenue": std_tot_rev,
            "std_roas": (std_tot_rev / std_tot_cost) if std_tot_cost > 0 else 0.0,
            "reach_devices": camp_reach_dev,
            "reach_coviewed": camp_reach_cov,
            "coview_factor_campaign": (camp_reach_cov / camp_reach_dev) if camp_reach_dev > 0 else 1.0,
            "avg_freq_devices": camp_freq,
            "avg_freq_coviewed": camp_freq_cov,
            "p2c_total_journeys": p2c["p2c_journeys"],
            "p2c_total_conversions": p2c["p2c_conversions"],
            "p2c_total_revenue": p2c["p2c_revenue"],
            "p2c_total_aov": p2c["p2c_aov"],
            "p2c_shared_other_agency_journeys": len(p2c["shared_cids"]),
        },
        "p2c_control_vs_ctv": {
            "control_multi_no_ctv_all": ctrl_all,
            "control_multi_no_ctv_camp": ctrl_camp,
            "ctv_combo_block_all": {
                **combo_all,
                "aov": combo_camp["aov"] if combo_camp["conversions"] >= 5 else combo_all["aov"],
                "camp_conversions": combo_camp["conversions"],
                "camp_aov": combo_camp["aov"],
                "camp_avg_non_ctv_touches": combo_camp["avg_non_ctv_touches"],
                "lift_valor_pct": p2c["blk_lift_val"],
                "lift_efic_pct": p2c["blk_lift_efic"],
            },
        },
        "ctv_block_consolidated": {
            "cost": blk_cost,
            "cost_share_pct": (blk_cost / std_tot_cost * 100.0) if std_tot_cost > 0 else 0.0,
            "impressions": sum(c["impressions"] for c in ctv_channels),
            "impressions_share_pct": (sum(c["impressions"] for c in ctv_channels) / std_tot_imps * 100.0) if std_tot_imps > 0 else 0.0,
            "std_conversions": sum(c["std_conversions"] for c in ctv_channels),
            "std_vt_conversions": sum(c.get("std_vt_conversions", c["std_conversions"]) for c in ctv_channels),
            "std_ct_conversions": sum(c.get("std_ct_conversions", 0.0) for c in ctv_channels),
            "std_revenue": sum(c["std_revenue"] for c in ctv_channels),
            "std_share_pct": (sum(c["std_conversions"] for c in ctv_channels) / std_tot_convs * 100.0) if std_tot_convs > 0 else 0.0,
            "exclusive_reach_1plus_sum": sum(c["exclusive_reach_1plus"] for c in ctv_channels),
            "exclusive_pct_campaign_sum": sum(c["exclusive_pct_campaign"] for c in ctv_channels),
            "duplicate_reach_1plus_sum": sum(c["duplicate_reach_1plus"] for c in ctv_channels),
            "overlap_pct_campaign_sum": sum(c["overlap_pct_campaign"] for c in ctv_channels),
            "intersecao_compras_1plus": sum(c["intersecao_compras_1plus"] for c in ctv_channels),
            "p2c_solo_conversions": sum(c["p2c_solo_conversions"] for c in ctv_channels),
            "p2c_solo_revenue": sum(c["p2c_solo_revenue"] for c in ctv_channels),
            "assisted_conversions": sum(c["assisted_conversions"] for c in ctv_channels),
            "total_attributed_conversions": blk_tot_convs,
            "share_campaign_attributed_pct": (blk_tot_convs / p2c["p2c_conversions"] * 100.0) if p2c["p2c_conversions"] > 0 else 0.0,
            "assisted_base_revenue": sum(c["assisted_base_revenue"] for c in ctv_channels),
            "aov_premium_revenue": sum(c["aov_premium_revenue"] for c in ctv_channels),
            "total_attributed_revenue": blk_tot_rev,
            "cpa_attributed": (blk_cost / blk_tot_convs) if blk_tot_convs > 0 else None,
            "roas_attributed": (blk_tot_rev / blk_cost) if blk_cost > 0 else None,
        },
        "ctv_channels": ctv_channels,
        "all_sites": all_sites,
        "dv360_reconciliation": _summarize_dv360(cfg.get("dv360", {}), manifest, out_dir),
    }

    out_json = out_dir / "methodology_results.json"
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    b = results["ctv_block_consolidated"]
    print(f"[ETAPA 2 - SITE CONCLUÍDA] {out_json}")
    print(f"  • Bloco CTV: {fmt_curr(b['cost'])} | {fmt_dec(b['total_attributed_conversions'], 1)} comp. | {fmt_curr(b['total_attributed_revenue'])} (ROAS {fmt_dec(b['roas_attributed'])}x)")
    return str(out_json)


def _compute_device_mode(cfg: dict, manifest: dict, out_dir: Path) -> str:
    cm_cfg = cfg["cm360"]
    camp_id = str(cm_cfg["campaign_id"])
    camp_name = cm_cfg["campaign_name"]
    norm_kw = cm_cfg.get("brand_keyword_normalized") or norm_slug(camp_name)
    purchase_ids = [int(x) for x in cm_cfg["purchase_activity_ids"]]
    sd, ed = cfg["date_window"]["start_date"], cfg["date_window"]["end_date"]

    df_std = read_cm360_csv(_report_file(out_dir, manifest["cm360_reports"]["std_device_site_placement_ad"]["path"]))
    df_std = df_std[clean_id_str(df_std["Campaign ID"]) == camp_id].copy()
    df_std["plc_id_str"] = clean_id_str(df_std["Placement ID"])
    df_std["ad_id_str"] = clean_id_str(df_std["Ad ID"])
    df_std["Platform Type"] = df_std["Platform Type"].fillna("Unknown platform").astype(str).str.strip()
    for col in ["Impressions", "Clicks", "DV360 Cost (Account Currency)", "Media Cost"]:
        if col in df_std.columns:
            df_std[col] = clean_num(df_std[col]).fillna(0.0)
    df_std["effective_cost"] = np.where(df_std["DV360 Cost (Account Currency)"] > 0, df_std["DV360 Cost (Account Currency)"], df_std["Media Cost"])
    df_std["is_ctv_device"] = df_std["Platform Type"].isin(CTV_PLATFORM_NAMES)
    df_std["is_smart_tv"] = df_std["Platform Type"] == "Connected TV"
    df_std["is_stb"] = df_std["Platform Type"] == "Set top box"

    df_fl = read_cm360_csv(_report_file(out_dir, manifest["cm360_reports"]["std_device_floodlights"]["path"]))
    df_fl["Activity ID"] = clean_num(df_fl["Activity ID"]).fillna(-1).astype(int)
    df_fl = df_fl[(clean_id_str(df_fl["Campaign ID"]) == camp_id) & (df_fl["Activity ID"].isin(purchase_ids))].copy()
    df_fl["plc_id_str"] = clean_id_str(df_fl["Placement ID"])
    df_fl["checkout_platform"] = df_fl["Platform Type"].fillna("Unknown platform").astype(str).str.strip()
    for col in ["Total Conversions", "Total Revenue", "View-through Conversions", "Click-through Conversions"]:
        if col in df_fl.columns:
            df_fl[col] = clean_num(df_fl[col]).fillna(0.0)

    plc_tot_imps = df_std.groupby("plc_id_str")["Impressions"].sum().to_dict()
    plc_tot_clks = df_std.groupby("plc_id_str")["Clicks"].sum().to_dict()
    plc_plat_grp = df_std.groupby(["plc_id_str", "Platform Type"], as_index=False).agg(
        Impressions=("Impressions", "sum"), Clicks=("Clicks", "sum")
    )
    plc_plat_grp["plat_imp_share"] = [
        float(imp / plc_tot_imps[p]) if plc_tot_imps.get(p, 0.0) > 0
        else (float(clk / plc_tot_clks[p]) if plc_tot_clks.get(p, 0.0) > 0 else 0.0)
        for p, imp, clk in zip(plc_plat_grp["plc_id_str"], plc_plat_grp["Impressions"], plc_plat_grp["Clicks"])
    ]
    covered_plcs = set(plc_plat_grp[plc_plat_grp["plat_imp_share"] > 0]["plc_id_str"])
    tail_fl = df_fl[~df_fl["plc_id_str"].isin(covered_plcs)]
    if not tail_fl.empty:
        tail_tot = tail_fl.groupby("plc_id_str")["Total Conversions"].sum().to_dict()
        tail_grp = tail_fl.groupby(["plc_id_str", "checkout_platform"], as_index=False)["Total Conversions"].sum().rename(columns={"checkout_platform": "Platform Type"})
        tail_grp["plat_imp_share"] = [
            float(c / tail_tot[p]) if tail_tot.get(p, 0.0) > 0 else 0.0
            for p, c in zip(tail_grp["plc_id_str"], tail_grp["Total Conversions"])
        ]
        plc_plat_grp = pd.concat(
            [plc_plat_grp[plc_plat_grp["plc_id_str"].isin(covered_plcs)][["plc_id_str", "Platform Type", "plat_imp_share"]], tail_grp[["plc_id_str", "Platform Type", "plat_imp_share"]]],
            ignore_index=True,
        )
    plc_ctv_share = plc_plat_grp[plc_plat_grp["Platform Type"].isin(CTV_PLATFORM_NAMES)].groupby("plc_id_str")["plat_imp_share"].sum().to_dict()

    fl_by_plc = df_fl.groupby(["Site (CM360)", "plc_id_str"], as_index=False).agg(
        tot_conv=("Total Conversions", "sum"), vt_conv=("View-through Conversions", "sum"),
        ct_conv=("Click-through Conversions", "sum"), tot_rev=("Total Revenue", "sum"),
    )
    fl_by_plc["ctv_share"] = fl_by_plc["plc_id_str"].map(lambda p: plc_ctv_share.get(p, 0.0))
    for k_out, k_in in [("ctv_std_conversions", "tot_conv"), ("ctv_std_vt", "vt_conv"), ("ctv_std_ct", "ct_conv"), ("ctv_std_revenue", "tot_rev")]:
        fl_by_plc[k_out] = fl_by_plc[k_in] * fl_by_plc["ctv_share"]

    fl_plat_alloc = pd.merge(fl_by_plc, plc_plat_grp[["plc_id_str", "Platform Type", "plat_imp_share"]], on="plc_id_str", how="left")
    for k_out, k_in in [("imp_std_conversions", "tot_conv"), ("imp_std_vt", "vt_conv"), ("imp_std_ct", "ct_conv"), ("imp_std_revenue", "tot_rev")]:
        fl_plat_alloc[k_out] = fl_plat_alloc[k_in] * fl_plat_alloc["plat_imp_share"]

    std_tot_cost = float(df_std["effective_cost"].sum())
    std_tot_imps = float(df_std["Impressions"].sum())
    std_tot_clicks = float(df_std["Clicks"].sum())
    std_tot_convs = float(df_fl["Total Conversions"].sum())
    std_tot_rev = float(df_fl["Total Revenue"].sum())

    camp_reach_dev, camp_reach_cov, camp_freq, camp_freq_cov = _parse_reach_totals(_report_file(out_dir, manifest["cm360_reports"]["reach_campaign_total"]["path"]))
    ctv_blk_dev, ctv_blk_cov, ctv_blk_freq, _ = _parse_reach_totals(_report_file(out_dir, manifest["cm360_reports"]["reach_ctv_devices_block"]["path"]))
    nonctv_blk_dev, _, _, _ = _parse_reach_totals(_report_file(out_dir, manifest["cm360_reports"]["reach_nonctv_devices_block"]["path"]))

    # Exact Inclusion-Exclusion: |A_CTV ∩ B_NonCTV| = |A_CTV| + |B_NonCTV| - |U|
    exact_ovl_dev = max(0.0, ctv_blk_dev + nonctv_blk_dev - camp_reach_dev)
    exact_excl_dev = max(0.0, ctv_blk_dev - exact_ovl_dev)
    exact_ovl_pct = (exact_ovl_dev / camp_reach_dev * 100.0) if camp_reach_dev > 0 else 0.0
    exact_excl_pct = (exact_excl_dev / camp_reach_dev * 100.0) if camp_reach_dev > 0 else 0.0
    exact_conn_pct = (exact_ovl_dev / ctv_blk_dev * 100.0) if ctv_blk_dev > 0 else 0.0

    df_rch_plat = read_cm360_csv(_report_file(out_dir, manifest["cm360_reports"]["reach_by_platform"]["path"]))
    rch_plat_map = {
        str(r["Platform Type"]).strip(): {
            "unique_reach": _scalar_num(r, "Unique Reach: Impression Reach", 0.0),
            "coviewed_reach": _scalar_num(r, "Unique Reach: Impression Reach (Co-Viewed)", 0.0),
        }
        for _, r in df_rch_plat.iterrows()
    }

    base_plats = ["Connected TV", "Set top box", "Smartphone", "Desktop", "Tablet", "Mobile midrange: feature phone", "Unknown platform"]
    extra_plats = sorted((set(df_std["Platform Type"].unique()) | set(df_fl["checkout_platform"].unique())) - set(base_plats))
    all_plats = pd.DataFrame({"Platform Type": base_plats + extra_plats})
    df_plat_sum = (
        all_plats
        .merge(df_std.groupby("Platform Type", as_index=False).agg(impressions=("Impressions", "sum"), clicks=("Clicks", "sum"), cost=("effective_cost", "sum")), on="Platform Type", how="left")
        .merge(fl_plat_alloc.groupby("Platform Type", as_index=False).agg(std_conversions=("imp_std_conversions", "sum"), std_vt=("imp_std_vt", "sum"), std_ct=("imp_std_ct", "sum"), std_revenue=("imp_std_revenue", "sum")), on="Platform Type", how="left")
        .merge(df_fl.groupby("checkout_platform", as_index=False).agg(checkout_std_conversions=("Total Conversions", "sum"), checkout_std_revenue=("Total Revenue", "sum")).rename(columns={"checkout_platform": "Platform Type"}), on="Platform Type", how="left")
        .fillna(0.0)
    )
    df_plat_sum["sort_key"] = np.where(df_plat_sum["Platform Type"] == "Connected TV", 1e12, np.where(df_plat_sum["Platform Type"] == "Set top box", 5e11, df_plat_sum["cost"]))
    platform_breakdown = []
    for _, r in df_plat_sum.sort_values("sort_key", ascending=False).iterrows():
        pt = str(r["Platform Type"])
        u_r = rch_plat_map.get(pt, {}).get("unique_reach", 0.0)
        c_r = rch_plat_map.get(pt, {}).get("coviewed_reach", 0.0) or u_r
        platform_breakdown.append({
            "platform_type": pt,
            "is_ctv_device": pt in CTV_PLATFORM_NAMES,
            "cost": float(r["cost"]),
            "cost_share_pct": (float(r["cost"]) / std_tot_cost * 100.0) if std_tot_cost > 0 else 0.0,
            "impressions": float(r["impressions"]),
            "impressions_share_pct": (float(r["impressions"]) / std_tot_imps * 100.0) if std_tot_imps > 0 else 0.0,
            "clicks": float(r["clicks"]),
            "unique_reach": u_r,
            "coviewed_reach": c_r,
            "coview_factor": (c_r / u_r) if u_r > 0 else 1.0,
            "std_conversions": float(r["std_conversions"]),
            "std_vt_conversions": float(r["std_vt"]),
            "std_ct_conversions": float(r["std_ct"]),
            "std_revenue": float(r["std_revenue"]),
            "checkout_std_conversions": float(r["checkout_std_conversions"]),
            "checkout_std_revenue": float(r["checkout_std_revenue"]),
        })

    site_ctv_rch = _parse_site_reach_map(_report_file(out_dir, manifest["cm360_reports"]["reach_site_ctv_devices"]["path"]))
    site_nonctv_rch = _parse_site_reach_map(_report_file(out_dir, manifest["cm360_reports"]["reach_site_nonctv_devices"]["path"]))
    site_all_rch = _parse_site_reach_map(_report_file(out_dir, manifest["cm360_reports"]["reach_site_all_coviewed"]["path"]))
    site_ovl_all = _parse_site_overlap_map(_report_file(out_dir, manifest["cm360_reports"]["reach_site_overlap_all"]["path"]))

    df_sp = read_cm360_csv(_report_file(out_dir, manifest["cm360_reports"]["reach_site_by_platform"]["path"]))
    site_plat_rch = {
        (str(r["Site (CM360)"]).strip(), str(r["Platform Type"]).strip()): _scalar_num(r, "Unique Reach: Impression Reach", 0.0)
        for _, r in df_sp.iterrows()
    }

    df_std["camp_id_str"] = clean_id_str(df_std["Campaign ID"])
    ad_grp = df_std.groupby(["camp_id_str", "plc_id_str", "ad_id_str"], as_index=False).agg(
        tot_imps=("Impressions", "sum"), ctv_imps=("Impressions", lambda x: x[df_std.loc[x.index, "is_ctv_device"]].sum())
    )
    ad_ctv_prob = {(r["camp_id_str"], r["plc_id_str"], r["ad_id_str"]): float(r["ctv_imps"] / r["tot_imps"]) for _, r in ad_grp.iterrows() if r["tot_imps"] > 0}

    df_adv = read_cm360_csv(_report_file(out_dir, manifest["cm360_reports"]["std_advertiser_device_map"]["path"]))
    df_adv["camp_id_str"] = clean_id_str(df_adv["Campaign ID"])
    df_adv["plc_id_str"] = clean_id_str(df_adv["Placement ID"])
    df_adv["Impressions"] = clean_num(df_adv["Impressions"]).fillna(0.0)
    df_adv["is_ctv_device"] = df_adv["Platform Type"].fillna("").astype(str).str.strip().isin(CTV_PLATFORM_NAMES)

    plc_grp = df_adv.groupby(["camp_id_str", "plc_id_str"], as_index=False).agg(
        tot_imps=("Impressions", "sum"), ctv_imps=("Impressions", lambda x: x[df_adv.loc[x.index, "is_ctv_device"]].sum())
    )
    plc_ctv_prob = {(r["camp_id_str"], r["plc_id_str"]): float(r["ctv_imps"] / r["tot_imps"]) for _, r in plc_grp.iterrows() if r["tot_imps"] > 0}
    site_adv_grp = df_adv.groupby("Site (CM360)", as_index=False).agg(
        tot_imps=("Impressions", "sum"), ctv_imps=("Impressions", lambda x: x[df_adv.loc[x.index, "is_ctv_device"]].sum())
    )
    site_ctv_prob = {str(r["Site (CM360)"]).strip(): float(r["ctv_imps"] / r["tot_imps"]) for _, r in site_adv_grp.iterrows() if r["tot_imps"] > 0}

    def _device_classifier(df_p):
        def _prob(r):
            s = r["site_clean"]
            if "search" in s.lower():
                return 0.0
            k_ad = (r["camp_id_str"], r["plc_id_str"], r["ad_id_str"])
            if k_ad in ad_ctv_prob:
                return ad_ctv_prob[k_ad]
            k_plc = (r["camp_id_str"], r["plc_id_str"])
            if k_plc in plc_ctv_prob:
                return plc_ctv_prob[k_plc]
            return site_ctv_prob.get(s, 1.0 if "ctv" in s.lower() else 0.0)

        df_p["ctv_device_prob"] = [_prob(r) for r in df_p[["site_clean", "camp_id_str", "plc_id_str", "ad_id_str"]].to_dict("records")]
        df_p["is_ctv_touch"] = df_p["ctv_device_prob"] >= PURE_CTV_PLACEMENT_THRESHOLD
        return df_p

    p2c = _analyze_p2c(
        _report_file(out_dir, manifest["cm360_reports"]["p2c_14d_device_enriched"]["path"]),
        camp_id, norm_kw, purchase_ids, _device_classifier, strict_combo_nonctv=True,
    )
    cid_stats, t_conv_df = p2c["cid_stats"], p2c["target_conv_df"]
    ctrl_all, ctrl_camp, combo_all, combo_camp = p2c["ctrl_all"], p2c["ctrl_camp"], p2c["combo_all"], p2c["combo_camp"]
    t_only = p2c["target_touches"][p2c["target_touches"]["is_target_camp"]]
    purity_audit = {
        "pure_ctv_touches_ge_95pct": int((t_only["ctv_device_prob"] >= PURE_CTV_PLACEMENT_THRESHOLD).sum()),
        "mixed_touches_5_to_95pct": int(((t_only["ctv_device_prob"] > 0.05) & (t_only["ctv_device_prob"] < PURE_CTV_PLACEMENT_THRESHOLD)).sum()),
        "pure_nonctv_touches_le_5pct": int((t_only["ctv_device_prob"] <= 0.05).sum()),
    }

    df_all_sites = (
        df_std.groupby("Site (CM360)", as_index=False).agg(site_total_impressions=("Impressions", "sum"), site_total_clicks=("Clicks", "sum"), site_total_cost=("effective_cost", "sum"))
        .merge(fl_by_plc.groupby("Site (CM360)", as_index=False).agg(
            site_total_std_conversions=("tot_conv", "sum"), site_total_std_vt=("vt_conv", "sum"), site_total_std_revenue=("tot_rev", "sum"),
            ctv_std_conversions=("ctv_std_conversions", "sum"), ctv_std_vt=("ctv_std_vt", "sum"), ctv_std_ct=("ctv_std_ct", "sum"), ctv_std_revenue=("ctv_std_revenue", "sum"),
        ), on="Site (CM360)", how="outer")
        .merge(df_std[df_std["is_ctv_device"]].groupby("Site (CM360)", as_index=False).agg(
            ctv_impressions=("Impressions", "sum"),
            smart_tv_impressions=("Impressions", lambda x: x[df_std.loc[x.index, "is_smart_tv"]].sum()),
            stb_impressions=("Impressions", lambda x: x[df_std.loc[x.index, "is_stb"]].sum()),
            ctv_clicks=("Clicks", "sum"),
            ctv_cost=("effective_cost", "sum"),
            smart_tv_cost=("effective_cost", lambda x: x[df_std.loc[x.index, "is_smart_tv"]].sum()),
            stb_cost=("effective_cost", lambda x: x[df_std.loc[x.index, "is_stb"]].sum()),
        ), on="Site (CM360)", how="outer")
        .fillna(0.0)
    )

    ctv_sites_sorted = sorted(df_all_sites[df_all_sites["ctv_impressions"] > 0]["Site (CM360)"].tolist(), key=lambda s: ("ctv" not in s.lower(), s))
    yt_ref_lift, yt_ref_aov = None, None
    raw_records = []

    for s in ctv_sites_sorted:
        row_s = df_all_sites[df_all_sites["Site (CM360)"] == s].iloc[0]
        u_ctv = site_ctv_rch.get(s, {}).get("unique_reach", 0.0)
        c_ctv = site_ctv_rch.get(s, {}).get("coviewed_reach", 0.0) or u_ctv
        u_non = site_nonctv_rch.get(s, {}).get("unique_reach", 0.0)
        u_all = site_all_rch.get(s, {}).get("unique_reach", 0.0)
        dupl_all_s = site_ovl_all.get(s, {}).get("dupl", 0.0)
        intra_ovl = min(u_ctv, max(0.0, u_ctv + u_non - u_all) if u_all > 0 else 0.0)
        cross_rate = min(1.0, max(0.0, (dupl_all_s / u_all) if u_all > 0 else 0.0))
        raw_dupl = min(u_ctv, dupl_all_s * (u_ctv / u_all)) if (u_non == 0 and u_all > 0) else min(u_ctv, intra_ovl + (u_ctv - intra_ovl) * cross_rate)

        cids_s = [c for c in p2c["target_cids"] if s in cid_stats[c]["ctv_sites_camp"]]
        df_solo = t_conv_df[t_conv_df["Conversion ID"].isin([c for c in cids_s if cid_stats[c]["all_touches_are_ctv"] and len(cid_stats[c]["unique_all_sites"]) == 1])]
        df_c_all = t_conv_df[t_conv_df["Conversion ID"].isin([c for c in cids_s if cid_stats[c]["non_ctv_touches_all"] > 0])]
        df_c_camp = t_conv_df[t_conv_df["Conversion ID"].isin([c for c in cids_s if cid_stats[c]["non_ctv_touches_camp"] > 0])]

        solo_convs, solo_rev = float(df_solo["Total Conversions"].sum()), float(df_solo["Total Revenue"].sum())
        c_all_convs, c_all_rev = float(df_c_all["Total Conversions"].sum()), float(df_c_all["Total Revenue"].sum())
        c_all_aov = (c_all_rev / c_all_convs) if c_all_convs > 0 else combo_all["aov"]
        c_all_touches = float(df_c_all["non_ctv_touches_all"].mean()) if len(df_c_all) > 0 else combo_all["avg_non_ctv_touches"]
        c_camp_convs, c_camp_rev = float(df_c_camp["Total Conversions"].sum()), float(df_c_camp["Total Revenue"].sum())
        c_camp_aov = (c_camp_rev / c_camp_convs) if c_camp_convs > 0 else c_all_aov
        base_ctrl_aov = ctrl_camp["aov"] if ctrl_camp["conversions"] >= 5 else ctrl_all["aov"]

        if c_all_convs >= 5 and ctrl_all["avg_non_ctv_touches"] > 0:
            lift_efic, lift_src = max(0.0, (ctrl_all["avg_non_ctv_touches"] - c_all_touches) / ctrl_all["avg_non_ctv_touches"] * 100.0), "p2c_placement_puro_direto"
        elif "youtube" in s.lower() and yt_ref_lift is not None:
            lift_efic, lift_src = yt_ref_lift, "benchmark_youtube_ctv_puro_mesma_campanha"
        else:
            lift_efic, lift_src = p2c["blk_lift_efic"], "bloco_ctv_devices_campanha"

        if c_camp_convs >= 5:
            aov_with_ctv, lift_val_spec = c_camp_aov, max(0.0, (c_camp_aov - base_ctrl_aov) / c_camp_aov * 100.0)
        elif c_all_convs >= 5:
            aov_with_ctv, lift_val_spec = c_all_aov, max(0.0, (c_all_aov - base_ctrl_aov) / c_all_aov * 100.0)
        elif "youtube" in s.lower() and yt_ref_aov is not None:
            aov_with_ctv, lift_val_spec = yt_ref_aov, max(0.0, (yt_ref_aov - base_ctrl_aov) / yt_ref_aov * 100.0)
        else:
            aov_with_ctv = combo_camp["aov"] if combo_camp["conversions"] >= 5 else combo_all["aov"]
            lift_val_spec = p2c["blk_lift_val"]

        if "youtubectv" in norm_slug(s) and c_all_convs >= 5:
            yt_ref_lift, yt_ref_aov = lift_efic, aov_with_ctv

        raw_records.append({
            "site": s, "is_residual": float(row_s["ctv_impressions"]) < MIN_MEANINGFUL_CTV_IMPS, "row_s": row_s,
            "u_reach_ctv": u_ctv, "c_reach_ctv": c_ctv, "smart_tv_rch": site_plat_rch.get((s, "Connected TV"), 0.0),
            "stb_rch": site_plat_rch.get((s, "Set top box"), 0.0), "coview_factor": (c_ctv / u_ctv) if u_ctv > 0 else 1.0,
            "intra_site_overlap": intra_ovl, "raw_dupl_1p": raw_dupl, "solo_convs": solo_convs, "solo_rev": solo_rev,
            "combo_all_convs": c_all_convs, "combo_all_nonctv_touches": c_all_touches, "combo_camp_convs": c_camp_convs,
            "aov_with_ctv": aov_with_ctv, "base_ctrl_aov": base_ctrl_aov, "s_lift_valor_specific": lift_val_spec,
            "lift_efic_pct": lift_efic, "lift_source": lift_src,
        })

    main_recs = [r for r in raw_records if not r["is_residual"]]
    resid_recs = [r for r in raw_records if r["is_residual"]]
    if resid_recs:
        r_names = "/".join(r["site"].replace("DV360_", "").replace("DV360-", "").replace(" BR", "") for r in resid_recs)
        thr_lbl = "1.000" if max(float(r["row_s"]["ctv_impressions"]) for r in resid_recs) >= 500.0 else "500"
        u_res, c_res = sum(r["u_reach_ctv"] for r in resid_recs), sum(r["c_reach_ctv"] for r in resid_recs)
        cols_sum = ["ctv_cost", "smart_tv_cost", "stb_cost", "site_total_cost", "ctv_impressions", "smart_tv_impressions",
                    "stb_impressions", "site_total_impressions", "ctv_clicks", "ctv_std_conversions", "ctv_std_vt", "ctv_std_ct", "ctv_std_revenue"]
        main_recs.append({
            "site": f"Residual (<{thr_lbl} imps TV: {r_names})", "is_residual": True,
            "row_s": {k: sum(float(r["row_s"][k]) for r in resid_recs) for k in cols_sum},
            "u_reach_ctv": u_res, "c_reach_ctv": c_res,
            "smart_tv_rch": sum(r["smart_tv_rch"] for r in resid_recs), "stb_rch": sum(r["stb_rch"] for r in resid_recs),
            "coview_factor": (c_res / u_res) if u_res > 0 else 1.0,
            "intra_site_overlap": sum(r["intra_site_overlap"] for r in resid_recs), "raw_dupl_1p": sum(r["raw_dupl_1p"] for r in resid_recs),
            "solo_convs": sum(r["solo_convs"] for r in resid_recs), "solo_rev": sum(r["solo_rev"] for r in resid_recs),
            "combo_all_convs": 0.0, "combo_all_nonctv_touches": combo_all["avg_non_ctv_touches"], "combo_camp_convs": 0.0,
            "aov_with_ctv": combo_camp["aov"] if combo_camp["conversions"] >= 5 else combo_all["aov"],
            "base_ctrl_aov": ctrl_camp["aov"] if ctrl_camp["conversions"] >= 5 else ctrl_all["aov"],
            "s_lift_valor_specific": p2c["blk_lift_val"], "lift_efic_pct": p2c["blk_lift_efic"], "lift_source": "bloco_ctv_devices_campanha",
        })

    tot_raw_dupl = sum(r["raw_dupl_1p"] for r in main_recs)
    pure_scale = (exact_ovl_dev / tot_raw_dupl) if tot_raw_dupl > 0 else 1.0

    ctv_channels = []
    for rec in main_recs:
        s, row_s = rec["site"], rec["row_s"]
        s_cost, s_imps = float(row_s["ctv_cost"]), float(row_s["ctv_impressions"])
        u_ctv, c_ctv, cov_f, raw_d = rec["u_reach_ctv"], rec["c_reach_ctv"], rec["coview_factor"], rec["raw_dupl_1p"]
        pure_d = raw_d * pure_scale
        pure_e = max(0.0, u_ctv - pure_d)
        pure_ovl_pct = (pure_d / camp_reach_dev * 100.0) if camp_reach_dev > 0 else 0.0
        raw_ovl_pct = (raw_d / camp_reach_dev * 100.0) if camp_reach_dev > 0 else 0.0
        pure_inter = p2c["p2c_conversions"] * (pure_ovl_pct / 100.0)
        raw_inter = p2c["p2c_conversions"] * (raw_ovl_pct / 100.0)

        val_pure = _value_channel(rec["solo_convs"], rec["solo_rev"], pure_inter, rec["lift_efic_pct"], rec["aov_with_ctv"], rec["base_ctrl_aov"], s_cost, p2c["p2c_conversions"])
        val_raw = _value_channel(rec["solo_convs"], rec["solo_rev"], raw_inter, rec["lift_efic_pct"], rec["aov_with_ctv"], rec["base_ctrl_aov"], s_cost, p2c["p2c_conversions"])

        ctv_channels.append({
            "site": s,
            "is_residual_bucket": rec["is_residual"],
            "had_ctv_in_site_name": ("ctv" in s.lower()) and (not rec["is_residual"]),
            "lift_calibration_source": rec["lift_source"],
            "cost": s_cost,
            "smart_tv_cost": float(row_s["smart_tv_cost"]),
            "stb_cost": float(row_s["stb_cost"]),
            "site_total_cost": float(row_s["site_total_cost"]),
            "ctv_share_of_site_cost_pct": (s_cost / float(row_s["site_total_cost"]) * 100.0) if float(row_s["site_total_cost"]) > 0 else 0.0,
            "cost_share_pct": (s_cost / std_tot_cost * 100.0) if std_tot_cost > 0 else 0.0,
            "impressions": s_imps,
            "smart_tv_impressions": float(row_s["smart_tv_impressions"]),
            "stb_impressions": float(row_s["stb_impressions"]),
            "site_total_impressions": float(row_s["site_total_impressions"]),
            "ctv_share_of_site_imps_pct": (s_imps / float(row_s["site_total_impressions"]) * 100.0) if float(row_s["site_total_impressions"]) > 0 else 0.0,
            "clicks": float(row_s["ctv_clicks"]),
            "cpm": (s_cost / (s_imps / 1000.0)) if s_imps > 0 else 0.0,
            "ecpm_coview": (s_cost / ((s_imps * cov_f) / 1000.0)) if s_imps > 0 else 0.0,
            "std_conversions": float(row_s["ctv_std_conversions"]),
            "std_vt_conversions": float(row_s["ctv_std_vt"]),
            "std_ct_conversions": float(row_s["ctv_std_ct"]),
            "std_revenue": float(row_s["ctv_std_revenue"]),
            "unique_reach": u_ctv,
            "smart_tv_reach": rec["smart_tv_rch"],
            "stb_reach": rec["stb_rch"],
            "coviewed_reach": c_ctv,
            "coview_factor": cov_f,
            "intra_site_overlap_1plus": rec["intra_site_overlap"],
            "exclusive_reach_1plus": pure_e,
            "exclusive_pct_site": (pure_e / u_ctv * 100.0) if u_ctv > 0 else 0.0,
            "exclusive_pct_campaign": (pure_e / camp_reach_dev * 100.0) if camp_reach_dev > 0 else 0.0,
            "duplicate_reach_1plus": pure_d,
            "duplicate_pct_site": (pure_d / u_ctv * 100.0) if u_ctv > 0 else 0.0,
            "overlap_pct_campaign": pure_ovl_pct,
            "intersecao_compras_1plus": pure_inter,
            "raw_duplicate_reach_1plus": raw_d,
            "raw_overlap_pct_campaign": raw_ovl_pct,
            "raw_intersecao_compras_1plus": raw_inter,
            "p2c_solo_conversions": rec["solo_convs"],
            "p2c_solo_revenue": rec["solo_rev"],
            "p2c_combo_all_conversions": rec["combo_all_convs"],
            "p2c_combo_all_nonctv_touches": rec["combo_all_nonctv_touches"],
            "p2c_combo_camp_conversions": rec["combo_camp_convs"],
            "p2c_combo_camp_aov": rec["aov_with_ctv"],
            "lift_lente1_specific_pct": rec["s_lift_valor_specific"],
            "lift_lente2_efic_pct": rec["lift_efic_pct"],
            **val_pure,
            "raw_assisted_conversions": val_raw["assisted_conversions"],
            "raw_total_attributed_conversions": val_raw["total_attributed_conversions"],
            "raw_total_attributed_revenue": val_raw["total_attributed_revenue"],
            "raw_roas_attributed": val_raw["roas_attributed"],
        })

    ctv_channels.sort(key=lambda x: (not x["is_residual_bucket"], x["cost"], x["impressions"]), reverse=True)
    blk_cost = sum(c["cost"] for c in ctv_channels)
    blk_dupl = sum(c["duplicate_reach_1plus"] for c in ctv_channels)
    blk_tot_convs = sum(c["total_attributed_conversions"] for c in ctv_channels)
    blk_tot_rev = sum(c["total_attributed_revenue"] for c in ctv_channels)
    raw_blk_dupl = sum(c["raw_duplicate_reach_1plus"] for c in ctv_channels)
    raw_blk_convs = sum(c["raw_total_attributed_conversions"] for c in ctv_channels)
    raw_blk_rev = sum(c["raw_total_attributed_revenue"] for c in ctv_channels)

    all_sites_split = [
        {
            "site": str(r["Site (CM360)"]),
            "had_ctv_in_name": "ctv" in str(r["Site (CM360)"]).lower(),
            "total_cost": float(r["site_total_cost"]),
            "ctv_device_cost": float(r["ctv_cost"]),
            "smart_tv_cost": float(r["smart_tv_cost"]),
            "stb_cost": float(r["stb_cost"]),
            "non_ctv_device_cost": max(0.0, float(r["site_total_cost"]) - float(r["ctv_cost"])),
            "ctv_cost_pct_of_site": (float(r["ctv_cost"]) / float(r["site_total_cost"]) * 100.0) if float(r["site_total_cost"]) > 0 else 0.0,
            "total_impressions": float(r["site_total_impressions"]),
            "ctv_device_impressions": float(r["ctv_impressions"]),
            "smart_tv_impressions": float(r["smart_tv_impressions"]),
            "stb_impressions": float(r["stb_impressions"]),
            "non_ctv_device_impressions": max(0.0, float(r["site_total_impressions"]) - float(r["ctv_impressions"])),
            "ctv_imps_pct_of_site": (float(r["ctv_impressions"]) / float(r["site_total_impressions"]) * 100.0) if float(r["site_total_impressions"]) > 0 else 0.0,
            "total_std_conversions": float(r["site_total_std_conversions"]),
            "ctv_device_std_conversions": float(r["ctv_std_conversions"]),
            "non_ctv_device_std_conversions": max(0.0, float(r["site_total_std_conversions"]) - float(r["ctv_std_conversions"])),
            "total_std_revenue": float(r["site_total_std_revenue"]),
            "ctv_device_std_revenue": float(r["ctv_std_revenue"]),
        }
        for _, r in df_all_sites.sort_values("site_total_cost", ascending=False).iterrows()
    ]

    comparison_vs_site = {}
    base_raw = cfg.get("baseline_site_results_path")
    if base_raw:
        base_file = resolve_path(base_raw)
        if base_file.exists():
            base_res = json.loads(base_file.read_text(encoding="utf-8"))
            b_blk = base_res["ctv_block_consolidated"]
            b_chans = {c["site"]: c for c in base_res["ctv_channels"]}
            d_chans = {c["site"]: c for c in ctv_channels}
            comp_sites = [c["site"] for c in ctv_channels] + [k for k in b_chans if k not in d_chans]
            comparison_vs_site = {
                "site_block": {
                    "cost": b_blk["cost"], "cost_share_pct": b_blk["cost_share_pct"], "impressions": b_blk["impressions"],
                    "std_conversions": b_blk["std_conversions"], "overlap_pct_sum": b_blk["overlap_pct_campaign_sum"],
                    "intersecao_compras": b_blk["intersecao_compras_1plus"], "solo_conversions": b_blk["p2c_solo_conversions"],
                    "assisted_conversions": b_blk["assisted_conversions"], "total_attributed_conversions": b_blk["total_attributed_conversions"],
                    "share_campaign_attributed_pct": b_blk["share_campaign_attributed_pct"], "aov_premium_revenue": b_blk["aov_premium_revenue"],
                    "total_attributed_revenue": b_blk["total_attributed_revenue"], "cpa_attributed": b_blk["cpa_attributed"], "roas_attributed": b_blk["roas_attributed"],
                },
                "per_site_comparison": [
                    {
                        "site": s,
                        "site_method_cost": b_chans.get(s, {}).get("cost", 0.0),
                        "device_method_cost": d_chans.get(s, {}).get("cost", 0.0),
                        "delta_cost": d_chans.get(s, {}).get("cost", 0.0) - b_chans.get(s, {}).get("cost", 0.0),
                        "site_method_overlap_pct": b_chans.get(s, {}).get("overlap_pct_campaign", 0.0),
                        "device_method_overlap_pct": d_chans.get(s, {}).get("overlap_pct_campaign", 0.0),
                        "device_raw_overlap_pct": d_chans.get(s, {}).get("raw_overlap_pct_campaign", 0.0),
                        "site_method_convs": b_chans.get(s, {}).get("total_attributed_conversions", 0.0),
                        "device_method_convs": d_chans.get(s, {}).get("total_attributed_conversions", 0.0),
                        "device_raw_convs": d_chans.get(s, {}).get("raw_total_attributed_conversions", 0.0),
                        "delta_convs": d_chans.get(s, {}).get("total_attributed_conversions", 0.0) - b_chans.get(s, {}).get("total_attributed_conversions", 0.0),
                        "site_method_rev": b_chans.get(s, {}).get("total_attributed_revenue", 0.0),
                        "device_method_rev": d_chans.get(s, {}).get("total_attributed_revenue", 0.0),
                        "device_raw_rev": d_chans.get(s, {}).get("raw_total_attributed_revenue", 0.0),
                        "delta_rev": d_chans.get(s, {}).get("total_attributed_revenue", 0.0) - b_chans.get(s, {}).get("total_attributed_revenue", 0.0),
                        "site_method_roas": b_chans.get(s, {}).get("roas_attributed"),
                        "device_method_roas": d_chans.get(s, {}).get("roas_attributed"),
                        "device_raw_roas": d_chans.get(s, {}).get("raw_roas_attributed"),
                    }
                    for s in comp_sites
                ],
            }

    # Mathematical Locks 1 & 2
    for c in ctv_channels:
        assert blk_cost + 1e-6 >= c["cost"], f"Trava 1 violada em custo: {c['site']}"
        assert blk_dupl + 1e-3 >= c["duplicate_reach_1plus"], f"Trava 1 violada em overlap: {c['site']}"
        assert blk_tot_convs + 1e-6 >= c["total_attributed_conversions"], f"Trava 1 violada em compras: {c['site']}"
    assert abs(blk_dupl - exact_ovl_dev) < 1.0, "Trava 2 violada: Soma Overlap Alocado != Inclusão-Exclusão Exata!"
    assert abs(sum(x["total_cost"] for x in all_sites_split) - std_tot_cost) < 0.05, "Trava 2 violada em sites!"
    assert abs(sum(x["cost"] for x in platform_breakdown) - std_tot_cost) < 0.05, "Trava 2 violada em plataformas!"
    assert abs(sum(x["std_conversions"] for x in platform_breakdown) - std_tot_convs) < 0.05, "Trava 2 violada em conversões Std!"

    results = {
        "meta": {
            "case_slug": cfg["case_slug"],
            "brand_name": cfg["brand_name"],
            "agency_name": cfg["agency_name"],
            "identification_mode": "device",
            "campaign_id": camp_id,
            "campaign_name": camp_name,
            "purchase_activity_labels": cm_cfg.get("purchase_activity_labels", {}),
            "start_date": sd,
            "end_date": ed,
            "generated_at_utc": manifest["generated_at_utc"],
        },
        "campaign_totals": {
            "std_cost": std_tot_cost, "std_impressions": std_tot_imps, "std_clicks": std_tot_clicks,
            "std_conversions": std_tot_convs, "std_revenue": std_tot_rev,
            "std_roas": (std_tot_rev / std_tot_cost) if std_tot_cost > 0 else 0.0,
            "reach_devices": camp_reach_dev, "reach_coviewed": camp_reach_cov,
            "coview_factor_campaign": (camp_reach_cov / camp_reach_dev) if camp_reach_dev > 0 else 1.0,
            "avg_freq_devices": camp_freq, "avg_freq_coviewed": camp_freq_cov,
            "p2c_total_journeys": p2c["p2c_journeys"], "p2c_total_conversions": p2c["p2c_conversions"],
            "p2c_total_revenue": p2c["p2c_revenue"], "p2c_total_aov": p2c["p2c_aov"],
            "p2c_shared_other_agency_journeys": len(p2c["shared_cids"]),
        },
        "platform_breakdown": platform_breakdown,
        "checkout_device_breakdown": p2c["checkout_breakdown"],
        "p2c_touch_purity_audit": purity_audit,
        "exact_inclusion_exclusion_block": {
            "ctv_devices_reach_dedup": ctv_blk_dev,
            "ctv_devices_coviewed_dedup": ctv_blk_cov,
            "ctv_devices_avg_freq": ctv_blk_freq,
            "non_ctv_devices_reach_dedup": nonctv_blk_dev,
            "campaign_total_reach_dedup": camp_reach_dev,
            "exact_cross_device_overlap_1plus": exact_ovl_dev,
            "exact_exclusive_ctv_1plus": exact_excl_dev,
            "exact_overlap_pct_campaign": exact_ovl_pct,
            "exact_exclusive_pct_campaign": exact_excl_pct,
            "exact_connectivity_pct_of_ctv": exact_conn_pct,
            "pure_cross_device_scale_factor": pure_scale,
            "tv_tv_and_multisite_purged_devices": max(0.0, raw_blk_dupl - exact_ovl_dev),
        },
        "p2c_control_vs_ctv": {
            "control_multi_no_ctv_all": ctrl_all,
            "control_multi_no_ctv_camp": ctrl_camp,
            "ctv_combo_block_all": {
                **combo_all,
                "aov": combo_camp["aov"] if combo_camp["conversions"] >= 5 else combo_all["aov"],
                "camp_conversions": combo_camp["conversions"],
                "camp_aov": combo_camp["aov"],
                "lift_valor_pct": p2c["blk_lift_val"],
                "lift_efic_pct": p2c["blk_lift_efic"],
            },
        },
        "ctv_block_consolidated": {
            "cost": blk_cost,
            "smart_tv_cost": sum(c["smart_tv_cost"] for c in ctv_channels),
            "stb_cost": sum(c["stb_cost"] for c in ctv_channels),
            "cost_share_pct": (blk_cost / std_tot_cost * 100.0) if std_tot_cost > 0 else 0.0,
            "impressions": sum(c["impressions"] for c in ctv_channels),
            "smart_tv_impressions": sum(c["smart_tv_impressions"] for c in ctv_channels),
            "stb_impressions": sum(c["stb_impressions"] for c in ctv_channels),
            "impressions_share_pct": (sum(c["impressions"] for c in ctv_channels) / std_tot_imps * 100.0) if std_tot_imps > 0 else 0.0,
            "std_conversions": sum(c["std_conversions"] for c in ctv_channels),
            "std_vt_conversions": sum(c["std_vt_conversions"] for c in ctv_channels),
            "std_revenue": sum(c["std_revenue"] for c in ctv_channels),
            "std_share_pct": (sum(c["std_conversions"] for c in ctv_channels) / std_tot_convs * 100.0) if std_tot_convs > 0 else 0.0,
            "duplicate_reach_1plus_sum": blk_dupl,
            "overlap_pct_campaign_sum": sum(c["overlap_pct_campaign"] for c in ctv_channels),
            "intersecao_compras_1plus": sum(c["intersecao_compras_1plus"] for c in ctv_channels),
            "p2c_solo_conversions": sum(c["p2c_solo_conversions"] for c in ctv_channels),
            "p2c_solo_revenue": sum(c["p2c_solo_revenue"] for c in ctv_channels),
            "assisted_conversions": sum(c["assisted_conversions"] for c in ctv_channels),
            "total_attributed_conversions": blk_tot_convs,
            "share_campaign_attributed_pct": (blk_tot_convs / p2c["p2c_conversions"] * 100.0) if p2c["p2c_conversions"] > 0 else 0.0,
            "assisted_base_revenue": sum(c["assisted_base_revenue"] for c in ctv_channels),
            "aov_premium_revenue": sum(c["aov_premium_revenue"] for c in ctv_channels),
            "total_attributed_revenue": blk_tot_rev,
            "cpa_attributed": (blk_cost / blk_tot_convs) if blk_tot_convs > 0 else None,
            "roas_attributed": (blk_tot_rev / blk_cost) if blk_cost > 0 else None,
            "raw_duplicate_reach_1plus_sum": raw_blk_dupl,
            "raw_overlap_pct_campaign_sum": sum(c["raw_overlap_pct_campaign"] for c in ctv_channels),
            "raw_intersecao_compras_1plus": sum(c["raw_intersecao_compras_1plus"] for c in ctv_channels),
            "raw_assisted_conversions": sum(c["raw_assisted_conversions"] for c in ctv_channels),
            "raw_total_attributed_conversions": raw_blk_convs,
            "raw_share_campaign_attributed_pct": (raw_blk_convs / p2c["p2c_conversions"] * 100.0) if p2c["p2c_conversions"] > 0 else 0.0,
            "raw_total_attributed_revenue": raw_blk_rev,
            "raw_cpa_attributed": (blk_cost / raw_blk_convs) if raw_blk_convs > 0 else None,
            "raw_roas_attributed": (raw_blk_rev / blk_cost) if blk_cost > 0 else None,
        },
        "ctv_channels": ctv_channels,
        "all_sites_device_split": all_sites_split,
        "dv360_reconciliation": _summarize_dv360(cfg.get("dv360", {}), manifest, out_dir),
        "comparison_vs_site_method": comparison_vs_site,
    }

    out_json = out_dir / "methodology_device_results.json"
    out_json.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    b = results["ctv_block_consolidated"]
    print(f"[ETAPA 2 - DEVICE CONCLUÍDA] {out_json}")
    print(f"  • Bloco TV/STB Puro: {fmt_curr(b['cost'])} | {fmt_dec(b['total_attributed_conversions'], 1)} comp. | {fmt_curr(b['total_attributed_revenue'])} (ROAS {fmt_dec(b['roas_attributed'])}x)")
    return str(out_json)


def compute_methodology(config_path: str, mode_override: str | None = None) -> str:
    cfg = load_config(config_path, mode_override=mode_override)
    mode = get_mode(cfg)
    out_dir = Path(cfg["output_dir"])
    if mode == "both":
        m_dev = out_dir / "extraction_manifest_device.json"
        if not m_dev.exists():
            raise FileNotFoundError(f"Manifesto Device não encontrado em {out_dir}. Rode step1_extract_reports.py --mode both primeiro.")
        m_site_cand = out_dir / "extraction_manifest.json"
        m_site = m_site_cand if (m_site_cand.exists() and m_site_cand.stat().st_mtime > m_dev.stat().st_mtime) else m_dev
        site_json = _compute_site_mode(cfg, json.loads(m_site.read_text(encoding="utf-8")), out_dir)
        site_res = json.loads(Path(site_json).read_text(encoding="utf-8"))
        if site_res["meta"].get("naming_detected") and not cfg.get("baseline_site_results_path"):
            cfg["baseline_site_results_path"] = site_json
        return _compute_device_mode(cfg, json.loads(m_dev.read_text(encoding="utf-8")), out_dir)

    m_candidates = (
        [out_dir / "extraction_manifest_device.json", out_dir / "extraction_manifest.json"]
        if mode == "device"
        else [out_dir / "extraction_manifest.json", out_dir / "extraction_manifest_device.json"]
    )
    m_path = next((p for p in m_candidates if p.exists()), None)
    if not m_path:
        raise FileNotFoundError(f"Manifesto de extração não encontrado em {out_dir}. Rode step1_extract_reports.py primeiro.")
    manifest = json.loads(m_path.read_text(encoding="utf-8"))
    return _compute_device_mode(cfg, manifest, out_dir) if mode == "device" else _compute_site_mode(cfg, manifest, out_dir)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Motor unificado da metodologia de CTV (both | site | device)")
    p.add_argument("--config", required=True, help="Caminho para o JSON de configuração")
    p.add_argument("--mode", choices=["both", "site", "device"], default=None, help="Sobrescrever modo (both | site | device)")
    a = p.parse_args()
    compute_methodology(a.config, mode_override=a.mode)
