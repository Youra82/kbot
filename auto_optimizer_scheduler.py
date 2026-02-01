#!/usr/bin/env python3
"""
KBot Auto-Optimizer Scheduler

Verwendung:
    python3 auto_optimizer_scheduler.py --check-only   # Status prüfen
    python3 auto_optimizer_scheduler.py --force        # Sofort optimieren
    python3 auto_optimizer_scheduler.py --daemon       # Als Daemon laufen
"""

import os
import sys
import json
import time
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.absolute()
SETTINGS_FILE = SCRIPT_DIR / "settings.json"
SECRET_FILE = SCRIPT_DIR / "secret.json"
CACHE_DIR = SCRIPT_DIR / "data" / "cache"
LAST_RUN_FILE = CACHE_DIR / ".last_optimization_run"
LOG_FILE = SCRIPT_DIR / "logs" / "scheduler.log"

if sys.platform == "win32":
    VENV_PYTHON = SCRIPT_DIR / ".venv" / "Scripts" / "python.exe"
else:
    VENV_PYTHON = SCRIPT_DIR / ".venv" / "bin" / "python3"

def get_python_executable() -> str:
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable

sys.path.insert(0, str(SCRIPT_DIR / "src"))

def log(message: str, also_print: bool = True):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    if also_print:
        print(log_entry)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(log_entry + "\n")
    except:
        pass

def load_settings() -> dict:
    if not SETTINGS_FILE.exists():
        return {}
    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def load_secrets() -> dict:
    """Lädt die secret.json Datei."""
    if not SECRET_FILE.exists():
        print(f"⚠️ secret.json nicht gefunden: {SECRET_FILE}")
        return {}
    
    try:
        # Debug: Zeige den rohen Dateiinhalt
        with open(SECRET_FILE, "r", encoding="utf-8") as f:
            raw_content = f.read()
            print(f"DEBUG secret.json Pfad: {SECRET_FILE}")
            print(f"DEBUG secret.json Größe: {len(raw_content)} Bytes")
        
        with open(SECRET_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"✓ secret.json geladen, Keys: {list(data.keys())}")
            # Debug: Zeige ob telegram-Werte existieren
            if "telegram" in data:
                tg = data["telegram"]
                print(f"DEBUG telegram.bot_token Länge: {len(tg.get('bot_token', ''))}")
                print(f"DEBUG telegram.chat_id Länge: {len(tg.get('chat_id', ''))}")
            return data
    except Exception as e:
        print(f"Fehler beim Laden von secret.json: {e}")
        return {}

def extract_symbols_timeframes(settings: dict, extract_type: str) -> list:
    opt_settings = settings.get("optimization_settings", {})
    live_settings = settings.get("live_trading_settings", {})
    strategies = live_settings.get("active_strategies", [])
    
    if extract_type == "symbols":
        setting_value = opt_settings.get("symbols_to_optimize", "auto")
        if setting_value == "auto" or not setting_value:
            symbols = set()
            for s in strategies:
                if s.get("active", False):
                    sym = s.get("symbol", "").split("/")[0]
                    if sym:
                        symbols.add(sym)
            return sorted(symbols) if symbols else ["BTC", "ETH"]
        return setting_value if isinstance(setting_value, list) else ["BTC", "ETH"]
    
    elif extract_type == "timeframes":
        setting_value = opt_settings.get("timeframes_to_optimize", "auto")
        if setting_value == "auto" or not setting_value:
            timeframes = set()
            for s in strategies:
                if s.get("active", False):
                    tf = s.get("timeframe", "")
                    if tf:
                        timeframes.add(tf)
            tf_order = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, 
                       "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440}
            sorted_tf = sorted(timeframes, key=lambda x: tf_order.get(x, 999))
            return sorted_tf if sorted_tf else ["1h", "4h"]
        return setting_value if isinstance(setting_value, list) else ["1h", "4h"]
    return []

def send_telegram(message: str) -> bool:
    try:
        from kbot.utils.telegram import send_message
        secrets = load_secrets()
        telegram = secrets.get("telegram", {})
        bot_token = telegram.get("bot_token")
        chat_id = telegram.get("chat_id")
        if bot_token and chat_id:
            send_message(bot_token, chat_id, message)
            log(f"✅ Telegram-Nachricht gesendet")
            return True
        else:
            log(f"⚠️ Telegram nicht konfiguriert (bot_token oder chat_id fehlt)")
    except ImportError as e:
        log(f"Telegram Import-Fehler: {e}")
    except Exception as e:
        log(f"Telegram-Fehler: {e}")
    return False

def get_last_run_time() -> datetime | None:
    if not LAST_RUN_FILE.exists():
        return None
    try:
        with open(LAST_RUN_FILE, "r") as f:
            return datetime.fromtimestamp(int(f.read().strip()))
    except:
        return None

def save_last_run_time():
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LAST_RUN_FILE, "w") as f:
        f.write(str(int(time.time())))

def should_run_now(settings: dict, force: bool = False) -> tuple[bool, str]:
    opt_settings = settings.get("optimization_settings", {})
    if not opt_settings.get("enabled", False):
        return False, "Automatische Optimierung ist deaktiviert"
    if force:
        return True, "Erzwungene Ausführung (--force)"
    
    schedule = opt_settings.get("schedule", {})
    day_of_week = schedule.get("day_of_week", 0)
    hour = schedule.get("hour", 3)
    minute = schedule.get("minute", 0)
    interval_days = schedule.get("interval_days", 7)
    
    now = datetime.now()
    if now.weekday() != day_of_week:
        return False, f"Falscher Tag (heute: {now.weekday()}, geplant: {day_of_week})"
    if now.hour != hour:
        return False, f"Falsche Stunde"
    if abs(now.minute - minute) > 5:
        return False, f"Falsche Minute"
    
    last_run = get_last_run_time()
    if last_run and (now - last_run).days < interval_days:
        return False, f"Intervall nicht erreicht"
    
    return True, "Geplanter Zeitpunkt erreicht"

def run_optimization() -> bool:
    log("Starte Optimierung...")
    settings = load_settings()
    opt_settings = settings.get("optimization_settings", {})
    
    symbols = extract_symbols_timeframes(settings, "symbols")
    timeframes = extract_symbols_timeframes(settings, "timeframes")
    lookback_days = opt_settings.get("lookback_days", 365)
    start_capital = opt_settings.get("start_capital", 1000)
    n_cores = opt_settings.get("cpu_cores", -1)
    n_trials = opt_settings.get("num_trials", 500)
    
    constraints = opt_settings.get("constraints", {})
    max_dd = constraints.get("max_drawdown_pct", 30)
    min_wr = constraints.get("min_win_rate_pct", 50)
    min_pnl = constraints.get("min_pnl_pct", 0)
    
    start_time = time.time()
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    
    optimizer_path = SCRIPT_DIR / "src" / "kbot" / "analysis" / "optimizer.py"
    if not optimizer_path.exists():
        log(f"Fehler: {optimizer_path} nicht gefunden!")
        return False
    
    python_exe = get_python_executable()
    log(f"Python: {python_exe}")
    
    cmd = [
        python_exe, str(optimizer_path),
        "--symbols", " ".join(symbols),
        "--timeframes", " ".join(timeframes),
        "--start_date", start_date,
        "--end_date", end_date,
        "--jobs", str(n_cores),
        "--max_drawdown", str(max_dd),
        "--start_capital", str(start_capital),
        "--min_win_rate", str(min_wr),
        "--trials", str(n_trials),
        "--min_pnl", str(min_pnl),
        "--mode", "strict"
    ]
    
    log(f"")
    log(f"╔══════════════════════════════════════════════════════════════╗")
    log(f"║  AUTO-OPTIMIZER: {len(symbols)} Symbole × {len(timeframes)} Timeframes = {len(symbols) * len(timeframes)} Kombinationen")
    log(f"║  Symbole: {', '.join(symbols)}")
    log(f"║  Timeframes: {', '.join(timeframes)}")
    log(f"║  Trials pro Kombination: {n_trials}")
    log(f"╚══════════════════════════════════════════════════════════════╝")
    log(f"")
    
    try:
        process = subprocess.Popen(cmd, cwd=str(SCRIPT_DIR))
        process.wait()
        returncode = process.returncode
        
        duration = int((time.time() - start_time) / 60)
        save_last_run_time()
        
        if returncode == 0:
            log(f"✅ OPTIMIERUNG ERFOLGREICH ({duration} Minuten)")
            if opt_settings.get("send_telegram_on_completion", True):
                interval_days = opt_settings.get("schedule", {}).get("interval_days", 7)
                send_telegram(f"✅ KBot Auto-Optimierung ABGESCHLOSSEN\n\nDauer: {duration} Minuten\nSymbole: {', '.join(symbols)}\nTimeframes: {', '.join(timeframes)}")
            return True
        else:
            log(f"❌ OPTIMIERUNG FEHLGESCHLAGEN (Exit-Code: {returncode})")
            if opt_settings.get("send_telegram_on_completion", True):
                send_telegram(f"❌ KBot Auto-Optimierung FEHLGESCHLAGEN\n\nFehlercode: {returncode}")
            return False
    except Exception as e:
        log(f"Fehler: {e}")
        return False

def run_daemon(check_interval: int = 60):
    log("Starte Scheduler-Daemon...")
    while True:
        try:
            settings = load_settings()
            should_run, reason = should_run_now(settings)
            if should_run:
                run_optimization()
            time.sleep(check_interval)
        except KeyboardInterrupt:
            break
        except Exception as e:
            log(f"Fehler: {e}")
            time.sleep(check_interval)

def main():
    parser = argparse.ArgumentParser(description="KBot Auto-Optimizer Scheduler")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--interval", type=int, default=60)
    args = parser.parse_args()
    
    settings = load_settings()
    
    if args.check_only:
        should_run, reason = should_run_now(settings)
        log(f"Optimierung fällig: {should_run} - {reason}")
        sys.exit(0 if should_run else 1)
    
    if args.force:
        log("Erzwinge sofortige Optimierung...")
        sys.exit(0 if run_optimization() else 1)
    
    if args.daemon:
        run_daemon(args.interval)
    else:
        should_run, reason = should_run_now(settings)
        log(f"Status: {reason}")
        if should_run:
            run_optimization()

if __name__ == "__main__":
    main()
