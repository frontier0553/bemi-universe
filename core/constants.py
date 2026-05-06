# -*- coding: utf-8 -*-
import os
import customtkinter as ctk

# 프로젝트 루트 (files/ 디렉터리)
_BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIG_FILE = os.path.join(_BASE_DIR, "config.json")

# ─────────────────────────────────────────
#  테마 상수
# ─────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT   = "#3B82F6"
SUCCESS  = "#22C55E"
DANGER   = "#EF4444"
PURPLE   = "#8B5CF6"

DARK  = {"BG_MAIN": "#0F172A", "BG_CARD": "#1E293B", "TEXT_DIM": "#94A3B8", "TEXT_MAIN": "#FFFFFF", "BORDER": "#334155"}
LIGHT = {"BG_MAIN": "#F1F5F9", "BG_CARD": "#FFFFFF",  "TEXT_DIM": "#64748B", "TEXT_MAIN": "#1E293B", "BORDER": "#94A3B8"}

BG_CARD  = DARK["BG_CARD"]
BG_MAIN  = DARK["BG_MAIN"]
TEXT_DIM = DARK["TEXT_DIM"]
