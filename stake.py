import db

MIN_BET = 400
MAX_BANK_FRACTION = 0.10


def compute_streak(results):
    if not results:
        return {"kind": "neutral", "n": 0}
    last = results[-1]
    n = 0
    for r in reversed(results):
        if r == last:
            n += 1
        else:
            break
    return {"kind": "win" if last == "won" else "loss", "n": n}


def recent_rate(results, window=10):
    if not results:
        return None
    last = results[-window:]
    return sum(1 for r in last if r == "won") / len(last)


def classify(results):
    kind, n = compute_streak(results).values()
    rate = recent_rate(results) or 0.5
    if kind == "loss" and n >= 2:
        return "racha_perdedora"
    if kind == "win" and n >= 2:
        return "racha_ganadora"
    if rate >= 0.57:
        return "racha_ganadora"
    if rate <= 0.43:
        return "racha_perdedora"
    return "intermitente"


def recommend_bet(results, bank):
    state = classify(results)
    kind, n = compute_streak(results).values()
    if state == "racha_ganadora":
        mult = {1: 1.5, 2: 2.0, 3: 2.5}.get(n, 3.0)
        bet = MIN_BET * mult
    else:
        bet = MIN_BET
    if bank and bank >= MIN_BET:
        bet = min(bet, bank * MAX_BANK_FRACTION)
    bet = round(max(bet, MIN_BET))
    if bank and bet > bank:
        bet = MIN_BET if bank >= MIN_BET else 0
    return bet, state


def status_line(results, bank):
    state = classify(results)
    kind, n = compute_streak(results).values()
    rate = recent_rate(results)
    bet, _ = recommend_bet(results, bank)

    lines = [
        "💰 *Stake*",
        f"Bank: **${bank:,}**" if bank else "Bank: **no registrado** (usa /bank)",
        f"Estado: **{state}**",
    ]
    if kind != "neutral":
        lines.append(f"Racha: **{n}** {'ganadas' if kind == 'win' else 'perdidas'} seguidas")
    lines.append(f"Winrate últimos 10: {rate * 100:.0f}%" if rate is not None else "Winrate últimos 10: —")
    lines.append("")
    if bank and bank < MIN_BET:
        lines.append(f"⚠️ Bank insuficiente (mínimo ${MIN_BET:,} COP partida).")
    lines.append(f"Apuesta recomendada: **${bet:,} COP**")
    return "\n".join(lines)