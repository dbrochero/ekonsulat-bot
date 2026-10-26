#!/bin/bash
# Ejecuta monitor.py una vez; el monitor notifica resultados y este wrapper
# solo avisa cuando el proceso no puede iniciarse correctamente.
# - No ejecuta .env como shell (se leen únicamente las dos claves de Telegram).
# - Lock para evitar corridas solapadas.
# - Oculta secretos antes de loguear o enviar nada.

cd "$(dirname "$0")" || exit 1

# --- Lock: evita instancias simultáneas (macOS no trae flock) ---
LOCK_DIR="${TMPDIR:-/tmp}/ekonsulat_bot.lock"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    PID_PREVIO=$(cat "$LOCK_DIR/pid" 2>/dev/null)
    if [ -n "$PID_PREVIO" ] && kill -0 "$PID_PREVIO" 2>/dev/null; then
        echo "$(date) Ya hay una corrida activa (pid $PID_PREVIO), se omite." >> ejecucion.log
        exit 0
    fi
    # Lock huérfano de una corrida que murió: se recupera.
    rm -rf "$LOCK_DIR"
    mkdir "$LOCK_DIR" || exit 1
fi
echo $$ > "$LOCK_DIR/pid"

LOG_ACTUAL=$(mktemp "${TMPDIR:-/tmp}/ekonsulat_run.XXXXXX")
LOG_ARCHIVO="ejecucion.log"
LOG_TMP=$(mktemp "${TMPDIR:-/tmp}/ekonsulat_log.XXXXXX")
TELEGRAM_RESPUESTA=$(mktemp "${TMPDIR:-/tmp}/ekonsulat_telegram.XXXXXX")
trap 'rm -rf "$LOCK_DIR" "$LOG_ACTUAL" "$LOG_TMP" "$TELEGRAM_RESPUESTA"' EXIT

# --- Leer solo lo necesario de .env, sin ejecutarlo ---
leer_env() {
    grep -E "^$1=" .env 2>/dev/null | head -n1 | cut -d= -f2- | sed -E 's/^"(.*)"$/\1/; s/^'"'"'(.*)'"'"'$/\1/'
}
TELEGRAM_BOT_TOKEN=$(leer_env TELEGRAM_BOT_TOKEN)
TELEGRAM_CHAT_ID=$(leer_env TELEGRAM_CHAT_ID)
TWOCAPTCHA_API_KEY=$(leer_env TWOCAPTCHA_API_KEY)

# Reemplaza secretos por *** en stdin
ocultar() {
    local texto
    texto=$(cat)
    for secreto in "$TELEGRAM_BOT_TOKEN" "$TWOCAPTCHA_API_KEY"; do
        [ -n "$secreto" ] && texto="${texto//"$secreto"/***}"
    done
    printf '%s\n' "$texto"
}

# --- Ejecutar (python-dotenv carga el .env por su cuenta) ---
source venv/bin/activate
python monitor.py > "$LOG_ACTUAL" 2>&1
PYTHON_STATUS=$?

{
    echo "==============================================="
    date
    cat "$LOG_ACTUAL"
    echo "==============================================="
} | ocultar > "$LOG_TMP"

if [ -f "$LOG_ARCHIVO" ]; then
    cat "$LOG_ARCHIVO" >> "$LOG_TMP"
fi

mv "$LOG_TMP" "$LOG_ARCHIVO"

SALIDA_CORRIDA=$(ocultar < "$LOG_ACTUAL")

# --- Decidir si vale la pena avisar ---
# Los resultados del registro, las excepciones capturadas y la intervención
# humana ya los notifica monitor.py; evitar enviar un segundo aviso.
if echo "$SALIDA_CORRIDA" | grep -q "ALERTA"; then
    exit 0
elif echo "$SALIDA_CORRIDA" | grep -q "^\[ERROR\]"; then
    TITULO="❌ *e-Konsulat:* error de ejecución"
elif [ "$PYTHON_STATUS" -ne 0 ]; then
    TITULO="❌ *e-Konsulat:* error al iniciar la automatización"
else
    exit 0   # "Cola llena" u otra corrida sin novedades: no se envía nada
fi

if [ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "[ERROR] No se pudo enviar la notificación: faltan credenciales de Telegram." >> "$LOG_ARCHIVO"
    exit 1
fi

# Telegram admite 4096 caracteres: se manda solo el final de la salida
SALIDA_CORTA=$(printf '%s' "$SALIDA_CORRIDA" | tail -c 3000)

MENSAJE="$TITULO
🕒 Hora: $(date '+%H:%M:%S')

\`\`\`
$SALIDA_CORTA
\`\`\`"

HTTP_STATUS=$(curl -sS --connect-timeout 5 --max-time 15 \
    -o "$TELEGRAM_RESPUESTA" -w '%{http_code}' \
    -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    -d parse_mode="Markdown" \
    --data-urlencode text="$MENSAJE" 2>/dev/null)
CURL_STATUS=$?

if [ "$CURL_STATUS" -ne 0 ] || ! [[ "$HTTP_STATUS" =~ ^2[0-9][0-9]$ ]] \
    || ! grep -Eq '"ok"[[:space:]]*:[[:space:]]*true' "$TELEGRAM_RESPUESTA"; then
    echo "[ERROR] Telegram no confirmó la entrega del aviso (HTTP ${HTTP_STATUS:-sin respuesta}, curl $CURL_STATUS)." >> "$LOG_ARCHIVO"
    exit 1
fi
