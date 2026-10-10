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
   - `HEADLESS`: `true` para ejecución silenciosa en segundo plano (por defecto), o `false` para ver el navegador.
   - Datos personales del solicitante (`CANDIDATO_NOMBRE`, `CANDIDATO_DOCUMENTO`, etc.).

---

## 💻 Uso

### Ejecución manual
```bash
source venv/bin/activate
python monitor.py
```

### Ejecución programada (Cron)
Puedes utilizar el script [run_cron.sh](run_cron.sh) para ejecutarlo automáticamente cada X minutos. Evita corridas solapadas (lock) y solo avisa por Telegram cuando hay novedades (cupo, éxito o error), no en cada corrida sin cambios:
```bash
chmod +x run_cron.sh
./run_cron.sh
```

---

## 🔒 Seguridad
- El archivo `.env` está ignorado por Git para proteger claves y datos personales.
- Las capturas de pantalla, archivos de registro (`*.log`) y dumps HTML temporales no se suben al repositorio.
- Ningún dato personal está en el código: todo el formulario sale de `.env` y el bot no arranca si faltan variables.
- La API key de 2Captcha y el token de Telegram se ocultan (`***`) en logs y mensajes de error.
- `run_cron.sh` no ejecuta el `.env` como shell: solo lee las claves que necesita.
