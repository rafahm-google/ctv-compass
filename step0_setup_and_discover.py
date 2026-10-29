#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Step 0 — OAuth2 Setup & Automatic CM360/DV360 Campaign + Floodlight Discovery."""

import argparse
import datetime
import json
from pathlib import Path

from googleapiclient.discovery import build

from common import (
    BASE_DIR,
    CM360_SCOPES,
    DEFAULT_CTV_PLATFORMS,
    DEFAULT_NON_CTV_PLATFORMS,
    DV360_SCOPES,
    classify_tag,
    load_credentials,
    norm_slug,
    resolve_path,
)


def discover_and_build_config(args):
    creds_cm = load_credentials(args.token_cm360, args.client_secrets, CM360_SCOPES)
    cm = build("dfareporting", "v5", credentials=creds_cm)

    profiles = cm.userProfiles().list().execute().get("items", [])
    if not profiles:
        raise RuntimeError("Nenhum User Profile CM360 encontrado para esta conta Google.")

    selected = next(
        (p for p in profiles if args.profile_id and str(p["profileId"]) == str(args.profile_id)),
        profiles[0],
    )
    prof_id = str(selected["profileId"])
    acc_id = str(selected["accountId"])
    print(f"[CM360] Profile selecionado: {prof_id} ({selected.get('userName')} - {selected.get('accountName')})")

    camp = cm.campaigns().get(profileId=prof_id, id=str(args.campaign_id)).execute()
    camp_name = camp.get("name", "")
    adv_id = str(camp.get("advertiserId"))
    start_date = args.start_date or camp.get("startDate")
    end_date = args.end_date or min(camp.get("endDate", "2099-12-31"), datetime.date.today().isoformat())

    adv = cm.advertisers().get(profileId=prof_id, id=adv_id).execute()
    adv_name = adv.get("name", "")
    fl_config_id = str(adv.get("floodlightConfigurationId", adv_id))

    purchase_ids, purchase_labels = [], {}
    if args.purchase_activity_ids:
        wanted = {x.strip() for x in args.purchase_activity_ids.split(",") if x.strip()}
        acts = cm.floodlightActivities().list(profileId=prof_id, floodlightConfigurationId=fl_config_id).execute().get("floodlightActivities", [])
        for a in acts:
            if str(a.get("id")) in wanted:
                aid = str(a["id"])
                purchase_ids.append(aid)
                purchase_labels[aid] = a.get("name", aid)
    else:
        excl = [norm_slug(k) for k in (args.exclude_tag_keywords or "").split(",") if k.strip()]
        acts = cm.floodlightActivities().list(profileId=prof_id, floodlightConfigurationId=fl_config_id).execute().get("floodlightActivities", [])
        for a in acts:
            aid, aname = str(a.get("id")), a.get("name", "")
            if any(x in norm_slug(aname) for x in excl):
                continue
            rec, lbl = classify_tag(aname)
            if rec:
                purchase_ids.append(aid)
                purchase_labels[aid] = lbl

    dv_block = {"enabled": False, "advertiser_id": "", "campaign_id": "", "token_dv360_path": args.token_dv360}
    if args.dv360_advertiser_id:
        creds_dv = load_credentials(args.token_dv360, args.client_secrets, DV360_SCOPES)
        dv4 = build("displayvideo", "v4", credentials=creds_dv)
        dv_camps = dv4.advertisers().campaigns().list(advertiserId=str(args.dv360_advertiser_id)).execute().get("campaigns", [])
        kw = norm_slug(args.brand_keyword or camp_name)
        matched_dv = str(args.dv360_campaign_id or "")
        if not matched_dv:
            for dc in dv_camps:
                if kw and kw in norm_slug(dc.get("displayName", "")):
                    matched_dv = str(dc["campaignId"])
                    break
        dv_block = {
            "enabled": True,
            "advertiser_id": str(args.dv360_advertiser_id),
            "campaign_id": matched_dv,
            "token_dv360_path": args.token_dv360,
        }

    slug = args.case_slug or f"camp_{args.campaign_id}_{args.mode}"
    cfg = {
        "case_slug": slug,
        "brand_name": args.brand_name or adv_name,
        "agency_name": args.agency_name or "Agência",
        "identification_mode": args.mode if args.mode in ("both", "device", "site") else "both",
        "cm360": {
            "profile_id": prof_id,
            "account_id": acc_id,
            "advertiser_id": adv_id,
            "floodlight_config_id": fl_config_id,
            "campaign_id": str(args.campaign_id),
            "campaign_name": camp_name,
            "brand_keyword_normalized": norm_slug(args.brand_keyword or camp_name),
            "token_reporting_path": args.token_cm360,
            "purchase_activity_ids": purchase_ids,
            "purchase_activity_labels": purchase_labels,
        },
        "dv360": dv_block,
        "date_window": {"start_date": start_date, "end_date": end_date},
        "output_dir": f"outputs/{slug}",
    }
    if args.mode in ("both", "device"):
        cfg["ctv_platform_types"] = DEFAULT_CTV_PLATFORMS
        cfg["non_ctv_platform_types"] = DEFAULT_NON_CTV_PLATFORMS

    out_cfg = resolve_path(f"configs/{slug}.json")
    out_cfg.parent.mkdir(parents=True, exist_ok=True)
    out_cfg.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[ETAPA 0 CONCLUÍDA] Configuração portátil salva em: {out_cfg.relative_to(BASE_DIR)}")
    return str(out_cfg)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Setup OAuth2 e descoberta automática de campanha CM360/DV360")
    p.add_argument("--client-secrets", default="client_secrets.json", help="JSON OAuth Desktop App do Google Cloud")
    p.add_argument("--token-cm360", default="token.json", help="Caminho relativo para salvar/ler token CM360")
    p.add_argument("--token-dv360", default="token_dv360.json", help="Caminho relativo para salvar/ler token DV360")
    p.add_argument("--profile-id", default=None, help="CM360 User Profile ID (opcional)")
    p.add_argument("--campaign-id", required=True, help="CM360 Campaign ID")
    p.add_argument("--mode", choices=["both", "site", "device"], default="both", help="Critério CTV: both (ambas as visões), site (nome) ou device (Smart TV + STB)")
    p.add_argument("--case-slug", default=None, help="Slug do estudo (ex.: minha_campanha)")
    p.add_argument("--brand-name", default=None, help="Nome da marca/campanha para o relatório")
    p.add_argument("--agency-name", default="Agência", help="Nome da agência")
    p.add_argument("--brand-keyword", default=None, help="Palavra-chave da marca (sem underscores)")
    p.add_argument("--purchase-activity-ids", default=None, help="IDs Floodlight de compra separados por vírgula (1 por plataforma)")
    p.add_argument("--exclude-tag-keywords", default="", help="Palavras-chave de outras marcas do grupo para excluir na autodescoberta")
    p.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    p.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    p.add_argument("--dv360-advertiser-id", default=None, help="DV360 Advertiser ID (opcional)")
    p.add_argument("--dv360-campaign-id", default=None, help="DV360 Campaign ID (opcional)")
    discover_and_build_config(p.parse_args())
