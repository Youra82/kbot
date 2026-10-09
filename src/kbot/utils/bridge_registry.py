"""
bridge_registry.py — Bridge-Adressen auf Ethereum + Ziel-Chain-Dekodierung.

Einzige Quelle fuer Live-Bot UND research/ (Live == Backtest).

Hinweis: Base/Arbitrum bekommen USDC heute fast nur ueber Circle CCTP,
USDT ueber USDT0 (LayerZero OFT). Die alten Standard-Bridges sind nahezu leer.
Bei CCTP landet der Transfer beim TokenMinter, die Ziel-Chain steht nur im
DepositForBurn-Event des TokenMessengers (Receipt).
"""

USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
STABLECOINS = {"USDC": USDC, "USDT": USDT}
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Empfaenger-Adresse des Transfers -> Quelle
BRIDGES = {
    "base_std": "0x3154cf16ccdb4c6d922629664174b904d80f2c35",
    "across": "0x5c7bcd6e7de5423a257d81b442095a1a6ced35c5",
    "op_std": "0x99c9fc46f92e8a1c0dec1b1747d010903e884be1",
    "arb_custom": "0xcee284f754e854890e311e3280b767f80797180d",
    "cctp_v1": "0xc4922d64a24675e16e1586e3e3aa56c06fabe907",   # TokenMinter v1
    "cctp_v2": "0xfd78ee919681417d192449715b2594ab58f5d002",   # TokenMinter v2
    "usdt0": "0x6c96de32cea08842dcc4058c14d3aaad7fa41dee",     # USDT0 OFT Adapter
    "stg_usdc": "0xc026395860db2d07ee33e05fe50ed7bd583189c7",  # Stargate v2 USDC
    "stg_usdt": "0x933597a323eb81cae705c5bc29985172fd5a3973",  # Stargate v2 USDT
}
SRC_BY_ADDR = {a: n for n, a in BRIDGES.items()}
CCTP_MESSENGER = {
    "cctp_v1": "0xbd3fa81b58ba92a82136038b25adec7066af3155",
    "cctp_v2": "0x28b5a0e9c621a5badaa536219b3a228c8168cf5d",
}
FIXED_DEST = {"base_std": "ETH", "op_std": "OP", "arb_custom": "ARB"}

# Ziel-ID -> handelbarer Token (nur sicher zugeordnete IDs)
CCTP_DOMAIN = {1: 'AVAX', 2: 'OP', 3: 'ARB', 5: 'SOL', 6: 'ETH', 7: 'POL', 8: 'SUI', 9: 'APT', 10: 'UNI',
               11: 'LINEA', 13: 'S', 14: 'WLD', 16: 'SEI', 19: 'HYPE'}
LZ_EID = {30110: 'ARB', 30111: 'OP', 30184: 'ETH', 30109: 'POL', 30102: 'BNB', 30106: 'AVAX', 30367: 'HYPE',
          30362: 'BERA', 30383: 'XPL', 30168: 'SOL'}
ACROSS_CHAIN = {42161: 'ARB', 10: 'OP', 8453: 'ETH', 137: 'POL', 56: 'BNB', 59144: 'LINEA', 480: 'WLD',
                130: 'UNI', 999: 'HYPE', 9745: 'XPL'}


def _word(data: str, i: int) -> int:
    d = data[2:]
    return int(d[64 * i:64 * (i + 1)], 16)


def decode_dest(src: str, receipt: dict) -> str:
    """Ziel-Chain-Kennung ('cctp:3', 'lz:30110', 'chain:42161', ...) aus Receipt-Logs."""
    logs = (receipt or {}).get('logs', [])
    if src in FIXED_DEST:
        return src
    if src in CCTP_MESSENGER:
        msgr = CCTP_MESSENGER[src]
        for lg in logs:
            if lg['address'].lower() == msgr and len(lg['data']) >= 2 + 64 * 3:
                return f"cctp:{_word(lg['data'], 2)}"
        return 'cctp:?'
    if src in ('usdt0', 'stg_usdc', 'stg_usdt'):
        a = BRIDGES[src]
        for lg in logs:
            # OFTSent(bytes32 indexed guid, uint32 dstEid, address indexed from, uint256 sent, uint256 received)
            if lg['address'].lower() == a and len(lg['topics']) == 3 and len(lg['data']) == 2 + 64 * 3:
                return f"lz:{_word(lg['data'], 0)}"
        return 'lz:?'
    if src == 'across':
        for lg in logs:
            if lg['address'].lower() == BRIDGES['across'] and len(lg['topics']) >= 3:
                return f"chain:{int(lg['topics'][1], 16)}"
        return 'chain:?'
    return '?'


def token_of(src: str, dest: str):
    """Quelle + Ziel-Kennung -> Token-Kuerzel (z.B. 'ARB') oder None wenn unbekannt."""
    if src in FIXED_DEST:
        return FIXED_DEST[src]
    if not dest or dest.endswith('?') or ':' not in dest:
        return None
    kind, n = dest.split(':')
    table = {'cctp': CCTP_DOMAIN, 'lz': LZ_EID, 'chain': ACROSS_CHAIN}.get(kind, {})
    return table.get(int(n))
