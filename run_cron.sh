#!/bin/bash
cd /Users/$(whoami)/ekonsulat-bot

# Cargar variables de entorno desde .env
if [ -f .env ]; then
    set -a
    source .env
    set +a
fi

# Archivo exclusivo para la salida de esta corrida
LOG_ACTUAL="/tmp/ekonsulat_run_actual.txt"
rm -f "$LOG_ACTUAL"

echo "===============================================" >> ejecucion.log
date >> ejecucion.log

# Activar entorno y ejecutar guardando la salida de esta única corrida
source venv/bin/activate
python monitor.py > "$LOG_ACTUAL" 2>&1

# También lo agregamos al historial general ejecucion.log
cat "$LOG_ACTUAL" >> ejecucion.log

# Leemos el contenido de la corrida actual
SALIDA_CORRIDA=$(cat "$LOG_ACTUAL")

# Determinar el estado y título
if echo "$SALIDA_CORRIDA" | grep -q "EXITO TOTAL"; then
    TITULO="🚨 *¡TURNO ENVIADO CON ÉXITO!* 🇵🇱"
elif echo "$SALIDA_CORRIDA" | grep -q "ALERTA"; then
    TITULO="⚠️ *¡HAY LUGAR EN LA LISTA DE ESPERA!* 🇵🇱"
elif echo "$SALIDA_CORRIDA" | grep -q "Cola llena"; then
    TITULO="ℹ️ *e-Konsulat:* Cola llena (sin novedades)"
else
    TITULO="⚙️ *e-Konsulat:* Reporte de ejecución"
fi

HORA_ACTUAL=$(date "+%H:%M:%S")

# Mensaje formateado para Telegram
MENSAJE="$TITULO
🕒 Hora: $HORA_ACTUAL

\`\`\`
$SALIDA_CORRIDA
\`\`\`"

# Enviar mensaje a Telegram
curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
    -d chat_id="${TELEGRAM_CHAT_ID}" \
    -d parse_mode="Markdown" \
    --data-urlencode text="$MENSAJE" > /dev/null 2>&1

# Si hubo inscripción exitosa, enviar la imagen de confirmación
if echo "$SALIDA_CORRIDA" | grep -q "confirmacion_final.png"; then
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendPhoto" \
        -F chat_id="${TELEGRAM_CHAT_ID}" \
        -F photo="@/Users/$(whoami)/ekonsulat-bot/confirmacion_final.png" \
        -F caption="Comprobante de inscripción de Felipe" > /dev/null 2>&1
fi
