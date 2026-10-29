#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unified runner for the CTV Integrated Measurement Pipeline ('site' and 'device' modes)."""

import argparse

from step1_extract_reports import extract_reports
from step2_compute_methodology import compute_methodology
from step3_generate_html import generate_html_report


def run_pipeline(config_path: str, mode: str | None = None, skip_extract: bool = False) -> str:
    if not skip_extract:
        extract_reports(config_path, mode_override=mode)
    compute_methodology(config_path, mode_override=mode)
    return generate_html_report(config_path, mode_override=mode)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Executa o pipeline completo de mensuração integrada de CTV")
    p.add_argument("--config", required=True, help="Caminho para o JSON de configuração (ex.: configs/campaign.example.json)")
    p.add_argument("--mode", choices=["both", "site", "device"], default=None, help="Sobrescrever modo CTV (both | site | device)")
    p.add_argument("--skip-extract", action="store_true", help="Pula extração API e recalcula sobre CSVs já baixados")
    args = p.parse_args()
    run_pipeline(args.config, mode=args.mode, skip_extract=args.skip_extract)
