import json, os, sys, collections, requests
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from kbot.utils.bridge_monitor import AlchemyClient
s = json.load(open(os.path.join(os.path.dirname(__file__), '..', '..', 'secret.json')))
c = AlchemyClient(s['alchemy_api_key'])
LINK = "0x514910771af9ca656af840dff83e8264ecf986ca"
CAND = {"Binance14": "0x28c6c06298d514db089934071355e5743bf21d60", "Binance15": "0x21a31ee1afc51d94c2efccaa2092ad1028285549",
        "Binance16": "0xdfd5293d8e347dfe59e90efd55b2956a1343963d", "Binance20": "0x4976a4a02f38326660d17bf34b431dc6e2eb2327",
        "Binance28": "0x5a52e96bacdabb82fd05763e25335261b270efcb", "Binance18": "0x9696f59e4d72e237be84ffd425dcad154bf96976",
        "Binance17": "0xe2fc31f816a9b94326492132018c3aecc4a93ae1", "Binance8": "0xf977814e90da44bfa03b6295a0616a897441acec",
        "Binance7": "0xbe0eb53f46cd790cd13851d5eff43d12404d33e8", "Binance36": "0xf3b0073e3a7f747c7255446d6c3d0c2c8f1b1a6b"}
latest = int(c.call("eth_blockNumber", []), 16)
for n, a in CAND.items():
    r = c.call("alchemy_getAssetTransfers", [{"fromBlock": hex(latest - 7 * 7200), "toBlock": "latest", "toAddress": a,
              "contractAddresses": [LINK], "category": ["erc20"], "maxCount": "0x3e8", "excludeZeroValue": True}])
    t = r['transfers']; snd = collections.Counter(x['from'] for x in t)
    out = c.call("alchemy_getAssetTransfers", [{"fromBlock": hex(latest - 7 * 7200), "toBlock": "latest", "fromAddress": a,
              "contractAddresses": [LINK], "category": ["erc20"], "maxCount": "0x3e8", "excludeZeroValue": True}])['transfers']
    print(f"{n:10s} rein {len(t):5d}{'+' if r.get('pageKey') else ' '} Absender {len(snd):5d} | raus {len(out):5d} | Summe rein {sum(float(x['value'] or 0) for x in t):,.0f} LINK")
