import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import config
import db
from handlers import (
    backup_command,
    bank_command,
    help_command,
    jugar_command,
    meta_command,
    on_callback,
    reset_command,
    simular_command,
    stake_command,
    start,
    stats_command,
    text_handler,
)
from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _start_health_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Servidor de salud en el puerto %s", port)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Excepción no controlada:", exc_info=context.error)

MENU_COMMANDS = [
    BotCommand("start", "Inicio"),
    BotCommand("jugar", "Generar señal de Mines"),
    BotCommand("simular", "Analizar 100,000 rondas"),
    BotCommand("stake", "Ver apuesta recomendada"),
    BotCommand("bank", "Registrar tu bank (ej. /bank 100000)"),
    BotCommand("meta", "Modo meta: fija bank y objetivo"),
    BotCommand("stats", "Ver tus estadísticas"),
    BotCommand("backup", "Descargar copia de la base de datos"),
    BotCommand("reset", "Borrar historial"),
    BotCommand("help", "Ayuda"),
]


async def post_init(app):
    await app.bot.set_my_commands(MENU_COMMANDS)


def main():
    db.init_db()
    _start_health_server()
    app = (
        Application.builder()
        .token(config.TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("jugar", jugar_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("simular", simular_command))
    app.add_handler(CommandHandler("stake", stake_command))
    app.add_handler(CommandHandler("bank", bank_command))
    app.add_handler(CommandHandler("meta", meta_command))
    app.add_handler(CommandHandler("backup", backup_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_error_handler(error_handler)

    print("Bot iniciado. Habla con tu bot en Telegram.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
