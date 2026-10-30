#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline assert-based self-check for CTV Compass ('site', 'device', 'both' + Web Portal)."""

import json
import tempfile
from pathlib import Path

from step2_compute_methodology import compute_methodology
from step3_generate_html import generate_html_report


def _write_cm_csv(path: Path, body: str) -> str:
    path.write_text("Report Metadata\nReport Fields\n" + body.strip() + "\nGrand Total,---\n", encoding="utf-8")
    return f"raw_reports/{path.name}"


def run_self_check() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        raw = root / "raw_reports"
        raw.mkdir(parents=True)

        # 1. Site-mode synthetic fixtures (Total cost = 1500.00; Total Reach = 1000; Duplicate CTV = 300 [30%])
        m_site = {
            "generated_at_utc": "2026-10-29T00:00:00Z",
            "cm360_reports": {
                "std_site_cost_conv": {"path": _write_cm_csv(raw / "s_cost.csv", """
Campaign,Campaign ID,Site (CM360),Placement,Placement ID,Impressions,Clicks,DV360 Cost (Account Currency),Media Cost
Camp_Test,999,DV360_YoutubeCTV,P1,10,50000,0,1000.00,800.00
Camp_Test,999,DV360-DemandGen,P2,20,40000,500,500.00,400.00
""")},
                "std_floodlight_activities": {"path": _write_cm_csv(raw / "s_fl.csv", """
Campaign,Campaign ID,Site (CM360),Attributed Event Platform Type,Activity Group,Activity,Activity ID,Total Conversions,Total Revenue,View-through Conversions,Click-through Conversions
Camp_Test,999,DV360_YoutubeCTV,Connected TV,G,Purchase,101,5,1000.00,5,0
Camp_Test,999,DV360_YoutubeCTV,Connected TV,G,View_Item,102,250,0.00,250,0
Camp_Test,999,DV360_YoutubeCTV,Connected TV,G,DuplicatePixel,999,5,1000.00,5,0
Camp_Test,999,DV360-DemandGen,Smartphone,G,Purchase,101,45,6750.00,15,30
Camp_Test,999,DV360-DemandGen,Smartphone,G,View_Item,102,4500,0.00,1500,3000
""")},
                "reach_campaign_total": {"path": _write_cm_csv(raw / "s_rtot.csv", """
Campaign,Unique Reach: Impression Reach,Unique Reach: Impression Reach (Co-Viewed),Unique Reach: Average Impression Frequency,Unique Reach: Average Impression Frequency (Co-Viewed)
Camp_Test,1000,1300,4.5,3.5
""")},
                "reach_site_coviewed": {"path": _write_cm_csv(raw / "s_rcov.csv", """
Campaign,Site (CM360),Unique Reach: Impression Reach,Unique Reach: Impression Reach (Co-Viewed),Unique Reach: Average Impression Frequency,Unique Reach: Average Impression Frequency (Co-Viewed)
Camp_Test,DV360_YoutubeCTV,400,600,3.0,2.0
Camp_Test,DV360-DemandGen,900,900,4.0,4.0
""")},
                "reach_site_overlap": {"path": _write_cm_csv(raw / "s_rovl.csv", """
Campaign,Site (CM360),Unique Reach: Exclusive Impression Reach,Unique Reach: Exclusive Impression Reach Percent,Unique Reach: Duplicate Impression Reach,Unique Reach: Duplicate Impression Reach Percent
Camp_Test,DV360_YoutubeCTV,100,25.0,300,75.0
Camp_Test,DV360-DemandGen,600,66.67,300,33.33
""")},
            },
            "dv360_reports": {},
        }

        # P2C: 1 Solo CTV (R$ 200), 5 Combo CTV+NonCTV (1 NonCTV touch each, AOV R$ 200), 5 Control Multi NonCTV (2 touches each, AOV R$ 150) => Total = 11 orders
        p2c_lines = ["Meta header", "Conversion ID,Activity ID,Activity,Interaction Number,Site (CM360),Campaign,Campaign ID,Placement ID,Ad ID,Platform Type,Total Conversions,Total Revenue"]
        p2c_lines += ["C_SOLO,101,Purchase,,,,,,,Smartphone,1,200.00", "C_SOLO,101,Purchase,1,DV360_YoutubeCTV,Camp_Test,999,10,100,Connected TV,0,0"]
        for i in range(5):
            p2c_lines += [
                f"C_CMB_{i},101,Purchase,,,,,,,Smartphone,1,200.00",
                f"C_CMB_{i},101,Purchase,2,DV360_YoutubeCTV,Camp_Test,999,10,100,Connected TV,0,0",
                f"C_CMB_{i},101,Purchase,1,DV360-DemandGen,Camp_Test,999,20,200,Smartphone,0,0",
                f"C_CTL_{i},101,Purchase,,,,,,,Smartphone,1,150.00",
                f"C_CTL_{i},101,Purchase,2,DV360-DemandGen,Camp_Test,999,20,200,Smartphone,0,0",
                f"C_CTL_{i},101,Purchase,1,Paid Search,Search_Camp,888,30,300,Smartphone,0,0",
            ]
        p2c_lines += ["C_DUP,999,PixelUnico,,,,,,,Smartphone,1,9999.00", "C_DUP,999,PixelUnico,1,DV360_YoutubeCTV,Camp_Test,999,10,100,Connected TV,0,0"]
        (raw / "p2c.csv").write_text("\n".join(p2c_lines) + "\n", encoding="utf-8")
        m_site["cm360_reports"]["p2c_14d"] = {"path": "raw_reports/p2c.csv"}
        (root / "extraction_manifest.json").write_text(json.dumps(m_site), encoding="utf-8")

        cfg = {
            "case_slug": "self_check",
            "brand_name": "SelfCheck Brand",
            "agency_name": "Agency",
            "identification_mode": "site",
            "cm360": {
                "profile_id": "1", "account_id": "1", "advertiser_id": "1", "floodlight_config_id": "1",
                "campaign_id": "999", "campaign_name": "Camp_Test", "brand_keyword_normalized": "camptest",
                "purchase_activity_ids": ["101"], "purchase_activity_labels": {"101": "Web Purchase"},
                "product_activity_ids": ["102"], "product_activity_labels": {"102": "Web Produto (View_Item)"},
            },
            "dv360": {"enabled": False},
            "date_window": {"start_date": "2026-09-01", "end_date": "2026-09-30"},
            "output_dir": str(root),
        }
        cfg_path = root / "cfg.json"
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

        res_site_path = compute_methodology(str(cfg_path), mode_override="site")
        res_site = json.loads(Path(res_site_path).read_text(encoding="utf-8"))
        b_site = res_site["ctv_block_consolidated"]
        assert abs(res_site["campaign_totals"]["std_conversions"] - 50.0) < 1e-6, "Duplicate Floodlight 999 leaked!"
        assert res_site["funnel_cvr_efficiency"]["metric_source"] == "cvr_produto_compra"
        assert abs(res_site["funnel_cvr_efficiency"]["ctv_block"]["capped_afe_pct"] - 50.0) < 1e-6
        assert abs(b_site["total_attributed_conversions"] - 2.65) < 1e-6, f"Unexpected site convs: {b_site['total_attributed_conversions']}"
        assert abs(b_site["total_attributed_revenue"] - 530.0) < 1e-6, f"Unexpected site rev: {b_site['total_attributed_revenue']}"
        html_site = Path(generate_html_report(str(cfg_path), mode_override="site"))
        assert html_site.exists() and html_site.stat().st_size > 10_000
        site_txt = html_site.read_text(encoding="utf-8")
        assert "Diagnóstico Comportamental no P2C" in site_txt and "Média Toques Não-CTV" in site_txt
        assert "× economia de toques" not in site_txt.lower()

        # 2. Device-mode synthetic fixtures (Inclusion-Exclusion: |CTV|=500 + |NonCTV|=800 - |U|=1000 => Exact Overlap = 300; click-tracker P3 = 0 imp / 100 clicks)
        m_dev = {
            "generated_at_utc": "2026-10-29T00:00:00Z",
            "cm360_reports": {
                "std_device_site_placement_ad": {"path": _write_cm_csv(raw / "d_std.csv", """
Campaign,Campaign ID,Site (CM360),Placement,Placement ID,Ad,Ad ID,Platform Type,Impressions,Clicks,DV360 Cost (Account Currency),Media Cost
Camp_Test,999,DV360_YoutubeCTV,P1,10,A1,100,Connected TV,50000,0,1000.00,800.00
Camp_Test,999,DV360-DemandGen,P2,20,A2,200,Connected TV,10000,0,200.00,150.00
Camp_Test,999,DV360-DemandGen,P2,20,A2,200,Smartphone,30000,500,300.00,250.00
Camp_Test,999,Partner_ClickTracker,P3,30,A3,300,Smartphone,0,100,0.00,0.00
""")},
                "std_advertiser_device_map": {"path": _write_cm_csv(raw / "d_adv.csv", """
Campaign,Campaign ID,Site (CM360),Placement,Placement ID,Platform Type,Impressions,Clicks
Camp_Test,999,DV360_YoutubeCTV,P1,10,Connected TV,50000,0
Camp_Test,999,DV360-DemandGen,P2,20,Connected TV,10000,0
Camp_Test,999,DV360-DemandGen,P2,20,Smartphone,30000,500
""")},
                "std_device_floodlights": {"path": _write_cm_csv(raw / "d_fl.csv", """
Campaign,Campaign ID,Site (CM360),Placement,Placement ID,Platform Type,Activity Group,Activity,Activity ID,Total Conversions,Total Revenue,View-through Conversions,Click-through Conversions
Camp_Test,999,DV360_YoutubeCTV,P1,10,Smartphone,G,Purchase,101,5,1000.00,5,0
Camp_Test,999,DV360-DemandGen,P2,20,Smartphone,G,Purchase,101,40,6000.00,16,24
Camp_Test,999,Partner_ClickTracker,P3,30,Desktop,G,Purchase,101,5,750.00,0,5
""")},
                "std_event_platform_floodlights": {"path": _write_cm_csv(raw / "d_ev_fl.csv", """
Campaign,Campaign ID,Site (CM360),Attributed Event Platform Type,Activity Group,Activity,Activity ID,Total Conversions,Total Revenue,View-through Conversions,Click-through Conversions
Camp_Test,999,DV360_YoutubeCTV,Connected TV,G,Purchase,101,5,1000.00,5,0
Camp_Test,999,DV360_YoutubeCTV,Connected TV,G,View_Item,102,200,0.00,200,0
Camp_Test,999,DV360-DemandGen,Connected TV,G,Purchase,101,10,1500.00,10,0
Camp_Test,999,DV360-DemandGen,Connected TV,G,View_Item,102,300,0.00,300,0
Camp_Test,999,DV360-DemandGen,Smartphone,G,Purchase,101,30,4500.00,6,24
Camp_Test,999,DV360-DemandGen,Smartphone,G,View_Item,102,3000,0.00,1000,2000
Camp_Test,999,Partner_ClickTracker,Smartphone,G,Purchase,101,5,750.00,0,5
Camp_Test,999,Partner_ClickTracker,Smartphone,G,View_Item,102,500,0.00,0,500
""")},
                "reach_campaign_total": m_site["cm360_reports"]["reach_campaign_total"],
                "reach_by_platform": {"path": _write_cm_csv(raw / "d_rplat.csv", """
Platform Type,Unique Reach: Impression Reach,Unique Reach: Impression Reach (Co-Viewed),Unique Reach: Average Impression Frequency
Connected TV,500,750,3.0
Smartphone,800,800,3.5
""")},
                "reach_ctv_devices_block": {"path": _write_cm_csv(raw / "d_rctv.csv", """
Campaign,Unique Reach: Impression Reach,Unique Reach: Impression Reach (Co-Viewed),Unique Reach: Average Impression Frequency,Unique Reach: Average Impression Frequency (Co-Viewed)
Camp_Test,500,750,3.0,2.0
""")},
                "reach_nonctv_devices_block": {"path": _write_cm_csv(raw / "d_rnon.csv", """
Campaign,Unique Reach: Impression Reach,Unique Reach: Impression Reach (Co-Viewed),Unique Reach: Average Impression Frequency,Unique Reach: Average Impression Frequency (Co-Viewed)
Camp_Test,800,800,3.5,3.5
""")},
                "reach_site_by_platform": {"path": _write_cm_csv(raw / "d_rsp.csv", """
Site (CM360),Platform Type,Unique Reach: Impression Reach,Unique Reach: Impression Reach (Co-Viewed)
DV360_YoutubeCTV,Connected TV,400,600
DV360-DemandGen,Connected TV,200,280
DV360-DemandGen,Smartphone,800,800
""")},
                "reach_site_ctv_devices": {"path": _write_cm_csv(raw / "d_rsctv.csv", """
Site (CM360),Unique Reach: Impression Reach,Unique Reach: Impression Reach (Co-Viewed),Unique Reach: Average Impression Frequency
DV360_YoutubeCTV,400,600,3.0
DV360-DemandGen,200,280,2.0
""")},
                "reach_site_nonctv_devices": {"path": _write_cm_csv(raw / "d_rsnon.csv", """
Site (CM360),Unique Reach: Impression Reach,Unique Reach: Impression Reach (Co-Viewed),Unique Reach: Average Impression Frequency
DV360-DemandGen,800,800,3.5
""")},
                "reach_site_all_coviewed": m_site["cm360_reports"]["reach_site_coviewed"],
                "reach_site_overlap_all": m_site["cm360_reports"]["reach_site_overlap"],
                "p2c_14d_device_enriched": {"path": "raw_reports/p2c.csv"},
            },
            "dv360_reports": {},
        }
        (root / "extraction_manifest_device.json").write_text(json.dumps(m_dev), encoding="utf-8")

        res_dev_path = compute_methodology(str(cfg_path), mode_override="device")
        res_dev = json.loads(Path(res_dev_path).read_text(encoding="utf-8"))
        b_dev = res_dev["ctv_block_consolidated"]
        ie = res_dev["exact_inclusion_exclusion_block"]
        assert abs(b_dev["cost"] - 1200.0) < 1e-6
        assert abs(b_dev["std_conversions"] - 15.0) < 1e-6
        assert res_dev["meta"]["has_event_platform_type"] is True
        assert res_dev["funnel_cvr_efficiency"]["ctv_block"]["cap_applied"] is True
        assert abs(res_dev["funnel_cvr_efficiency"]["ctv_block"]["capped_afe_pct"] - 50.0) < 1e-6
        assert abs(ie["exact_cross_device_overlap_1plus"] - 300.0) < 1e-6
        assert abs(b_dev["duplicate_reach_1plus_sum"] - 300.0) < 1e-6
        html_dev = Path(generate_html_report(str(cfg_path), mode_override="device"))
        assert html_dev.exists() and html_dev.stat().st_size > 10_000
        dev_txt = html_dev.read_text(encoding="utf-8")
        assert "Diagnóstico Comportamental no P2C" in dev_txt and "Média Toques Não-CTV" in dev_txt
        assert "× economia de toques" not in dev_txt.lower()

        # 3. Unified 'both' mode WITH 'CTV' site naming
        (root / "extraction_manifest.json").unlink(missing_ok=True)
        compute_methodology(str(cfg_path), mode_override="both")
        html_both = Path(generate_html_report(str(cfg_path), mode_override="both"))
        both_txt = html_both.read_text(encoding="utf-8")
        assert "let activeDeck = 0," in both_txt and "switchDeck(1)" in both_txt
        assert "TOTAL BLOCO CTV RECONCILIADO" in both_txt
        assert "Diagnóstico Comportamental no P2C" in both_txt and "Média Toques Não-CTV" in both_txt
        assert "× economia de toques" not in both_txt.lower()

        # 4. Unified 'both' mode WITHOUT 'CTV' site naming + fallback without product tags
        for p in raw.glob("*.csv"):
            txt = "\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines() if ",View_Item,102," not in ln)
            p.write_text(txt.replace("DV360_YoutubeCTV", "DV360-YouTubeVideo"), encoding="utf-8")
        cfg["cm360"]["product_activity_ids"] = []
        cfg["cm360"]["product_activity_labels"] = {}
        cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
        compute_methodology(str(cfg_path), mode_override="both")
        res_site_noname = json.loads((root / "methodology_results.json").read_text(encoding="utf-8"))
        assert res_site_noname["meta"]["naming_detected"] is False
        assert res_site_noname["funnel_cvr_efficiency"]["metric_source"] == "fallback_aov_lift_sem_tag_produto"
        html_both_noname = Path(generate_html_report(str(cfg_path), mode_override="both"))
        noname_txt = html_both_noname.read_text(encoding="utf-8")
        assert "let activeDeck = 1," in noname_txt and "Validação Automática por Device Type Ativada" in noname_txt

    import threading, urllib.request
    from http.server import ThreadingHTTPServer
    from web_app import CTVWebHandler

    srv = ThreadingHTTPServer(("127.0.0.1", 0), CTVWebHandler)
    port = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz") as r:
            assert r.status == 200 and json.loads(r.read())["ok"] is True
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as r:
            html_ui = r.read().decode("utf-8")
            assert r.status == 200 and "CTV Compass" in html_ui
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/bootstrap") as r:
            boot = json.loads(r.read())
            assert r.status == 200 and boot["auth_mode"] in ("unconfigured", "oauth_web", "server_credentials")
    finally:
        srv.shutdown()
        srv.server_close()

    print("[SELF-CHECK OK] CTV Compass ('site', 'device', 'both') e Portal Web validados!")


if __name__ == "__main__":
    run_self_check()
