import db
import signals
import simulate
import stake
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

MENU_BUTTONS = ["🎮 Jugar", "🔬 Simular", "📊 Stats", "🧹 Reset", "🆘 Ayuda", "💰 Stake", "🏦 Bank"]
BANK_AWAITING = set()


def _main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("🎮 Jugar"), KeyboardButton("🔬 Simular")],
            [KeyboardButton("💰 Stake"), KeyboardButton("🏦 Bank")],
            [KeyboardButton("📊 Stats"), KeyboardButton("🧹 Reset"), KeyboardButton("🆘 Ayuda")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Elige una opción del menú…",
    )

MINES = list(range(1, 25))


def _mines_keyboard():
    rows = []
    row = []
    for m in MINES:
        row.append(InlineKeyboardButton(str(m), callback_data=f"mines:{m}"))
        if len(row) == 6:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton("📊 Stats", callback_data="stats"),
            InlineKeyboardButton("❌ Cancelar", callback_data="cancel"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _bomb_keyboard(mask):
    rows = []
    idx = 0
    for r in range(signals.GRID_ROWS):
        row = []
        for c in range(signals.GRID_COLS):
            label = "💣" if mask & (1 << idx) else "🟦"
            row.append(InlineKeyboardButton(label, callback_data=f"bomb:{mask ^ (1 << idx)}"))
            idx += 1
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(f"✔️ Confirmar ({mask.bit_count()})", callback_data=f"bomb:done:{mask}"),
            InlineKeyboardButton("🧹 Limpiar", callback_data="bomb:clear"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def _result_keyboard():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🟢 Gané", callback_data="result:won"),
                InlineKeyboardButton("🔴 Perdí", callback_data="result:lost"),
            ],
            [
                InlineKeyboardButton("📊 Stats", callback_data="stats"),
                InlineKeyboardButton("🔁 Nueva señal", callback_data="jugar"),
            ],
        ]
    )


async def start(update, context):
    text = (
        "🎯 *Bot Mines 1win*\n\n"
        "Te genero señales de qué casillas abrir según el número de minas "
        "(riesgo) y el historial de tus partidas.\n\n"
        "**Cómo funciona:**\n"
        "1. Escribe /jugar y elige el nº de minas del tablero.\n"
        "2. Abre en 1win las casillas marcadas en la cuadrícula.\n"
        "3. Pulsa 🟢 Gané o 🔴 Perdí.\n"
        "4. El bot registra el resultado y ajusta el patrón para la próxima.\n\n"
        "Comandos: /jugar · /simular · /stats · /reset · /help"
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=_main_menu_keyboard())


async def help_command(update, context):
    text = (
        "🆘 *Ayuda*\n\n"
        "/jugar - Generar una señal de Mines\n"
        "/stats - Ver tus estadísticas y progreso del entrenamiento\n"
        "/reset - Borrar todo tu historial\n\n"
        "💡 El bot sugiere casillas según el patrón que aprende de tus "
        "resultados. Registra el resultado **solo** si abriste las casillas "
        "indicadas, así el entrenamiento es fiable.\n\n"
        "⚠️ Las minas se colocan de forma aleatoria: ninguna señal garantiza "
        "ganar. Juega con responsabilidad."
    )
    await update.message.reply_text(text, parse_mode="Markdown",
                                    reply_markup=_main_menu_keyboard())


async def jugar_command(update, context):
    text = "🎮 *Nueva señal de Mines*\n\nElige el número de minas del tablero (1-24):"
    await update.message.reply_text(text, reply_markup=_mines_keyboard(), parse_mode="Markdown")


async def stats_command(update, context):
    await _show_stats(update.message.chat_id, None, update)


async def simular_command(update, context):
    user_id = update.effective_user.id
    mines = 3
    if context.args:
        try:
            mines = max(1, min(24, int(context.args[0])))
        except ValueError:
            pass
    else:
        risk = db.get_risk_stats(user_id)
        if risk:
            mines = max(risk, key=lambda r: r["games"])["mines"]

    res = simulate.monte_carlo(mines, signals.suggested_count(mines))
    mine_counts = db.get_mine_counts(user_id)
    safe_counts = db.get_safe_counts(user_id)
    total_mines = sum(mine_counts.values())
    total_safe = sum(safe_counts.values())

    lines = [
        f"🔬 *Simulación Monte Carlo*",
        f"Trampas: {mines} · Casillas: {res['tiles']} · Rondas: **{res['games']:,}**",
        "",
        f"Multiplicador justo: x{res['mult']:.2f}",
        f"Winrate: **{res['win_rate'] * 100:.2f}%**",
        f"EV por jugada: **{res['ev']}**",
    ]
    if res["ev"] >= 0.9995 and res["ev"] <= 1.0005:
        lines.append("→ Juego matemáticamente justo (EV ≈ 1.0): **no hay ventaja explotable**")
    elif res["ev"] < 0.9995:
        lines.append(f"→ EV < 1: la casa cobra comisión (≈{(1 - res['ev']) * 100:.2f}%)")
    else:
        lines.append("→ EV > 1: pagos por encima del valor justo (revisa si es real)")

    lines.append("")
    if total_mines >= 50:
        chi = simulate.chi_square_uniformity(mine_counts)
        if chi:
            lines.append("🧪 *Datos acumulados:*")
            lines.append(f"Minas reportadas: {total_mines} · Celdas seguras: {total_safe}")
            if chi["biased"]:
                lines.append(f"χ²={chi['stat']} > 36.4 → **¡Sesgo detectado!**")
                rec = simulate.best_cells_by_data(mines, mine_counts, safe_counts)
                lines.append("Nueva señal en modo sesgo:")
                lines.append(simulate.render_recommendation(rec))
            else:
                lines.append(f"χ²={chi['stat']} ≤ 36.4 → distribución uniforme, **sin casillas más seguras**.")
    else:
        lines.append(
            f"📥 Datos: {total_mines} minas reportadas · {total_safe} celdas seguras. "
            f"Faltan {max(0, 50 - total_mines)} minas para poder hacer el test de uniformidad."
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def reset_command(update, context):
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🧹 Sí, borrar todo", callback_data="reset_confirm"),
                InlineKeyboardButton("Cancelar", callback_data="reset_cancel"),
            ]
        ]
    )
    await update.message.reply_text(
        "⚠️ ¿Seguro que quieres borrar todo tu historial y el entrenamiento?",
        reply_markup=kb,
    )


async def menu_button(update, context):
    handlers_map = {
        "🎮 Jugar": jugar_command,
        "🔬 Simular": simular_command,
        "📊 Stats": stats_command,
        "🧹 Reset": reset_command,
        "🆘 Ayuda": help_command,
        "💰 Stake": stake_command,
        "🏦 Bank": bank_command,
    }
    handler = handlers_map.get(update.message.text)
    if handler:
        await handler(update, context)


async def stake_command(update, context):
    user_id = update.effective_user.id
    bank = db.get_bank(user_id)
    results = db.get_results(user_id)
    await update.message.reply_text(
        stake.status_line(results, bank),
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )


async def bank_command(update, context):
    user_id = update.effective_user.id
    if context.args:
        digits = "".join(ch for ch in context.args[0] if ch.isdigit())
        if digits and int(digits) >= stake.MIN_BET:
            amt = int(digits)
            db.set_bank(user_id, amt)
            await update.message.reply_text(
                f"🏦 Bank actualizado: **${amt:,} COP**.",
                parse_mode="Markdown",
                reply_markup=_main_menu_keyboard(),
            )
            return
    BANK_AWAITING.add(user_id)
    await update.message.reply_text(
        f"🏦 ¿Cuánto tienes de bank en pesos? (mín ${stake.MIN_BET:,} COP, ej: 100000)",
        reply_markup=_main_menu_keyboard(),
    )


async def text_handler(update, context):
    user_id = update.effective_user.id
    text = update.message.text
    if user_id in BANK_AWAITING:
        BANK_AWAITING.discard(user_id)
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            await update.message.reply_text("No entendí el monto. Escribe un número, ej: 100000")
            return
        amt = int(digits)
        if amt < stake.MIN_BET:
            await update.message.reply_text(
                f"El bank debe ser al menos ${stake.MIN_BET:,} COP."
            )
            return
        db.set_bank(user_id, amt)
        await update.message.reply_text(
            f"🏦 Bank actualizado: **${amt:,} COP**.",
            parse_mode="Markdown",
            reply_markup=_main_menu_keyboard(),
        )
        return
    await menu_button(update, context)


async def on_callback(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data.startswith("mines:"):
        mines = int(data.split(":")[1])
        await _send_signal(q.from_user.id, q.message.chat_id, mines, q=q)
    elif data == "result:won":
        await _report_result(q, True)
    elif data == "result:lost":
        await _report_result(q, False)
    elif data == "bomb_skip":
        await q.edit_message_text(
            "✅ Guardado. Solo las celdas seguras quedan registradas."
        )
    elif data == "bomb_start":
        await q.edit_message_text(
            "💣 Marca **todas** las bombas que salieron:",
            reply_markup=_bomb_keyboard(0),
        )
    elif data.startswith("bomb:done:"):
        mask = int(data[len("bomb:done:"):] or 0)
        indices = [i for i in range(25) if mask & (1 << i)]
        positions = [(i // 5, i % 5) for i in indices]
        db.log_many_mines(q.from_user.id, positions)
        total = sum(db.get_mine_counts(q.from_user.id).values())
        await q.edit_message_text(
            f"✅ **{len(indices)} bombas** registradas ({total} en total).\n"
            f"Sigue reportando para que /simular detecte casillas más seguras."
        )
    elif data == "bomb:clear":
        await q.edit_message_text(
            "💣 Marca **todas** las bombas que salieron:",
            reply_markup=_bomb_keyboard(0),
        )
    elif data.startswith("bomb:"):
        mask = int(data[len("bomb:"):] or 0)
        await q.edit_message_reply_markup(reply_markup=_bomb_keyboard(mask))
    elif data == "jugar":
        await q.edit_message_text(
            "🎮 *Nueva señal de Mines*\n\nElige el número de minas (1-24):",
            reply_markup=_mines_keyboard(),
            parse_mode="Markdown",
        )
    elif data == "stats":
        await _show_stats(q.message.chat_id, q, None)
    elif data == "reset_confirm":
        db.reset_user(q.from_user.id)
        await q.edit_message_text("🧹 Historial y entrenamiento borrados. Empieza de cero con /jugar.")
    elif data == "reset_cancel":
        await q.edit_message_text("✅ Cancelado.")
    elif data == "cancel":
        await q.edit_message_text("❌ Operación cancelada.")


async def _send_signal(user_id, chat_id, mines, q=None):
    cells = signals.generate_signal(user_id, mines)
    bank = db.get_bank(user_id)
    results = db.get_results(user_id)
    bet, _ = stake.recommend_bet(results, bank)
    db.create_game(user_id, mines, cells, bet)
    grid = signals.render_grid(cells)
    text = f"🎯 Señal · {mines} trampas\n\n{grid}\n\n💰 Apuesta: ${bet:,}"
    if q:
        await q.edit_message_text(text, reply_markup=_result_keyboard(), parse_mode="Markdown")
    else:
        await context.bot.send_message(chat_id, text, reply_markup=_result_keyboard(), parse_mode="Markdown")


async def _report_result(q, won):
    user_id = q.from_user.id
    game = db.get_pending_game(user_id)
    if not game:
        await q.edit_message_text(
            "⚠️ No hay una partida pendiente. Usa /jugar para generar una señal."
        )
        return
    db.resolve_game(game["id"], won)

    stake_amount = game["stake"]
    mult = signals.signal_multiplier(game["mines"])
    if won:
        db.update_bank(user_id, round(stake_amount * (mult - 1)))
    else:
        db.update_bank(user_id, -stake_amount)

    bank = db.get_bank(user_id)
    bank_val = bank if bank is not None else 0
    next_bet, state = stake.recommend_bet(db.get_results(user_id), bank)
    stats = db.get_user_stats(user_id)
    rate = stats["wins"] / stats["games"] * 100 if stats["games"] else 0
    profit = round(stake_amount * (mult - 1)) if won else -stake_amount
    bank_line = f"💰 Bank: ${bank_val:,}" if bank is not None else "💰 Bank: no registrado (usa /bank)"
    text = (
        ("🟢 ¡Ganaste! " if won else "🔴 Perdiste... ")
        + ("+" if profit >= 0 else "-")
        + f"${abs(profit):,}\n\n"
        + bank_line
        + f"\n📈 {state} · Próxima apuesta: ${next_bet:,}\n"
        f"📊 {stats['games']}P · {stats['wins']}G · {stats['losses']}P · {rate:.1f}%"
    )
    kb = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔁 Nueva señal", callback_data="jugar")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        ]
    )
    await q.edit_message_text(text, reply_markup=kb)

    ref = signals.render_grid(game["suggested"])
    if not won:
        await q.message.reply_text(f"Tablero de esa señal:\n\n{ref}")
        await q.message.reply_text(
            "💣 Marca **todas** las bombas que salieron:",
            reply_markup=_bomb_keyboard(0),
        )
    else:
        db.log_safe_cells(user_id, game["suggested"])
        kb_mark = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("💣 Sí, marcar bombas", callback_data="bomb_start"),
                    InlineKeyboardButton("➖ Omitir", callback_data="bomb_skip"),
                ]
            ]
        )
        await q.message.reply_text(
            f"Tablero de esa señal:\n\n{ref}\n\n"
            f"✅ Las celdas abiertas quedan registradas como **seguras** "
            f"para el análisis.\n"
            f"¿Viste dónde estaban las bombas? (si 1win te mostró el tablero final)",
            reply_markup=kb_mark,
        )


async def _show_stats(chat_id, q=None, update=None):
    if q:
        user_id = q.from_user.id
    else:
        user_id = update.effective_user.id

    stats = db.get_user_stats(user_id)
    rate = stats["wins"] / stats["games"] * 100 if stats["games"] else 0
    lines = [
        "📊 *Tus estadísticas*",
        "",
        f"Total: {stats['games']} · 🏆 {stats['wins']} G · ❌ {stats['losses']} P · "
        f"Winrate **{rate:.1f}%**",
    ]

    risk = db.get_risk_stats(user_id)
    if risk:
        lines.append("")
        lines.append("🎚 *Por riesgo (minas):*")
        for r in risk:
            r_rate = r["wins"] / r["games"] * 100 if r["games"] else 0
            lines.append(
                f"• {r['mines']} minas: {r['games']} partidas, {r['wins']} G ({r_rate:.0f}%)"
            )

    cells = db.get_cell_stats(user_id)
    ranked = sorted(
        [c for c in cells if c["opened"] >= 2],
        key=lambda c: c["wins"] / c["opened"],
        reverse=True,
    )
    if ranked:
        lines.append("")
        lines.append("🌟 *Celdas con mejor historial:*")
        for c in ranked[:5]:
            label = signals.COL_LABELS[c["col"]] + str(c["row"] + 1)
            lines.append(f"• {label}: {c['wins']}G/{c['losses']}P ({c['opened']} abiertas)")

    if stats["games"] == 0:
        lines.append("")
        lines.append("Aún no has jugado. Usa /jugar para generar tu primera señal.")

    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔁 Nueva señal", callback_data="jugar")]])
    text = "\n".join(lines)
    if q:
        await q.edit_message_text(text, reply_markup=kb, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="Markdown")
