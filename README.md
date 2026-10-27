# e-Konsulat Bot

Script automatizado con Playwright para monitorear la disponibilidad de turnos en el sistema **e-Konsulat** (Sección Consular de la Embajada de Polonia en Buenos Aires), resolver captchas automáticamente mediante **2Captcha** y notificar eventos a través de **Telegram**.

---

## 🚀 Requisitos

- Python 3.10 o superior
- macOS / Linux
- Cuenta en 2Captcha (con saldo y API Key)
- Bot de Telegram configurado

---

## 🛠️ Instalación

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/tu-usuario/ekonsulat-bot.git
   cd ekonsulat-bot
   ```

2. **Crear y activar un entorno virtual:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Configurar variables de entorno:**
   Copia el archivo de ejemplo y completa tus datos reales:
   ```bash
   cp .env.example .env
   ```
   Edita `.env` con tus credenciales y datos:
   - `TWOCAPTCHA_API_KEY`: Tu clave de API de 2Captcha.
   - `TELEGRAM_BOT_TOKEN`: Token otorgado por @BotFather.
   - `TELEGRAM_CHAT_ID`: Tu Chat ID de Telegram.
   - `HEADLESS`: `true` para ejecutar Chromium sin ventana visible; `false` para abrir Chrome visible durante toda la ejecución.
   - Datos personales del solicitante (`CANDIDATO_NOMBRE`, `CANDIDATO_DOCUMENTO`, etc.).

---

## 💻 Uso

### Ejecución manual
```bash
source venv/bin/activate
python monitor.py
```

### Ejecución programada (Cron)
`run_cron.sh` ejecuta una sola corrida; la frecuencia se configura aparte en cron o en el scheduler del sistema. Evita corridas solapadas (lock) y avisa por Telegram cuando hay novedades. La respuesta se considera enviada solo si Telegram devuelve HTTP exitoso y `"ok": true`. El bot no informa un registro exitoso si no detecta una confirmación explícita de e-Konsulat:
```bash
chmod +x run_cron.sh
./run_cron.sh
```
Si aparece un lugar en la lista de espera, el bot puede enviar el formulario hasta cinco veces cuando no detecta una confirmación explícita; esto puede crear duplicados si el servidor aceptó un envío sin mostrar un mensaje reconocido. Detiene los reenvíos ante errores de validación y no envía el formulario si no pudo completar/verificar todos los campos obligatorios. Los fallos recuperables de 2Captcha obtienen un CAPTCHA nuevo y se reintentan, hasta ocho intentos.

Con `HEADLESS=true`, Chromium permanece oculto. Si el formulario requiere revisión humana, Telegram indica qué campos fallaron, pero no se puede intervenir visualmente en esa corrida; ejecuta manualmente con `HEADLESS=false` para revisar la página. Si el registro quedó sin confirmar, verifica el estado en e-Konsulat y el correo antes de lanzar otra inscripción.

Cuando aparece un cupo, el bot espera hasta 90 segundos a que el formulario esté en pantalla (aceptando los diálogos "Tak" que aparezcan), en lugar de esperar un tiempo fijo. La fecha de nacimiento se prueba en `YYYY-MM-DD`, `DD.MM.YYYY` y `DD/MM/YYYY` hasta que el sitio la acepte. Si e-Konsulat rechaza el formulario, el log y Telegram indican qué campo marcó el sitio y con qué mensaje. Al apretar "Dalej", e-Konsulat muestra una pantalla de revisión (Anuluj / Popraw / Zapisz): el registro se hace recién con "Zapisz", que el bot aprieta una sola vez. Si el formulario desaparece después de enviarlo sin un mensaje de confirmación reconocido, el bot no lo reenvía, para no duplicar la inscripción.

Ante cualquier falla en el formulario, el HTML de la página se guarda en `debug/` (ignorado por git, permisos 600) para poder diagnosticarla.

El cron de esta Mac está configurado en `*/10 * * * *` (cada 10 minutos). El lock evita ejecutar dos instancias a la vez; `run_cron.sh` no modifica por sí mismo la frecuencia.

### Pruebas
```bash
python -m unittest -v test_monitor
```

---

## 🔒 Seguridad
- El archivo `.env` está ignorado por Git para proteger claves y datos personales.
- Las capturas de pantalla, archivos de registro (`*.log`) y dumps HTML temporales no se suben al repositorio.
- Ningún dato personal está en el código: todo el formulario sale de `.env` y el bot no arranca si faltan variables.
- La API key de 2Captcha y el token de Telegram se ocultan (`***`) en logs y mensajes de error.
- El texto reconocido del CAPTCHA no se registra.
- `run_cron.sh` no ejecuta el `.env` como shell: solo lee las claves que necesita.
