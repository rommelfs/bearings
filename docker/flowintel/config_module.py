"""Local synthetic pilot: no mail, Matrix, webhooks or AI/analysis endpoints."""

from pathlib import Path

exec(
    compile(
        Path(__file__).with_name("config_module.py.default").read_text(), "flowintel-default-modules", "exec"
    )
)
SMTP_SERVER = SENDER_EMAIL = SENDER_PASSOWRD = ""
MATRIX_SERVER = MATRIX_USER = MATRIX_PASSWORD = MATRIX_ROOM_ID = ""
WEBHOOK_ENABLED = False
WEBHOOK_URL = WEBHOOK_SECRET = ""
CASE_CREATE_ALERT_ENABLED = False
OLLAMA_URL = OLLAMA_KEY = OLLAMA_MODEL = ""
