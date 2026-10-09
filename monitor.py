import os
import time
import base64
import subprocess
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Cargar variables de entorno desde archivo .env si existe
load_dotenv()

URL = "https://secure.e-konsulat.gov.pl/placowki/164/sprawy-paszportowe/wizyty/formularz"
API_KEY_2CAPTCHA = os.getenv("TWOCAPTCHA_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
HEADLESS = os.getenv("HEADLESS", "true").strip().lower() in ("true", "1", "yes", "t")

# Configurar sesión con reintentos
session = requests.Session()
retries = Retry(total=5, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

DATOS_FELIPE = {
    "nombre": os.getenv("CANDIDATO_NOMBRE", ""),
    "apellido": os.getenv("CANDIDATO_APELLIDO", ""),
    "documento": os.getenv("CANDIDATO_DOCUMENTO", ""),
    "direccion_completa": os.getenv("CANDIDATO_DIRECCION", ""),
    "telefono": os.getenv("CANDIDATO_TELEFONO", ""),
    "email": os.getenv("CANDIDATO_EMAIL", ""),
    "fecha_nacimiento": os.getenv("CANDIDATO_FECHA_NACIMIENTO", ""),
    "descripcion": os.getenv("CANDIDATO_DESCRIPCION", "Wniosek o pierwszy paszport 10-letni (PESEL nienadany)")
}

def enviar_telegram(mensaje: str, foto_path: str = None):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url_msg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        session.post(url_msg, data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"}, timeout=10)
        
        if foto_path and os.path.exists(foto_path):
            url_photo = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(foto_path, "rb") as f:
                session.post(url_photo, data={"chat_id": TELEGRAM_CHAT_ID, "caption": "Estado en pantalla"}, files={"photo": f}, timeout=15)
    except Exception as e:
        print(f"[WARN] Error enviando Telegram: {e}")

def alarma_local():
    """Hace sonar una alarma en macOS para avisarte si estás cerca de la Mac."""
    try:
        subprocess.Popen(["afplay", "/System/Library/Sounds/Glass.aiff"])
        subprocess.Popen(["say", "Atención. Cupo de pasaporte disponible. Revisar pantalla."])
    except Exception:
        pass

def resolver_captcha_2captcha(b64_img: str):
    if not API_KEY_2CAPTCHA:
        raise ValueError("Falta configurar TWOCAPTCHA_API_KEY.")
    
    if "," in b64_img:
        b64_img = b64_img.split(",", 1)[1]

    res = session.post("https://2captcha.com/in.php", data={
        "key": API_KEY_2CAPTCHA,
        "method": "base64",
        "body": b64_img,
        "regsense": 1,
        "min_len": 4,
        "max_len": 6,
        "json": 1
    }, timeout=15).json()
    
    if res.get("status") != 1:
        raise Exception(f"Error 2Captcha al enviar imagen: {res}")
    
    req_id = res["request"]
    print(f"[2Captcha] Tarea ID {req_id}. Esperando resolución...")

    for _ in range(25):
        time.sleep(2.5)
        res_res = session.get(f"https://2captcha.com/res.php?key={API_KEY_2CAPTCHA}&action=get&id={req_id}&json=1", timeout=10).json()
        if res_res.get("status") == 1:
            return res_res.get("request", "").strip(), req_id
        if res_res.get("request") != "CAPCHA_NOT_READY":
            raise Exception(f"Error devuelto por 2Captcha: {res_res}")
            
    raise TimeoutError("Tiempo agotado esperando a 2Captcha.")

def escribir_campo(locator, valor, nombre=""):
    try:
        if locator.is_visible(timeout=3000):
            locator.scroll_into_view_if_needed()
            locator.click()
            locator.fill("")
            locator.type(valor, delay=35)
            locator.dispatch_event("input")
            locator.dispatch_event("change")
            print(f"[OK] Campo '{nombre}' completado.")
            return True
    except Exception:
        pass
    return False

def ejecutar():
    with sync_playwright() as p:
        print(f"[INFO] Iniciando navegador (modo silencioso: {HEADLESS})...")
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(
            viewport={"width": 1280, "height": 1050},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            print("[INFO] Accediendo a e-Konsulat...")
            page.goto(URL, timeout=60000, wait_until="networkidle")
            page.wait_for_timeout(2500)

            # 1. Superar Captcha
            superado = False
            for intento in range(8):
                print(f"[INFO] Intento de captcha {intento + 1}/8...")
                captcha_elem = page.locator("img[alt='Weryfikacja obrazkowa']").first
                try:
                    captcha_elem.wait_for(state="visible", timeout=15000)
                except Exception as e_cap:
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

                input_box = page.locator("#mat-input-0, input[formcontrolname*='captcha' i], input").first
                input_box.click()
                input_box.fill("")
                input_box.type(texto_captcha, delay=60)
                input_box.dispatch_event("input")
                input_box.dispatch_event("change")
                page.wait_for_timeout(600)

                btn_dalej = page.locator("button:has-text('Dalej'), button:has-text('dalej')").first
                btn_dalej.click()
                page.wait_for_timeout(4000)

                if not page.locator("img[alt='Weryfikacja obrazkowa']").is_visible():
                    print("[EXITO] Captcha superado.")
                    superado = True
                    break
                else:
                    print(f"[REINTENTO] Rechazado. Refrescando...")
                    try:
                        session.get(f"https://2captcha.com/res.php?key={API_KEY_2CAPTCHA}&action=reportbad&id={req_id}", timeout=5)
                    except Exception:
                        pass
                    btn_ref = page.locator("button:has-text('Odśwież')").first
                    if btn_ref.is_visible():
                        btn_ref.click()
                        page.wait_for_timeout(2000)

            if not superado:
                print("[ERROR] No se pudo validar el captcha tras 8 intentos.")
                return

            # 2. Selección de trámite y personas
            todos_selects = page.locator("mat-select").all()
            select_servicio = todos_selects[1] if len(todos_selects) > 1 else todos_selects[0]
            select_servicio.scroll_into_view_if_needed()
            select_servicio.click()

            overlay = page.locator(".cdk-overlay-container")
            overlay.locator("mat-option").first.wait_for(state="visible", timeout=10000)
            overlay.locator("mat-option").filter(has_text="bez").first.click()
            page.wait_for_timeout(1500)

            todos_selects = page.locator("mat-select").all()
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

            # 3. ¡CUPO ENCONTRADO!
            if "Czy chcesz zapisać się na listę oczekujących?" in html_content:
                print("\n=======================================================")
                print("[ALERTA] ¡HAY LUGAR DISPONIBLE EN LA LISTA DE ESPERA!")
                print("=======================================================")

                alarma_local()
                page.locator("button:has-text('Tak')").first.click()
                page.wait_for_timeout(2000)

                btn_tak2 = page.locator("button:has-text('Tak')").first
                if btn_tak2.is_visible():
                    btn_tak2.click()
                page.wait_for_timeout(3000)

                # Guardamos el dump HTML completo para tener registro forense
                with open("formulario_abierto_dump.html", "w", encoding="utf-8") as f:
                    f.write(page.content())

                # Intentar completar automáticamente
                print("[INFO] Intentando completar formulario automáticamente...")
                inputs = page.locator("input:not([type='hidden']):not([type='checkbox'])").all()

                if len(inputs) >= 4:
                    escribir_campo(inputs[0], DATOS_FELIPE["nombre"], "Nombre")
                    escribir_campo(inputs[1], DATOS_FELIPE["apellido"], "Apellido")
                    escribir_campo(inputs[2], DATOS_FELIPE["documento"], "Documento")
                    escribir_campo(inputs[3], DATOS_FELIPE["direccion_completa"], "Dirección")

                try:
                    prefijo = page.locator("mat-form-field:has-text('Prefiks') mat-select").first
                    if prefijo.is_visible(timeout=2000):
                        prefijo.click()
                        overlay.locator("mat-option").filter(has_text="+54").first.click()
                except Exception:
                    pass

                escribir_campo(page.locator("mat-form-field:has-text('Telefon') input").first, DATOS_FELIPE["telefono"], "Teléfono")
                escribir_campo(page.locator("mat-form-field:has-text('Email') input").first, DATOS_FELIPE["email"], "Email")

                try:
                    t_area = page.locator("textarea").first
                    if t_area.is_visible(timeout=2000):
                        t_area.fill(DATOS_FELIPE["descripcion"])
                        t_area.dispatch_event("input")
                except Exception:
                    pass

                # Checkboxes
                for selector in [
                    "mat-checkbox:has-text('Czy sprawa dotyczy osoby rejestrującej')",
                    "mat-checkbox:has-text('1-SZY PASZPORT')",
                    "mat-checkbox:has-text('RODO'), mat-checkbox:has-text('Wyrażam zgodę')"
                ]:
                    try:
                        chk = page.locator(selector).first
                        if chk.is_visible(timeout=2000):
                            chk.scroll_into_view_if_needed()
                            chk.click()
                    except Exception:
                        pass

                page.wait_for_timeout(2000)
                page.screenshot(path="formulario_felipe_completado.png", full_page=True)

                # Intentar enviar
                print("[INFO] Presionando botón de envío...")
                btn_dalej = page.locator("button:has-text('Dalej')").last
                btn_dalej.scroll_into_view_if_needed()
                btn_dalej.click()
                page.wait_for_timeout(5000)

                html_final = page.content()
                page.screenshot(path="confirmacion_final.png", full_page=True)

                # VERIFICACIÓN DE ÉXITO O FALLBACK HUMANO
                if "Wystąpiły błędy walidacji" in html_final or "Pole wymagane" in html_final:
                    print("\n🚨 [INTERVENCIÓN HUMANA REQUERIDA] Hubo un error de validación.")
                    alarma_local()
                    
                    msg_alerta = (
                        "🚨 *¡ATENCIÓN! SE ABRIÓ CUPO EN e-KONSULAT*\n"
                        "⚠️ *El formulario requiere intervención humana.*\n"
                        "La ventana quedó abierta en tu Mac con el temporizador activo (~4 minutos).\n"
                        "👉 Revisá la pantalla, completá el campo en rojo y tocá 'Dalej'."
                    )
                    enviar_telegram(msg_alerta, "confirmacion_final.png")
                    
                    # Mantener el navegador abierto para que lo termines a mano
                    print("[PAUSA] Manteniendo navegador abierto hasta 240 segundos para que intervengas...")
                    try:
                        page.wait_for_timeout(240000)
                    except Exception:
                        pass
                else:
                    print("\n=======================================================")
                    print("[EXITO TOTAL] ¡Formulario enviado automáticamente con éxito!")
                    print("=======================================================\n")
                    msg_exito = "🎉 *¡TURNO REGISTRADO CON ÉXITO!* 🇵🇱\nRevisá el comprobante adjunto y tu casilla de email."
                    enviar_telegram(msg_exito, "confirmacion_final.png")

        except Exception as e:
            print(f"[EXCEPCION] {e}")
            try:
                if not page.is_closed():
                    page.screenshot(path="error_trace.png")
            except Exception:
                pass
            alarma_local()
            msg_error = f"⚠️ *e-Konsulat Excepción:* {e}\nRevisá la pantalla de la Mac."
            enviar_telegram(msg_error, "error_trace.png" if os.path.exists("error_trace.png") else None)
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
