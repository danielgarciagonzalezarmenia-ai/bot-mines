import os

TOKEN = os.environ.get("BOT_TOKEN", "").strip()

_token_file = os.path.join(os.path.dirname(__file__), "token.txt")
if not TOKEN and os.path.exists(_token_file):
    with open(_token_file, encoding="utf-8") as f:
        TOKEN = f.read().strip()

if not TOKEN:
    raise SystemExit(
        "Falta el token del bot. Crea un bot con @BotFather, copia su token "
        "y ponlo en la variable BOT_TOKEN o en un archivo token.txt."
    )
