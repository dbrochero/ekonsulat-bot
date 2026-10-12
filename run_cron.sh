#!/bin/bash
# Ejecuta monitor.py una vez y avisa por Telegram SOLO si hay novedades.
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
trap 'rm -rf "$LOCK_DIR" "$LOG_ACTUAL" "$LOG_TMP"' EXIT

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
# Las excepciones y el aviso de intervención humana ya los notifica monitor.py.
if echo "$SALIDA_CORRIDA" | grep -q "CONFIRMACION REQUERIDA"; then
    TITULO="⚠️ *e-Konsulat: registro no confirmado*"
elif echo "$SALIDA_CORRIDA" | grep -q "ALERTA"; then
    TITULO="⚠️ *¡HAY LUGAR EN LA LISTA DE ESPERA!* 🇵🇱"
elif echo "$SALIDA_CORRIDA" | grep -q "^\[ERROR\]"; then
    TITULO="❌ *e-Konsulat:* error de ejecución"
else
    exit 0   # "Cola llena" u otra corrida sin novedades: no se envía nada
fi

[ -z "$TELEGRAM_BOT_TOKEN" ] || [ -z "$TELEGRAM_CHAT_ID" ] && exit 0

# Telegram admite 4096 caracteres: se manda solo el final de la salida
SALIDA_CORTA=$(printf '%s' "$SALIDA_CORRIDA" | tail -c 3000)

MENSAJE="$TITULO
🕒 Hora: $(date '+%H:%M:%S')

\`\`\`
$SALIDA_CORTA
\`\`\`"

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    -d parse_mode="Markdown" \
    --data-urlencode text="$MENSAJE" > /dev/null 2>&1
