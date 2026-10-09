import json, os, sys, collections
import pandas as pd
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
from kbot.utils.bridge_monitor import AlchemyClient
s = json.load(open(os.path.join(os.path.dirname(__file__), '..', '..', 'secret.json')))
c = AlchemyClient(s['alchemy_api_key'])
LINK = "0x514910771af9ca656af840dff83e8264ecf986ca"; HOT = "0x28c6c06298d514db089934071355e5743bf21d60"
latest = int(c.call("eth_blockNumber", []), 16)
sw = c.call("alchemy_getAssetTransfers", [{"fromBlock": hex(latest - 7 * 7200), "toBlock": "latest", "toAddress": HOT,
           "contractAddresses": [LINK], "category": ["erc20"], "maxCount": "0x3e8", "excludeZeroValue": True, "withMetadata": True, "order": "desc"}])['transfers']
big = sorted(sw, key=lambda x: -float(x['value'] or 0))[:12]
lags = []
for x in big:
    addr = x['from']; blk = int(x['blockNum'], 16)
    ins = c.call("alchemy_getAssetTransfers", [{"fromBlock": hex(blk - 3 * 7200), "toBlock": hex(blk), "toAddress": addr,
           "contractAddresses": [LINK], "category": ["erc20"], "maxCount": "0x14", "withMetadata": True, "order": "desc"}])['transfers']
    outs = c.call("alchemy_getAssetTransfers", [{"fromBlock": hex(latest - 30 * 7200), "toBlock": "latest", "fromAddress": addr,
           "contractAddresses": [LINK], "category": ["erc20"], "maxCount": "0x3e8"}])['transfers']
    dest = collections.Counter(o['to'] for o in outs)
    t_sw = pd.Timestamp(x['metadata']['blockTimestamp'])
    if ins:
        t_in = pd.Timestamp(ins[0]['metadata']['blockTimestamp']); lags.append((t_sw - t_in).total_seconds() / 60)
        print(f"Sweep {float(x['value']):>10,.0f} LINK | letzte Einzahlung {float(ins[0]['value'] or 0):>10,.0f} von {ins[0]['from'][:10]} "
              f"| Lag {(t_sw - t_in).total_seconds()/60:6.1f} min | Ziele der Adresse: {len(dest)} ({dest.most_common(1)[0][0][:10]})")
print("Lag Median min:", pd.Series(lags).median())
