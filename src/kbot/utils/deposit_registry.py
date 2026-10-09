"""
deposit_registry.py — Binance-Einzahlungen auf Ethereum: Adressen und Tokens.

Einzige Quelle fuer Live-Waechter UND research/cex/ (Live == Backtest).

Ablauf bei Binance: Kunde -> eigene Einzahladresse -> (Median ~5 min) Sweep an Binance 14.
Eine Adresse, die an Binance 14 sweept, ist eine Binance-Einzahladresse.
"""

BINANCE_HOT = "0x28c6c06298d514db089934071355e5743bf21d60"   # Binance 14 (Sammel-Wallet)

# ERC-20-Contracts (Ethereum) der ueberwachten Alts; alle mit Bitget-USDT-Perp (1 Token je Kontrakt)
TOKENS = {
    'LINK': '0x514910771af9ca656af840dff83e8264ecf986ca', 'UNI': '0x1f9840a85d5af5bf1d1762f925bdaddc4201f984',
    'AAVE': '0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9', 'LDO': '0x5a98fcbea516cf06857215779fd812ca3bef1b32',
    'ENA': '0x57e114b691db790c35207b2e685d4a43181e6061', 'ONDO': '0xfaba6f8e4a5e8ab82f62fe7c39859fa577269be3',
    'PENDLE': '0x808507121b80c02388fad14726482e061b8da827', 'CRV': '0xd533a949740bb3306d119cc777fa900ba034cd52',
    'ETHFI': '0xfe0c30065b384f05761f15d0cc899d4f9f9cc0eb', 'PEPE': '0x6982508145454ce325ddbe47a25d4ec3d2311933',
    'SHIB': '0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce', 'FET': '0xaea46a60368a7bd060eec7df8cba43b7ef41ad85',
    'COMP': '0xc00e94cb662c3520282e6f5717214004a7f26888', 'SNX': '0xc011a73ee8576fb46f5e1c5751ca3b9fe0af2a6f',
    'GRT': '0xc944e90c64b2c07662a292be6244bdf05cda44a7', 'IMX': '0xf57e7e7c23978c3caec3c3548e3d615c346e79ff',
    'SAND': '0x3845badade8e6dff049820680d1f14bd3903a5d0', 'MANA': '0x0f5d2fb29fb7d3cfee444a200298f468908cc942',
    'APE': '0x4d224452801aced8b2f0aebe155379bb5d594381', 'ENS': '0xc18360217d8f7ab5e7c516566761ea12ce7f9d72',
    'WLD': '0x163f8c2467924be0ae7b5347228cabf260318753', '1INCH': '0x111111111117dc0aa78b770fa6a738034120c302',
}
TOKEN_BY_CONTRACT = {a: t for t, a in TOKENS.items()}

# Absender = Boersen-Hot-Wallet (Boerse -> Binance-Verschiebung, im Backtest ohne Effekt). Nur Markierung.
CEX_HOT = {
    '0xa9d1e08c7793af67e9d92fe308d5697fb81d3e43': 'Coinbase', '0x71660c4005ba85c37ccec55d0c4493e66fe775d3': 'Coinbase',
    '0x6cc5f688a315f3dc28a7781717a9a798a59fda7b': 'OKX', '0xf89d7b9c864f589bbf53a82105107622b35eaa40': 'Bybit',
    '0x2910543af39aba0cd09dbb2d50200b3e800a63d2': 'Kraken', '0x21a31ee1afc51d94c2efccaa2092ad1028285549': 'Binance',
    '0xdfd5293d8e347dfe59e90efd55b2956a1343963d': 'Binance', BINANCE_HOT: 'Binance',
}


def sender_type(sender: str) -> str:
    return CEX_HOT.get((sender or '').lower(), '-')
