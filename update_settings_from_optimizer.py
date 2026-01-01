#!/usr/bin/env python3
"""
Update settings.json with optimized portfolio configurations.
Reads config names from command line and updates settings.json accordingly.
"""

import sys
import os
import json
import shutil
from pathlib import Path


def get_project_root():
    """Determine project root directory."""
    return Path(__file__).parent


def parse_config_name(filename):
    """Parse config filename to extract symbol and timeframe."""
    # Example: config_BTCUSDT_1d.json -> ('BTCUSDT', '1d')
    if not filename.startswith('config_') or not filename.endswith('.json'):
        return None, None
    
    parts = filename[7:-5]  # Remove 'config_' and '.json'
    elements = parts.rsplit('_', 1)  # Split from right to get timeframe
    
    if len(elements) == 2:
        symbol, timeframe = elements
        return symbol, timeframe
    return None, None


def symbol_to_trading_pair(symbol):
    """Convert symbol like BTCUSDT to trading pair like BTC/USDT."""
    # If already in format XXXUSDT, convert to XXX/USDT
    if symbol.endswith('USDT') and len(symbol) > 4:
        base = symbol[:-4]  # Remove USDT
        return f"{base}/USDT"
    return f"{symbol}/USDT"


def load_settings_json(project_root):
    """Load current settings.json."""
    settings_path = project_root / 'settings.json'
    if not settings_path.exists():
        print(f"❌ Fehler: settings.json nicht gefunden unter {settings_path}")
        return None
    
    try:
        with open(settings_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden von settings.json: {e}")
        return None


def load_config_json(project_root, config_name):
    """Load a strategy config JSON file."""
    config_path = project_root / 'src' / 'kbot' / 'strategy' / 'configs' / config_name
    if not config_path.exists():
        print(f"⚠️  Warnung: Config-Datei nicht gefunden: {config_name}")
        return None
    
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Fehler beim Laden von {config_name}: {e}")
        return None


def build_strategy_entry(symbol, config_data):
    """Build a strategy entry for settings.json from config data."""
    strategy = config_data.get('strategy', {})
    return {
        'symbol': symbol_to_trading_pair(symbol),
        'interval': config_data.get('market', {}).get('timeframe', '1d'),
        'params': {
            'buy': strategy.get('buy', {}),
            'sell': strategy.get('sell', {}),
            'roi': strategy.get('roi', {}),
            'stoploss': strategy.get('stoploss', -0.05),
            'trailing_stop': strategy.get('trailing_stop', False)
        }
    }


def main():
    """Main function."""
    project_root = get_project_root()
    
    if len(sys.argv) < 2:
        print("❌ Fehler: Keine Config-Dateien angegeben")
        print("Verwendung: python3 update_settings_from_optimizer.py config1.json config2.json ...")
        sys.exit(1)
    
    config_names = sys.argv[1:]
    
    print("\n" + "="*60)
    print("Aktualisiere settings.json mit optimierten Strategien...")
    print("="*60 + "\n")
    
    # Load current settings
    settings = load_settings_json(project_root)
    if settings is None:
        sys.exit(1)
    
    # Create backup
    settings_path = project_root / 'settings.json'
    backup_path = project_root / 'settings.json.backup'
    try:
        shutil.copy2(settings_path, backup_path)
        print(f"✓ Backup erstellt: settings.json.backup")
    except Exception as e:
        print(f"❌ Fehler beim Erstellen von Backup: {e}")
        sys.exit(1)
    
    # Build new strategies list
    new_strategies = []
    successful_configs = 0
    
    for config_name in config_names:
        config_name = config_name.strip()
        symbol, timeframe = parse_config_name(config_name)
        
        if symbol is None:
            print(f"⚠️  Warnung: Konnte {config_name} nicht parsen")
            continue
        
        config_data = load_config_json(project_root, config_name)
        if config_data is None:
            continue
        
        strategy_entry = build_strategy_entry(symbol, config_data)
        new_strategies.append(strategy_entry)
        successful_configs += 1
        print(f"  ✓ {config_name}")
    
    if successful_configs == 0:
        print("❌ Fehler: Keine Strategien konnten geladen werden")
        sys.exit(1)
    
    # Update settings
    settings['strategies'] = new_strategies
    
    # Save updated settings
    try:
        with open(settings_path, 'w') as f:
            json.dump(settings, f, indent=2)
        print(f"\n✓ settings.json wurde mit {successful_configs} Strategien aktualisiert")
        print("="*60)
        sys.exit(0)
    except Exception as e:
        print(f"❌ Fehler beim Speichern von settings.json: {e}")
        print("   Backup: settings.json.backup bleibt erhalten")
        sys.exit(1)


if __name__ == '__main__':
    main()
