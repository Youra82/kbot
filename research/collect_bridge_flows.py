"""Sammelt 12 Monate grosse USDC/USDT-Transfers an Bridge-Adressen (Ethereum) + Ziel-Chain via Receipt."""
import json, os, sys, time, requests

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
s = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'secret.json')))
URL = f"https://eth-mainnet.g.alchemy.com/v2/{s['alchemy_api_key']}"
USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"; USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
ADDR = {
    "base_std": "0x3154cf16ccdb4c6d922629664174b904d80f2c35",
    "across": "0x5c7bcd6e7de5423a257d81b442095a1a6ced35c5",
    "op_std": "0x99c9fc46f92e8a1c0dec1b1747d010903e884be1",
    "arb_custom": "0xcee284f754e854890e311e3280b767f80797180d",
    "cctp_v1": "0xc4922d64a24675e16e1586e3e3aa56c06fabe907",
    "cctp_v2": "0xfd78ee919681417d192449715b2594ab58f5d002",
    "usdt0": "0x6c96de32cea08842dcc4058c14d3aaad7fa41dee",
    "stg_usdc": "0xc026395860db2d07ee33e05fe50ed7bd583189c7",
    "stg_usdt": "0x933597a323eb81cae705c5bc29985172fd5a3973",
}
MIN_STORE = 50_000
DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 365


def rpc(method, params, retries=6):
    for i in range(retries):
        try:
            r = requests.post(URL, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=90)
            j = r.json()
            if 'error' in j:
                raise RuntimeError(j['error'])
            return j['result']
        except Exception as e:
            print(f"  retry {i+1} {method}: {str(e)[:120]}", flush=True)
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"{method} endgueltig fehlgeschlagen")


def collect_transfers():
    path = os.path.join(OUT, 'transfers.jsonl')
    done = set()
    if os.path.exists(path):
        for line in open(path):
            done.add(json.loads(line)['_src'])
    latest = int(rpc("eth_blockNumber", []), 16)
    frm = latest - DAYS * 7200
    for name, a in ADDR.items():
        if name in done:
            continue
        pk, pages, kept = None, 0, []
        while True:
            p = {"fromBlock": hex(frm), "toBlock": hex(latest), "toAddress": a,
                 "contractAddresses": [USDC, USDT], "category": ["erc20"], "withMetadata": True,
                 "maxCount": "0x3e8", "excludeZeroValue": True}
            if pk:
                p["pageKey"] = pk
            res = rpc("alchemy_getAssetTransfers", [p])
            for t in res['transfers']:
                v = float(t.get('value') or 0)
                if v >= MIN_STORE:
                    kept.append({"src": name, "ts": t['metadata']['blockTimestamp'], "block": int(t['blockNum'], 16),
                                 "tx": t['hash'], "from": t['from'], "value": v, "asset": t.get('asset')})
            pk = res.get('pageKey'); pages += 1
            if pages % 50 == 0:
                print(f"  {name}: {pages} Seiten, {len(kept)} gross", flush=True)
            if not pk:
                break
        with open(path, 'a') as f:
            for k in kept:
                f.write(json.dumps({**k, "_src": name}) + "\n")
            if not kept:
                f.write(json.dumps({"_src": name, "empty": True}) + "\n")
        print(f"{name}: {pages} Seiten, {len(kept)} Transfers >= {MIN_STORE}", flush=True)


def word(data, i):
    d = data[2:]
    return int(d[64 * i:64 * (i + 1)], 16)


def decode_dest(src, receipt):
    """Ziel-Chain aus Receipt-Logs bestimmen."""
    logs = receipt.get('logs', [])
    if src in ('base_std',):
        return 'base'
    if src == 'op_std':
        return 'optimism'
    if src == 'arb_custom':
        return 'arbitrum'
    if src in ('cctp_v1', 'cctp_v2'):
        msgr = {"cctp_v1": "0xbd3fa81b58ba92a82136038b25adec7066af3155",
                "cctp_v2": "0x28b5a0e9c621a5badaa536219b3a228c8168cf5d"}[src]
        for lg in logs:
            if lg['address'].lower() == msgr and len(lg['data']) >= 2 + 64 * 3:
                return f"cctp:{word(lg['data'], 2)}"
        return 'cctp:?'
    if src in ('usdt0', 'stg_usdc', 'stg_usdt'):
        a = ADDR[src]
        for lg in logs:
            # OFTSent(bytes32 indexed guid, uint32 dstEid, address indexed from, uint256, uint256)
            if lg['address'].lower() == a and len(lg['topics']) == 3 and len(lg['data']) == 2 + 64 * 3:
                return f"lz:{word(lg['data'], 0)}"
        return 'lz:?'
    if src == 'across':
        for lg in logs:
            if lg['address'].lower() == ADDR['across'] and len(lg['topics']) >= 3:
                return f"chain:{int(lg['topics'][1], 16)}"
        return 'chain:?'
    return '?'


def resolve_dest(min_val=100_000):
    path = os.path.join(OUT, 'transfers.jsonl')
    outp = os.path.join(OUT, 'dest.json')
    dest = json.load(open(outp)) if os.path.exists(outp) else {}
    rows = [json.loads(l) for l in open(path)]
    todo = [r for r in rows if not r.get('empty') and r['value'] >= min_val and r['src'] not in ('base_std', 'op_std', 'arb_custom')]
    txs = sorted({r['tx'] for r in todo} - set(dest))
    src_of = {r['tx']: r['src'] for r in todo}
    print(f"Receipts zu holen: {len(txs)}", flush=True)
    B = 10
    for i in range(0, len(txs), B):
        chunk = txs[i:i + B]
        body = [{"jsonrpc": "2.0", "id": j, "method": "eth_getTransactionReceipt", "params": [h]} for j, h in enumerate(chunk)]
        for attempt in range(6):
            try:
                resp = requests.post(URL, json=body, timeout=120).json()
                if isinstance(resp, dict):
                    raise RuntimeError(resp)
                bad = [x for x in resp if 'error' in x]
                if bad:
                    raise RuntimeError(bad[0]['error'])
                break
            except Exception as e:
                print(f"  batch retry {attempt+1}: {str(e)[:120]}", flush=True)
                time.sleep(4 * (attempt + 1))
        else:
            raise RuntimeError("Receipt-Batch fehlgeschlagen")
        time.sleep(0.5)
        for x in resp:
            h = chunk[x['id']]
            dest[h] = decode_dest(src_of[h], x['result'] or {})
        if (i // B) % 300 == 0:
            json.dump(dest, open(outp, 'w'))
            print(f"  {i + len(chunk)}/{len(txs)}", flush=True)
    json.dump(dest, open(outp, 'w'))
    print("Receipts fertig", flush=True)


if __name__ == '__main__':
    collect_transfers()
    resolve_dest()
