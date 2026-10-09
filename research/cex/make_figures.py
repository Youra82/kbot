"""Erzeugt die README-Grafiken (docs/img/*.svg, hell + dunkel) aus den Backtest-Daten."""
import os
import numpy as np, pandas as pd
from test import load, run, TOKENS, D, COST, SPLIT

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img')
FONT = "-apple-system, 'Segoe UI', Helvetica, Arial, sans-serif"
THEME = {
    'light': dict(surface='#fcfcfb', text='#0b0b0b', text2='#52514e', muted='#898781', grid='#e1e0d9',
                  axis='#c3c2b7', s1='#2a78d6', s2='#eb6834', border='rgba(11,11,11,0.10)', box='#f4f3f0',
                  wash1='rgba(42,120,214,0.10)'),
    'dark': dict(surface='#1a1a19', text='#ffffff', text2='#c3c2b7', muted='#898781', grid='#2c2c2a',
                 axis='#383835', s1='#3987e5', s2='#d95926', border='rgba(255,255,255,0.10)', box='#242422',
                 wash1='rgba(57,135,229,0.14)'),
}


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def svg(w, h, body, c, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'font-family="{FONT}" role="img" aria-label="{esc(title)}">'
            f'<title>{esc(title)}</title>'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="12" fill="{c["surface"]}" stroke="{c["border"]}"/>'
            f'{body}</svg>')


def text(x, y, s, fill, size=13, weight=400, anchor='start'):
    return f'<text x="{x:.1f}" y="{y:.1f}" fill="{fill}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}">{esc(s)}</text>'


# ---------------------------------------------------------------- 1) Ablauf
def flow(c):
    W, H = 900, 262
    b = [text(28, 40, 'So entsteht das Signal', c['text'], 17, 600),
         text(28, 62, 'Die Einzahlung ist on-chain sichtbar, bevor Binance sie gutschreibt', c['text2'], 13)]
    steps = [('Wal', 'schickt ≥ 500k $', 'eines Altcoins'),
             ('Binance-', 'Einzahladresse', 'on-chain sichtbar'),
             ('Binance', 'schreibt gut', 'nach ~1–5 min'),
             ('Verkauf', 'Kurs gerät', 'unter Druck')]
    x0, bw, bh, gap, y = 28, 180, 92, 44, 92
    for i, (a, l1, l2) in enumerate(steps):
        x = x0 + i * (bw + gap)
        b.append(f'<rect x="{x}" y="{y}" width="{bw}" height="{bh}" rx="10" fill="{c["box"]}" stroke="{c["border"]}"/>')
        b.append(text(x + bw / 2, y + 34, a, c['text'], 15, 600, 'middle'))
        b.append(text(x + bw / 2, y + 56, l1, c['text2'], 13, 400, 'middle'))
        b.append(text(x + bw / 2, y + 74, l2, c['muted'], 12, 400, 'middle'))
        if i < 3:
            ax = x + bw + 8
            b.append(f'<line x1="{ax}" y1="{y + bh / 2}" x2="{ax + gap - 16}" y2="{y + bh / 2}" stroke="{c["muted"]}" stroke-width="2"/>')
            b.append(f'<path d="M{ax + gap - 16},{y + bh / 2 - 5} l8,5 l-8,5 z" fill="{c["muted"]}"/>')
    # KBot-Zweig: liest an Schritt 2, handelt auf Bitget
    kx = x0 + (bw + gap) + bw / 2
    ky = y + bh
    bx, bwk = 590, 290
    b.append(f'<path d="M{kx},{ky + 4} V{ky + 40} H{bx}" fill="none" stroke="{c["s1"]}" stroke-width="2" stroke-linejoin="round"/>')
    b.append(f'<circle cx="{kx}" cy="{ky + 4}" r="5" fill="{c["s1"]}" stroke="{c["surface"]}" stroke-width="2"/>')
    b.append(f'<rect x="{bx}" y="{ky + 18}" width="{bwk}" height="46" rx="10" fill="{c["wash1"]}" stroke="{c["s1"]}" stroke-width="1.5"/>')
    b.append(text(bx + bwk / 2, ky + 37, 'KBot: Short auf Bitget', c['text'], 13, 600, 'middle'))
    b.append(text(bx + bwk / 2, ky + 55, 'Einstieg nach 1–2 min · Ausstieg nach 60 min', c['text2'], 12, 400, 'middle'))
    b.append(text(kx + 12, ky + 34, 'KBot liest jeden Block mit', c['text2'], 12))
    return svg(W, H, ''.join(b), c, 'Ablauf: Wal-Einzahlung auf Binance bis Short auf Bitget')


# ---------------------------------------------------------------- 2) Kapitalkurve
def equity_curves():
    data = {t: load(t) for t in TOKENS if os.path.exists(os.path.join(D, 'deposits', f'{t}.json'))}
    ev = run(data, 5e5, 60)
    ev = ev[ev.t >= pd.Timestamp('2026-05-01', tz='UTC')].sort_values('t').reset_index(drop=True)
    mae = []
    for _, e in ev.iterrows():
        w = data[e.tok][0][e.t:e.t + pd.Timedelta(minutes=60)]
        mae.append(w.max() / w.iloc[0] - 1)
    ev['mae'] = mae
    curves = {}
    for name, cost in [('limit', 0.0004), ('market', 0.0012)]:
        eq, pts = 100.0, [(pd.Timestamp('2026-05-01', tz='UTC'), 100.0)]
        for _, e in ev.iterrows():
            margin = eq / 3
            eq += -margin if e.mae >= 0.9 / 5 else margin * 5 * (e.short - cost)
            pts.append((e.t, eq))
        curves[name] = pts
    return curves


def equity(c, curves):
    W, H, L, R, T, B = 900, 380, 64, 120, 84, 44
    t0, t1 = pd.Timestamp('2026-05-01', tz='UTC'), pd.Timestamp('2026-10-09', tz='UTC')
    ymax = max(v for pts in curves.values() for _, v in pts)
    top = int(np.ceil(ymax / 100) * 100)
    X = lambda t: L + (t - t0) / (t1 - t0) * (W - L - R)
    Y = lambda v: T + (1 - v / top) * (H - T - B)
    b = [text(28, 36, 'Simulation: 100 USDT seit 01.05.2026', c['text'], 17, 600),
         text(28, 58, '532 Signale · 5x Hebel · Margin ⅓ je Trade · Short 60 min', c['text2'], 13)]
    # Legende
    lx = W - R - 300
    for i, (k, lab) in enumerate([('s1', 'Limit-Orders (0,04 %)'), ('s2', 'Market-Orders (0,12 %)')]):
        x = lx + i * 170
        b.append(f'<line x1="{x}" y1="31" x2="{x + 18}" y2="31" stroke="{c[k]}" stroke-width="2" stroke-linecap="round"/>')
        b.append(text(x + 24, 35, lab, c['text2'], 12))
    # Gitter + y-Achse
    for v in range(0, top + 1, 100):
        y = Y(v)
        b.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="{c["grid" if v else "axis"]}" stroke-width="1"/>')
        b.append(text(L - 10, y + 4, f'{v}', c['muted'], 12, 400, 'end'))
    # Start-Linie 100
    b.append(f'<line x1="{L}" y1="{Y(100):.1f}" x2="{W - R}" y2="{Y(100):.1f}" stroke="{c["axis"]}" stroke-width="1"/>')
    b.append(text(W - R - 6, Y(100) - 6, 'Startkapital 100', c['muted'], 11, 400, 'end'))
    # Monate
    for m in pd.date_range('2026-05-01', '2026-10-01', freq='MS', tz='UTC'):
        b.append(text(X(m), H - B + 20, m.strftime('%b').replace('May', 'Mai').replace('Oct', 'Okt'), c['muted'], 12, 400, 'middle'))
    # Testzeitraum-Markierung
    xs = X(SPLIT)
    b.append(f'<rect x="{xs:.1f}" y="{T}" width="{W - R - xs:.1f}" height="{H - T - B}" fill="{c["grid"]}" opacity="0.35"/>')
    b.append(text(xs + 8, T + 16, 'Testzeitraum (ab 09.06.)', c['text2'], 12, 600))
    for k, key in [('market', 's2'), ('limit', 's1')]:
        pts = curves[k]
        d = 'M' + ' L'.join(f'{X(t):.1f},{Y(v):.1f}' for t, v in pts)
        b.append(f'<path d="{d}" fill="none" stroke="{c[key]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>')
        tx, tv = pts[-1]
        b.append(f'<circle cx="{X(tx):.1f}" cy="{Y(tv):.1f}" r="4.5" fill="{c[key]}" stroke="{c["surface"]}" stroke-width="2"/>')
        b.append(text(X(tx) + 10, Y(tv) + 4, f'{tv:.0f} USDT', c['text'], 13, 600))
    return svg(W, H, ''.join(b), c, 'Kapitalkurve der Simulation mit 100 USDT seit Mai 2026')


# ---------------------------------------------------------------- 3) Backtest
def backtest_vals():
    data = {t: load(t) for t in TOKENS if os.path.exists(os.path.join(D, 'deposits', f'{t}.json'))}
    out = []
    for lab, f in [('Alle Signale', None), ('Absender: Wal', lambda e: e.cex == '-'),
                   ('Absender: andere Börse', lambda e: e.cex != '-')]:
        ev = run(data, 5e5, 60, filt=f)
        out.append((lab, ev[~ev.oos]['diff'].mean() * 100, ev[ev.oos]['diff'].mean() * 100, len(ev)))
    return out


def backtest(c, vals):
    W, H, L, R, T, B = 900, 360, 64, 28, 92, 52
    top = 0.35
    Y = lambda v: T + (1 - v / top) * (H - T - B)
    b = [text(28, 36, 'Backtest: Wie viel schwächer läuft der Coin nach der Einzahlung?', c['text'], 17, 600),
         text(28, 58, 'Short 60 min, Abweichung zur normalen Kursentwicklung, je Trade (Einzahlung ≥ 500k $)', c['text2'], 13)]
    lx = W - R - 300
    for i, (k, lab) in enumerate([('s1', 'Entwicklung (11/25–06/26)'), ('s2', 'Test (06–10/26)')]):
        x = lx + i * 165
        b.append(f'<rect x="{x}" y="72" width="12" height="12" rx="3" fill="{c[k]}"/>')
        b.append(text(x + 18, 82, lab, c['text2'], 12))
    for v in [0, 0.1, 0.2, 0.3]:
        y = Y(v)
        b.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="{c["axis" if v == 0 else "grid"]}" stroke-width="1"/>')
        b.append(text(L - 10, y + 4, f'+{v:.1f} %'.replace('.', ',') if v else '0', c['muted'], 12, 400, 'end'))
    # Referenzlinie Taker-Gebuehr
    yf = Y(0.12)
    b.append(f'<line x1="{L}" y1="{yf:.1f}" x2="{W - R}" y2="{yf:.1f}" stroke="{c["text2"]}" stroke-width="1"/>')
    b.append(text(W - R - 4, yf - 6, 'Market-Gebühren 0,12 %', c['text2'], 11.5, 600, 'end'))
    slot = (W - L - R) / len(vals)
    bw = 24
    for i, (lab, vis, voos, n) in enumerate(vals):
        cx = L + slot * (i + 0.5)
        for j, (v, key) in enumerate([(vis, 's1'), (voos, 's2')]):
            x = cx - bw - 6 + j * (bw + 12)
            y0, y1 = Y(0), Y(max(v, 0))
            h = y0 - y1
            r = min(4, h)
            b.append(f'<path d="M{x},{y0} V{y1 + r} Q{x},{y1} {x + r},{y1} H{x + bw - r} Q{x + bw},{y1} {x + bw},{y1 + r} V{y0} Z" fill="{c[key]}"/>')
            b.append(text(x + bw / 2, y1 - 6, f'+{v:.2f}'.replace('.', ','), c['text'], 12, 600, 'middle'))
        b.append(text(cx, H - B + 22, lab, c['text2'], 13, 400, 'middle'))
        b.append(text(cx, H - B + 38, f'{n} Trades', c['muted'], 11.5, 400, 'middle'))
    return svg(W, H, ''.join(b), c, 'Backtest-Ergebnis: Kurs nach Wal-Einzahlung im Entwicklungs- und Testzeitraum')


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    curves = equity_curves()
    vals = backtest_vals()
    print('Endstaende:', {k: round(v[-1][1], 1) for k, v in curves.items()}, '| Backtest:', vals)
    for mode, c in THEME.items():
        for name, s in [('flow', flow(c)), ('equity', equity(c, curves)), ('backtest', backtest(c, vals))]:
            with open(os.path.join(OUT, f'{name}-{mode}.svg'), 'w', encoding='utf-8') as f:
                f.write(s)
    print('geschrieben:', sorted(os.listdir(OUT)))
