import os
import time
import base64
import subprocess
from typing import Dict, List

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright
from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
for env_name, env_value in dotenv_values(os.path.join(BASE_DIR, ".env")).items():
    if env_value is not None and not os.environ.get(env_name):
        os.environ[env_name] = env_value

URL = "https://secure.e-konsulat.gov.pl/placowki/164/sprawy-paszportowe/wizyty/formularz"
API_KEY_2CAPTCHA = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
HEADLESS = os.getenv("HEADLESS", "true").strip().lower() in ("true", "1", "yes", "t")

REQUIRED_ENV_VARS: List[str] = [
    "TWOCAPTCHA_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]

MANDATORY_APPLICANT_FIELDS: List[str] = [
    "nombre",
    "apellido",
    "documento",
    "direccion_completa",
    "telefono",
    "email",
    "fecha_nacimiento",
    "apellido_madre",
]

SELECTORS = {
    "captcha_img": "img[alt='Weryfikacja obrazkowa']",
    "captcha_input": "#mat-input-0, input[formcontrolname*='captcha' i], input",
    "next_button": "button:has-text('Dalej'), button:has-text('dalej')",
    "refresh_button": "button:has-text('Odśwież')",
    "service_select": "mat-select",
    "mat_option": ".cdk-overlay-container mat-option",
    "accept_waitlist": "button:has-text('Tak')",
    "nombre": "input[aria-label*='Imię' i], #mat-input-1",
    "apellido": "input[aria-label*='Nazwisko' i], #mat-input-2",
    "documento": "input[aria-label*='Numer paszportu' i], #mat-input-3",
    "direccion": "input[aria-label*='Ulica' i], #mat-input-4",
    "prefijo": "input[aria-label*='Prefiks' i], #mat-input-5",
    "telefono": "input[aria-label*='Telefon' i], #mat-input-6, input[autocomplete='tel']",
    "email": "input[aria-label*='Email' i], #mat-input-7, input[autocomplete='email']",
    "descripcion": "textarea[aria-label*='Opis sprawy' i], textarea, #mat-input-8",
    "mat_checkbox_registrante": "mat-checkbox:has-text('Czy sprawa dotyczy osoby rejestrującej')",
    "mat_checkbox_pasaporte": "mat-checkbox:has-text('1-SZY PASZPORT')",
    "apellido_madre": "input[aria-label*='Nazwisko rodowe matki' i], app-text-control:has-text('Nazwisko rodowe matki') input",
    "fecha_nacimiento": "input[aria-label*='Data urodzenia' i], app-date-control input, input.mat-datepicker-input",
    "checkbox_rodo": "mat-checkbox:has-text('Wyrażam zgodę'), mat-checkbox:has-text('RODO')",
}

session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount("https://", HTTPAdapter(max_retries=retries))

DATOS_SOLICITANTE: Dict[str, str] = {
    "nombre": os.getenv("CANDIDATO_NOMBRE", "").strip(),
    "apellido": os.getenv("CANDIDATO_APELLIDO", "").strip(),
    "documento": os.getenv("CANDIDATO_DOCUMENTO", "").strip(),
    "direccion_completa": os.getenv("CANDIDATO_DIRECCION", "").strip(),
    "telefono": os.getenv("CANDIDATO_TELEFONO", "").strip(),
    "email": os.getenv("CANDIDATO_EMAIL", "").strip(),
    "fecha_nacimiento": os.getenv("CANDIDATO_FECHA_NACIMIENTO", "").strip(),
    "apellido_madre": os.getenv("CANDIDATO_APELLIDO_MADRE", "").strip(),
    "descripcion": os.getenv("CANDIDATO_DESCRIPCION", "Wniosek o pierwszy paszport 10-letni (PESEL nienadany)").strip(),
}

CAMPOS_OBLIGATORIOS = (
    "nombre",
    "apellido",
    "documento",
    "direccion_completa",
    "telefono",
    "email",
    "fecha_nacimiento",
    "apellido_madre",
)


def sin_secretos(texto) -> str:
    """Oculta la API key de 2Captcha y el token de Telegram en cualquier texto."""
    texto = str(texto)
    for secreto in (API_KEY_2CAPTCHA, TELEGRAM_BOT_TOKEN):
        if secreto:
            texto = texto.replace(secreto, "***")
    return texto


def sanitize_for_logs(text: object) -> str:
    return sin_secretos(text)


def faltan_variables() -> List[str]:
    faltan: List[str] = []
    valores_entorno = {
        "TWOCAPTCHA_API_KEY": API_KEY_2CAPTCHA,
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
    }
    for key in REQUIRED_ENV_VARS:
        if not valores_entorno.get(key, ""):
            faltan.append(key)
    for key in CAMPOS_OBLIGATORIOS:
        if not DATOS_SOLICITANTE.get(key, ""):
            faltan.append(f"CANDIDATO_{key.upper()}")
    return faltan


def enviar_telegram(mensaje: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url_msg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        session.post(
            url_msg,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"},
            timeout=10,
        )
    except Exception as exc:
        print(f"[WARN] Error enviando Telegram: {sanitize_for_logs(exc)}")


def alarma_local():
    """Hace sonar una alarma en macOS para avisarte si estás cerca de la Mac."""
    try:
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["say", "Atención. Cupo de pasaporte disponible. Revisar pantalla."], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def resolver_captcha_2captcha(b64_img: str):
    if not API_KEY_2CAPTCHA:
        raise ValueError("Falta configurar TWOCAPTCHA_API_KEY.")

    if "," in b64_img:
        b64_img = b64_img.split(",", 1)[1]

    res = session.post(
        "https://2captcha.com/in.php",
        data={
            "key": API_KEY_2CAPTCHA,
            "method": "base64",
            "body": b64_img,
            "regsense": 1,
            "min_len": 4,
            "max_len": 6,
            "json": 1,
        },
        timeout=15,
    ).json()

    if res.get("status") != 1:
        raise Exception(f"Error 2Captcha al enviar imagen: {res}")

    req_id = res["request"]
    print(f"[2Captcha] Tarea ID {req_id}. Esperando resolución...")

    for _ in range(25):
        time.sleep(2.5)
        res_res = session.get(
            "https://2captcha.com/res.php",
            params={"key": API_KEY_2CAPTCHA, "action": "get", "id": req_id, "json": 1},
            timeout=10,
        ).json()
        if res_res.get("status") == 1:
            return res_res.get("request", "").strip(), req_id
        if res_res.get("request") != "CAPCHA_NOT_READY":
            raise Exception(f"Error devuelto por 2Captcha: {res_res}")

    raise TimeoutError("Tiempo agotado esperando a 2Captcha.")


def escribir_campo(locator, valor, nombre=""):
    try:
        if locator and locator.count() > 0:
            campo = locator.first
            campo.scroll_into_view_if_needed()
            campo.click()
            campo.fill("")
            campo.type(str(valor), delay=35)
            campo.dispatch_event("input")
            campo.dispatch_event("change")
            print(f"[OK] Campo '{nombre}' completado con éxito.")
            return True
    except Exception as exc:
        print(f"[WARN] Error en campo '{nombre}': {sanitize_for_logs(exc)}")
    return False


def ejecutar():
    faltan = faltan_variables()
    if faltan:
        print(f"[ERROR] Faltan variables obligatorias: {', '.join(faltan)}")
        return

    with sync_playwright() as p:
        print(f"[INFO] Iniciando navegador (modo silencioso: {HEADLESS})...")
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            viewport={"width": 1280, "height": 1050},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        try:
            print("[INFO] Accediendo a e-Konsulat...")
            page.goto(URL, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(2500)

            superado = False
            for intento in range(8):
                print(f"[INFO] Intento de captcha {intento + 1}/8...")
                captcha_elem = page.locator(SELECTORS["captcha_img"]).first
                try:
                    captcha_elem.wait_for(state="visible", timeout=15000)
                except Exception:
                    print(f"[WARN] Captcha no visible en intento {intento + 1}/8. Recargando página...")
                    try:
                        page.reload(timeout=30000, wait_until="domcontentloaded")
                        page.wait_for_timeout(2500)
                    except Exception:
                        pass
                    continue

                src_data = captcha_elem.get_attribute("src") or ""
                if not src_data.startswith("data:image"):
                    img_bytes = captcha_elem.screenshot()
                    src_data = base64.b64encode(img_bytes).decode("utf-8")

                texto_captcha, req_id = resolver_captcha_2captcha(src_data)
                print(f"[OK] 2Captcha respondió: '{texto_captcha}'")

                input_box = page.locator(SELECTORS["captcha_input"]).first
                input_box.click()
                input_box.fill("")
                input_box.type(texto_captcha, delay=60)
                input_box.dispatch_event("input")
                input_box.dispatch_event("change")
                page.wait_for_timeout(600)

                btn_dalej = page.locator(SELECTORS["next_button"]).first
                btn_dalej.click()
                page.wait_for_timeout(4000)

                if not page.locator(SELECTORS["captcha_img"]).is_visible():
                    print("[EXITO] Captcha superado.")
                    superado = True
                    break

                print("[REINTENTO] Rechazado. Refrescando...")
                try:
                    session.get(
                        "https://2captcha.com/res.php",
                        params={"key": API_KEY_2CAPTCHA, "action": "reportbad", "id": req_id},
                        timeout=5,
                    )
                except Exception:
                    pass
                btn_ref = page.locator(SELECTORS["refresh_button"]).first
                if btn_ref.is_visible():
                    btn_ref.click()
                    page.wait_for_timeout(2000)

            if not superado:
                print("[ERROR] No se pudo validar el captcha tras 8 intentos.")
                return

            todos_selects = page.locator(SELECTORS["service_select"]).all()
            select_servicio = todos_selects[1] if len(todos_selects) > 1 else todos_selects[0]
            select_servicio.scroll_into_view_if_needed()
            select_servicio.click()

            overlay = page.locator(".cdk-overlay-container")
            overlay.locator("mat-option").first.wait_for(state="visible", timeout=10000)
            overlay.locator("mat-option").filter(has_text="bez").first.click()
            page.wait_for_timeout(1500)

            todos_selects = page.locator(SELECTORS["service_select"]).all()
            select_personas = todos_selects[2] if len(todos_selects) > 2 else todos_selects[-1]
            select_personas.scroll_into_view_if_needed()
            select_personas.click()
            overlay.locator("mat-option").first.wait_for(state="visible", timeout=10000)
            overlay.locator("mat-option").filter(has_text="1").first.click()
            page.wait_for_timeout(3000)

            html_content = page.content()
            if "Lista oczekujących" in html_content and "jest pełna" in html_content:
                print("\n[REPORTE] Cola llena: sin novedades, se reintenta en la próxima corrida.")
                return

            if "Czy chcesz zapisać się na listę oczekujących?" in html_content:
                print("\n=======================================================")
                print("[ALERTA] ¡HAY LUGAR DISPONIBLE EN LA LISTA DE ESPERA!")
                print("=======================================================")

                alarma_local()
                page.locator(SELECTORS["accept_waitlist"]).first.click()
                page.wait_for_timeout(2000)

                btn_tak2 = page.locator(SELECTORS["accept_waitlist"]).first
                if btn_tak2.is_visible():
                    btn_tak2.click()
                page.wait_for_timeout(3000)

                print("[INFO] Intentando completar formulario automáticamente...")

                escribir_campo(page.locator(SELECTORS["nombre"]).first, DATOS_SOLICITANTE["nombre"], "Nombre")
                escribir_campo(page.locator(SELECTORS["apellido"]).first, DATOS_SOLICITANTE["apellido"], "Apellido")
                escribir_campo(page.locator(SELECTORS["documento"]).first, DATOS_SOLICITANTE["documento"], "Documento")
                escribir_campo(page.locator(SELECTORS["direccion"]).first, DATOS_SOLICITANTE["direccion_completa"], "Dirección")

                try:
                    pref_inp = page.locator(SELECTORS["prefijo"]).first
                    if pref_inp.count() > 0:
                        pref_inp.scroll_into_view_if_needed()
                        pref_inp.click()
                        pref_inp.fill("")
                        pref_inp.type("+54", delay=50)
                        page.wait_for_timeout(600)
                        opc = page.locator(SELECTORS["mat_option"] + ":has-text('+54')").first
                        if opc.is_visible(timeout=1500):
                            opc.click()
                        else:
                            pref_inp.press("Enter")
                        print("[OK] Campo 'Prefiks' completado (+54).")
                except Exception as exc:
                    print(f"[WARN] Error seleccionando Prefiks: {sanitize_for_logs(exc)}")

                escribir_campo(page.locator(SELECTORS["telefono"]).first, DATOS_SOLICITANTE["telefono"], "Teléfono")
                escribir_campo(page.locator(SELECTORS["email"]).first, DATOS_SOLICITANTE["email"], "Email")

                try:
                    t_area = page.locator(SELECTORS["descripcion"]).first
                    if t_area.count() > 0:
                        t_area.fill(DATOS_SOLICITANTE["descripcion"])
                        t_area.dispatch_event("input")
                        print("[OK] Campo 'Opis sprawy' completado.")
                except Exception:
                    pass

                chk_rejestr = page.locator(SELECTORS["mat_checkbox_registrante"]).first
                if chk_rejestr.count() > 0 and not chk_rejestr.locator("input").is_checked():
                    chk_rejestr.scroll_into_view_if_needed()
                    chk_rejestr.click()
                    print("[OK] Checkbox 'Czy sprawa dotyczy osoby rejestrującej' tildado.")
                    page.wait_for_timeout(500)

                chk_pasz = page.locator(SELECTORS["mat_checkbox_pasaporte"]).first
                if chk_pasz.count() > 0 and not chk_pasz.locator("input").is_checked():
                    chk_pasz.scroll_into_view_if_needed()
                    chk_pasz.click()
                    print("[OK] Checkbox '1-SZY PASZPORT' tildado.")
                    page.wait_for_timeout(1500)

                print("[INFO] Completando datos específicos del menor (Osoba 1)...")
                matka_inp = page.locator(SELECTORS["apellido_madre"]).first
                escribir_campo(matka_inp, DATOS_SOLICITANTE["apellido_madre"], "Nazwisko rodowe matki (Apellido madre)")

                fecha_inp = page.locator(SELECTORS["fecha_nacimiento"]).first
                escribir_campo(fecha_inp, DATOS_SOLICITANTE["fecha_nacimiento"], "Data urodzenia (Fecha nacimiento)")

                chk_rodo = page.locator(SELECTORS["checkbox_rodo"]).first
                if chk_rodo.count() > 0 and not chk_rodo.locator("input").is_checked():
                    chk_rodo.scroll_into_view_if_needed()
                    chk_rodo.click()
                    print("[OK] Checkbox RODO tildado.")
                    page.wait_for_timeout(500)

                page.wait_for_timeout(1500)

                print("[INFO] Presionando botón de envío...")
                btn_dalej = page.locator("button:has-text('Dalej')").last
                btn_dalej.scroll_into_view_if_needed()
                btn_dalej.click()
                page.wait_for_timeout(5000)

                html_final = page.content()
                if "Wystąpiły błędy walidacji" in html_final or "Pole wymagane" in html_final:
                    print("\n🚨 [INTERVENCIÓN HUMANA REQUERIDA] Hubo un error de validación.")
                    alarma_local()
                    msg_alerta = (
                        "🚨 *¡ATENCIÓN! SE ABRIÓ CUPO EN e-KONSULAT*\n"
                        "⚠️ *El formulario requiere intervención humana.*\n"
                        "La ventana quedó abierta en tu Mac con el temporizador activo (~4 minutos).\n"
                        "👉 Revisá la pantalla, completá el campo en rojo y tocá 'Dalej'."
                    )
                    enviar_telegram(msg_alerta)
                    print("[PAUSA] Manteniendo navegador abierto hasta 240 segundos para que intervengas...")
                    try:
                        page.wait_for_timeout(240000)
                    except Exception:
                        pass
                else:
                    print("\n=======================================================")
                    print("[CONFIRMACION REQUERIDA] No se encontró una confirmación explícita del registro.")
                    print("=======================================================\n")
                    msg_confirmacion = (
                        "⚠️ *e-Konsulat: registro no confirmado* 🇵🇱\n"
                        "El formulario avanzó sin errores de validación, pero no se encontró una "
                        "confirmación explícita del registro.\n"
                        "No asumas que el turno quedó registrado ni vuelvas a enviar el formulario "
                        "hasta comprobarlo. Revisá tu email y el estado en e-Konsulat."
                    )
                    enviar_telegram(msg_confirmacion)

        except Exception as exc:
            err = sanitize_for_logs(exc)
            print(f"[EXCEPCION] {err}")
            alarma_local()
            msg_error = f"⚠️ *e-Konsulat Excepción:* {err}\nRevisá la pantalla de la Mac."
            enviar_telegram(msg_error)
            try:
                if not page.is_closed():
                    page.wait_for_timeout(60000)
            except Exception:
                pass
        finally:
            try:
                context.close()
            except Exception:
                pass
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    ejecutar()
