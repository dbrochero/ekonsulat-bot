import os
import re
import time
import base64
from datetime import datetime
from typing import Dict, List, Optional, Tuple

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
DEBUG_DIR = os.path.join(BASE_DIR, "debug")
MAX_REGISTRATION_SUBMISSIONS = 5
REGISTRATION_RESPONSE_TIMEOUT_SECONDS = 15
FORM_LOAD_TIMEOUT_SECONDS = 30
REGISTRATION_CONFIRMATION_TEXTS = (
    "zostałeś zapisany na listę oczekujących",
    "zostałaś zapisana na listę oczekujących",
    "zostało zapisane na listę oczekujących",
    "zapisano na listę oczekujących",
    "zapis na listę oczekujących został potwierdzony",
    "zapis na listę oczekujących został przyjęty",
    "zostałeś dodany do listy oczekujących",
    "zostałaś dodana do listy oczekujących",
    "zostałeś wpisany na listę oczekujących",
    "zostałaś wpisana na listę oczekujących",
)
# Solo cuentan si aparecen (o aumentan) después de enviar: "pole wymagane"
# puede ser una leyenda fija del formulario y no un error.
REGISTRATION_VALIDATION_TEXTS = (
    "wystąpiły błędy walidacji",
    "pole wymagane",
)
API_KEY_2CAPTCHA = os.getenv("TWOCAPTCHA_API_KEY", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
HEADLESS = os.getenv("HEADLESS", "true").strip().lower() in ("true", "1", "yes", "t")

REQUIRED_ENV_VARS: List[str] = [
    "TWOCAPTCHA_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
]


def _por_etiqueta(texto: str, control: str = "input") -> str:
    """Selector de respaldo: el control dentro del mat-form-field con esa etiqueta."""
    return f"mat-form-field:has(mat-label:has-text('{texto}')) {control}"


SELECTORS = {
    "captcha_img": "img[alt='Weryfikacja obrazkowa']",
    "captcha_input": "#mat-input-0, input[formcontrolname*='captcha' i]",
    "next_button": "button:has-text('Dalej'), button:has-text('dalej')",
    "submit_button": "button:has-text('Dalej')",
    "refresh_button": "button:has-text('Odśwież')",
    "service_select": "mat-select",
    "mat_option": ".cdk-overlay-container mat-option",
    "accept_waitlist": "button:has-text('Tak')",
    "nombre": "input[aria-label*='Imię' i], #mat-input-1, " + _por_etiqueta("Imię"),
    "apellido": "input[aria-label*='Nazwisko' i]:not([aria-label*='rodowe' i]), #mat-input-2",
    "documento": "input[aria-label*='Numer paszportu' i], #mat-input-3, " + _por_etiqueta("Numer paszportu"),
    "direccion": "input[aria-label*='Ulica' i], #mat-input-4, " + _por_etiqueta("Ulica"),
    "prefijo": "input[aria-label*='Prefiks' i], #mat-input-5",
    "telefono": "input[aria-label*='Telefon' i], #mat-input-6, input[autocomplete='tel']",
    "email": "input[aria-label*='Email' i], #mat-input-7, input[autocomplete='email']",
    "descripcion": "textarea[aria-label*='Opis sprawy' i], textarea, #mat-input-8",
    "mat_checkbox_registrante": "mat-checkbox:has-text('Czy sprawa dotyczy osoby rejestrującej')",
    "mat_checkbox_pasaporte": "mat-checkbox:has-text('1-SZY PASZPORT')",
    "apellido_madre": "input[aria-label*='Nazwisko rodowe matki' i], input[placeholder*='Nazwisko rodowe matki' i], app-text-control:has-text('Nazwisko rodowe matki') input, #mat-input-9",
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

# (clave en DATOS_SOLICITANTE, nombre para el log, clave en SELECTORS)
CAMPOS_ANTES_DEL_PREFIJO = (
    ("nombre", "Nombre", "nombre"),
    ("apellido", "Apellido", "apellido"),
    ("documento", "Documento", "documento"),
    ("direccion_completa", "Dirección", "direccion"),
)
CAMPOS_DESPUES_DEL_PREFIJO = (
    ("telefono", "Teléfono", "telefono"),
    ("email", "Email", "email"),
    ("apellido_madre", "Nazwisko rodowe matki (Apellido madre)", "apellido_madre"),
)
CHECKBOXES_OBLIGATORIOS = (
    ("mat_checkbox_registrante", "Czy sprawa dotyczy osoby rejestrującej"),
    ("mat_checkbox_pasaporte", "1-SZY PASZPORT"),
    ("checkbox_rodo", "RODO"),
)

# Recorre el formulario y devuelve "etiqueta: mensaje" por cada control
# inválido visible. No devuelve valores ingresados (datos personales).
JS_ERRORES_FORMULARIO = r"""
() => {
  const visible = el => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
  const limpio = (t, n) => (t || '').replace(/\s+/g, ' ').trim().slice(0, n);
  const contenedor = el => el.closest('mat-form-field, .mat-mdc-form-field, mat-checkbox, mat-radio-group') || el;
  const etiqueta = (cont, el) => {
    const lab = cont.querySelector('mat-label, label');
    return limpio((lab && lab.innerText) || el.getAttribute('aria-label') ||
                  el.getAttribute('placeholder') || el.getAttribute('formcontrolname') ||
                  el.tagName.toLowerCase(), 80);
  };
  const vistos = new Set();
  const salida = [];
  const candidatos = document.querySelectorAll(
    '[aria-invalid="true"], mat-error, .mat-mdc-form-field-error, ' +
    'mat-checkbox.ng-invalid.ng-touched, mat-select.ng-invalid.ng-touched'
  );
  for (const el of candidatos) {
    if (!visible(el)) continue;
    const cont = contenedor(el);
    if (vistos.has(cont)) continue;
    vistos.add(cont);
    const err = cont.querySelector('mat-error, .mat-mdc-form-field-error');
    const msg = err && visible(err) ? limpio(err.innerText, 120) : 'inválido';
    salida.push(etiqueta(cont, el) + ': ' + msg);
  }
  return salida;
}
"""

JS_TITULOS_PAGINA = r"""
() => Array.from(document.querySelectorAll('h1, h2, h3, mat-dialog-container h2, .mat-mdc-dialog-title'))
  .filter(el => el.offsetWidth || el.offsetHeight)
  .map(el => el.innerText.replace(/\s+/g, ' ').trim().slice(0, 100))
  .filter(Boolean).slice(0, 6)
"""


class CaptchaServiceError(RuntimeError):
    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


# ---------------------------------------------------------------------------
# Utilidades generales
# ---------------------------------------------------------------------------

def sin_secretos(texto) -> str:
    """Oculta la API key de 2Captcha y el token de Telegram en cualquier texto."""
    texto = str(texto)
    for secreto in (API_KEY_2CAPTCHA, TELEGRAM_BOT_TOKEN):
        if secreto:
            texto = texto.replace(secreto, "***")
    return texto


def sanitize_for_logs(text: object) -> str:
    return sin_secretos(text)


def escapar_markdown(texto: str) -> str:
    """Escapa caracteres que rompen el Markdown clásico de Telegram."""
    return re.sub(r"([_*`\[])", r"\\\1", str(texto))


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


def enviar_telegram(mensaje: str) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[ERROR] No se pudo enviar Telegram: faltan token o chat ID.")
        return False
    url_msg = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        response = session.post(
            url_msg,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje, "parse_mode": "Markdown"},
            timeout=10,
        )
        if response.status_code == 400:
            # Markdown inválido: se reenvía como texto plano para no perder el aviso.
            response = session.post(
                url_msg,
                data={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje},
                timeout=10,
            )
        response.raise_for_status()
        try:
            resultado = response.json()
        except ValueError as exc:
            raise RuntimeError("Telegram devolvió una respuesta no JSON.") from exc
        if not isinstance(resultado, dict) or resultado.get("ok") is not True:
            raise RuntimeError("Telegram no confirmó el envío del mensaje.")
        return True
    except (requests.RequestException, RuntimeError) as exc:
        print(f"[WARN] Error enviando Telegram: {sanitize_for_logs(exc)}")
        return False


def guardar_dump(page, motivo: str) -> Optional[str]:
    """Guarda el HTML de la página en debug/ (ignorado por git) para diagnosticar."""
    try:
        os.makedirs(DEBUG_DIR, mode=0o700, exist_ok=True)
        nombre = f"{datetime.now():%Y%m%d_%H%M%S}_{motivo}.html"
        ruta = os.path.join(DEBUG_DIR, nombre)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write(page.content())
        os.chmod(ruta, 0o600)
        print(f"[DEBUG] HTML de la página guardado en debug/{nombre}")
        return ruta
    except Exception as exc:
        print(f"[WARN] No se pudo guardar el HTML de diagnóstico: {sanitize_for_logs(exc)}")
        return None


def titulos_pagina(page) -> List[str]:
    try:
        return page.evaluate(JS_TITULOS_PAGINA) or []
    except Exception:
        return []


def texto_pagina(page) -> str:
    try:
        return page.locator("body").inner_text().casefold()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 2Captcha
# ---------------------------------------------------------------------------

def respuesta_json_2captcha(response, etapa: str) -> dict:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise CaptchaServiceError(
            f"2Captcha devolvió HTTP {response.status_code} al {etapa}.",
            retryable=response.status_code >= 500,
        ) from exc

    try:
        resultado = response.json()
    except ValueError as exc:
        tipo_contenido = response.headers.get("Content-Type", "desconocido")
        raise CaptchaServiceError(
            f"2Captcha devolvió una respuesta no JSON al {etapa} "
            f"(HTTP {response.status_code}, Content-Type: {tipo_contenido}).",
            retryable=True,
        ) from exc

    if not isinstance(resultado, dict):
        raise CaptchaServiceError(
            f"2Captcha devolvió JSON con formato inesperado al {etapa}.",
            retryable=True,
        )

    return resultado


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
    )
    res = respuesta_json_2captcha(res, "enviar el captcha")

    if res.get("status") != 1:
        codigo = str(res.get("request", "respuesta inesperada"))
        raise CaptchaServiceError(
            f"2Captcha no aceptó la imagen ({codigo}).",
            retryable=(codigo == "ERROR_CAPTCHA_UNSOLVABLE"),
        )

    req_id = res["request"]
    print(f"[2Captcha] Tarea ID {req_id}. Esperando resolución...")

    for _ in range(25):
        time.sleep(2.5)
        res_res = session.get(
            "https://2captcha.com/res.php",
            params={"key": API_KEY_2CAPTCHA, "action": "get", "id": req_id, "json": 1},
            timeout=10,
        )
        res_res = respuesta_json_2captcha(res_res, "consultar el resultado del captcha")
        if res_res.get("status") == 1:
            return res_res.get("request", "").strip(), req_id
        if res_res.get("request") != "CAPCHA_NOT_READY":
            codigo = str(res_res.get("request", "respuesta inesperada"))
            raise CaptchaServiceError(
                f"2Captcha no pudo resolver la imagen ({codigo}).",
                retryable=(codigo == "ERROR_CAPTCHA_UNSOLVABLE"),
            )

    raise TimeoutError("Tiempo agotado esperando a 2Captcha.")


def reportar_captcha_incorrecto(req_id: str) -> None:
    try:
        response = session.get(
            "https://2captcha.com/res.php",
            params={"key": API_KEY_2CAPTCHA, "action": "reportbad", "id": req_id},
            timeout=5,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[WARN] No se pudo reportar el captcha rechazado: {sanitize_for_logs(exc)}")


def refrescar_captcha(page):
    boton = page.locator(SELECTORS["refresh_button"]).first
    if boton.count() > 0 and boton.is_visible():
        boton.click()
    else:
        page.reload(timeout=30000, wait_until="domcontentloaded")
    page.locator(SELECTORS["captcha_img"]).first.wait_for(
        state="visible", timeout=15000
    )
    page.wait_for_timeout(1000)


def superar_captcha(page, max_intentos: int = 8) -> bool:
    for intento in range(1, max_intentos + 1):
        ultimo = intento == max_intentos
        print(f"[INFO] Intento de captcha {intento}/{max_intentos}...")
        captcha_elem = page.locator(SELECTORS["captcha_img"]).first
        try:
            captcha_elem.wait_for(state="visible", timeout=15000)
        except Exception:
            print(f"[WARN] Captcha no visible en intento {intento}/{max_intentos}. Recargando página...")
            try:
                refrescar_captcha(page)
            except Exception as refresh_exc:
                raise RuntimeError(
                    "No se pudo recargar la página para obtener otro captcha."
                ) from refresh_exc
            continue

        src_data = captcha_elem.get_attribute("src") or ""
        if not src_data.startswith("data:image"):
            src_data = base64.b64encode(captcha_elem.screenshot()).decode("utf-8")

        try:
            texto_captcha, req_id = resolver_captcha_2captcha(src_data)
        except (CaptchaServiceError, requests.RequestException, TimeoutError) as exc:
            print(f"[WARN] Falló la resolución del captcha ({sanitize_for_logs(exc)}).")
            if isinstance(exc, CaptchaServiceError) and not exc.retryable:
                raise
            if ultimo:
                raise RuntimeError(
                    f"No se pudo resolver el captcha tras {max_intentos} intentos."
                ) from exc
            try:
                refrescar_captcha(page)
            except Exception as refresh_exc:
                raise RuntimeError(
                    "No se pudo obtener un captcha nuevo tras un fallo de resolución."
                ) from refresh_exc
            continue

        input_box = page.locator(SELECTORS["captcha_input"]).first
        input_box.click()
        input_box.fill("")
        input_box.type(texto_captcha, delay=60)
        input_box.dispatch_event("input")
        input_box.dispatch_event("change")
        page.wait_for_timeout(600)

        page.locator(SELECTORS["next_button"]).first.click()
        page.wait_for_timeout(4000)

        if not page.locator(SELECTORS["captcha_img"]).is_visible():
            print("[EXITO] Captcha superado.")
            return True

        print("[REINTENTO] Rechazado. Refrescando...")
        reportar_captcha_incorrecto(req_id)
        if not ultimo:
            refrescar_captcha(page)

    return False


# ---------------------------------------------------------------------------
# Selección de servicio y apertura del formulario
# ---------------------------------------------------------------------------

def elegir_opcion(page, select, texto: str) -> None:
    select.scroll_into_view_if_needed()
    select.click()
    overlay = page.locator(".cdk-overlay-container")
    overlay.locator("mat-option").first.wait_for(state="visible", timeout=10000)
    overlay.locator("mat-option").filter(has_text=texto).first.click()


def seleccionar_servicio(page) -> None:
    selects = page.locator(SELECTORS["service_select"]).all()
    elegir_opcion(page, selects[1] if len(selects) > 1 else selects[0], "bez")
    page.wait_for_timeout(1500)

    selects = page.locator(SELECTORS["service_select"]).all()
    elegir_opcion(page, selects[2] if len(selects) > 2 else selects[-1], "1")
    page.wait_for_timeout(3000)


def formulario_visible(page) -> bool:
    try:
        return page.locator(SELECTORS["nombre"]).first.is_visible()
    except Exception:
        return False


def esperar_formulario(page, timeout_s: int = FORM_LOAD_TIMEOUT_SECONDS) -> bool:
    """Acepta los diálogos 'Tak' que aparezcan y espera a que el formulario
    esté realmente en pantalla, en lugar de esperar un tiempo fijo."""
    limite = time.monotonic() + timeout_s
    clics_tak = 0
    while time.monotonic() < limite:
        if formulario_visible(page):
            page.wait_for_timeout(1000)  # deja terminar el render de Angular
            print(f"[INFO] Formulario cargado (diálogos aceptados: {clics_tak}).")
            return True
        boton_tak = page.locator(SELECTORS["accept_waitlist"]).first
        try:
            if boton_tak.count() > 0 and boton_tak.is_visible():
                boton_tak.click()
                clics_tak += 1
                page.wait_for_timeout(1000)
                continue
        except Exception:
            pass
        page.wait_for_timeout(500)
    return False


# ---------------------------------------------------------------------------
# Completar el formulario
# ---------------------------------------------------------------------------

def quitar_foco(campo) -> None:
    """Dispara blur para que Angular marque el campo como 'touched' y lo valide."""
    try:
        campo.evaluate("el => el.blur()")
    except Exception:
        pass


def campo_invalido(campo) -> bool:
    try:
        return (campo.get_attribute("aria-invalid") or "").lower() == "true"
    except Exception:
        return False


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
            if campo.input_value() != str(valor):
                print(f"[WARN] El campo '{nombre}' no conserva el valor ingresado.")
                return False
            quitar_foco(campo)
            if campo_invalido(campo):
                print(f"[WARN] El sitio marca el campo '{nombre}' como inválido.")
                return False
            print(f"[OK] Campo '{nombre}' completado con éxito.")
            return True
    except Exception as exc:
        print(f"[WARN] Error en campo '{nombre}': {sanitize_for_logs(exc)}")
    else:
        print(f"[WARN] No se encontró el campo '{nombre}'.")
    return False


def variantes_fecha(valor: str) -> List[str]:
    """Devuelve la fecha en el formato configurado y en los formatos habituales
    del sitio. ISO va primero porque es inequívoco para cualquier parser."""
    fecha = None
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            fecha = datetime.strptime(valor, fmt)
            break
        except ValueError:
            continue
    if fecha is None:
        return [valor]
    variantes = [fecha.strftime(f) for f in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y")]
    if valor not in variantes:
        variantes.insert(0, valor)
    return variantes


def escribir_fecha(locator, valor: str, nombre: str) -> bool:
    """Prueba formatos de fecha hasta que el datepicker la acepte como válida."""
    if not locator or locator.count() == 0:
        print(f"[WARN] No se encontró el campo '{nombre}'.")
        return False
    campo = locator.first
    for variante in variantes_fecha(valor):
        try:
            campo.scroll_into_view_if_needed()
            campo.click()
            campo.fill("")
            campo.type(variante, delay=35)
            campo.dispatch_event("input")
            campo.dispatch_event("change")
            quitar_foco(campo)
            campo.page.wait_for_timeout(300)
            if campo.input_value().strip() and not campo_invalido(campo):
                print(f"[OK] Campo '{nombre}' completado con éxito.")
                return True
        except Exception as exc:
            print(f"[WARN] Error en campo '{nombre}': {sanitize_for_logs(exc)}")
            return False
    print(f"[WARN] El sitio no aceptó '{nombre}' en ningún formato de fecha.")
    return False


def completar_prefijo(page) -> bool:
    """Devuelve False solo si el campo existe y no se pudo completar."""
    pref_inp = page.locator(SELECTORS["prefijo"]).first
    try:
        if pref_inp.count() == 0:
            return True
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
        return True
    except Exception as exc:
        print(f"[WARN] Error seleccionando Prefiks: {sanitize_for_logs(exc)}")
        return False


def marcar_checkbox(locator, nombre: str) -> bool:
    try:
        if locator.count() == 0:
            print(f"[WARN] No se encontró el checkbox '{nombre}'.")
            return False
        checkbox = locator.first
        control = checkbox.locator("input").first
        if control.count() == 0:
            print(f"[WARN] No se encontró el control del checkbox '{nombre}'.")
            return False
        if not control.is_checked():
            checkbox.scroll_into_view_if_needed()
            checkbox.click()
        if not control.is_checked():
            print(f"[WARN] No se pudo tildar el checkbox '{nombre}'.")
            return False
        print(f"[OK] Checkbox '{nombre}' tildado.")
        return True
    except Exception as exc:
        print(f"[WARN] Error en checkbox '{nombre}': {sanitize_for_logs(exc)}")
        return False


def completar_formulario(page) -> List[str]:
    """Completa todos los campos y devuelve los que no se pudieron completar."""
    fallidos: List[str] = []

    for clave, nombre, selector in CAMPOS_ANTES_DEL_PREFIJO:
        if not escribir_campo(page.locator(SELECTORS[selector]).first, DATOS_SOLICITANTE[clave], nombre):
            fallidos.append(nombre)

    if not completar_prefijo(page):
        fallidos.append("Prefiks")

    for clave, nombre, selector in CAMPOS_DESPUES_DEL_PREFIJO:
        if not escribir_campo(page.locator(SELECTORS[selector]).first, DATOS_SOLICITANTE[clave], nombre):
            fallidos.append(nombre)

    nombre_fecha = "Data urodzenia (Fecha nacimiento)"
    if not escribir_fecha(
        page.locator(SELECTORS["fecha_nacimiento"]).first,
        DATOS_SOLICITANTE["fecha_nacimiento"],
        nombre_fecha,
    ):
        fallidos.append(nombre_fecha)

    t_area = page.locator(SELECTORS["descripcion"]).first
    try:
        if t_area.count() > 0 and not escribir_campo(
            t_area, DATOS_SOLICITANTE["descripcion"], "Opis sprawy"
        ):
            print("[WARN] No se pudo completar la descripción.")
    except Exception as exc:
        print(f"[WARN] Error completando la descripción: {sanitize_for_logs(exc)}")

    for selector, nombre in CHECKBOXES_OBLIGATORIOS:
        if not marcar_checkbox(page.locator(SELECTORS[selector]), nombre):
            fallidos.append(nombre)

    return fallidos


# ---------------------------------------------------------------------------
# Envío y resultado
# ---------------------------------------------------------------------------

def registro_confirmado(page) -> bool:
    texto_visible = texto_pagina(page)
    return any(frase in texto_visible for frase in REGISTRATION_CONFIRMATION_TEXTS)


def errores_formulario(page) -> List[str]:
    """Lista 'campo: mensaje' de los controles que el sitio marca como inválidos."""
    try:
        return list(page.evaluate(JS_ERRORES_FORMULARIO) or [])
    except Exception as exc:
        print(f"[WARN] No se pudieron leer los errores del formulario: {sanitize_for_logs(exc)}")
        return []


def textos_validacion_nuevos(texto_antes: str, texto_despues: str) -> List[str]:
    """Frases de validación que aparecieron (o se multiplicaron) tras enviar."""
    return [
        frase
        for frase in REGISTRATION_VALIDATION_TEXTS
        if texto_despues.count(frase) > texto_antes.count(frase)
    ]


def error_validacion_registro(page, texto_antes: str = "") -> List[str]:
    """Devuelve la lista de errores de validación (vacía si no hay)."""
    errores = errores_formulario(page)
    if errores:
        return errores
    return [f"mensaje del sitio: '{f}'" for f in textos_validacion_nuevos(texto_antes, texto_pagina(page))]


def enviar_formulario(page) -> Tuple[str, int, List[str]]:
    """Envía el formulario y devuelve (estado, envíos, errores).

    Estados: 'confirmado', 'validacion', 'pagina_cambio', 'sin_boton',
    'sin_confirmacion'. Solo reenvía si el formulario sigue en pantalla
    sin errores, para no apretar un botón de otra etapa.
    """
    envios = 0
    for intento in range(1, MAX_REGISTRATION_SUBMISSIONS + 1):
        boton = page.locator(SELECTORS["submit_button"]).last
        if boton.count() == 0 or not boton.is_visible() or not boton.is_enabled():
            print("[WARN] No se encontró el botón 'Dalej' habilitado.")
            return ("sin_boton" if envios == 0 else "sin_confirmacion"), envios, []

        texto_antes = texto_pagina(page)
        print(f"[INFO] Envío del formulario {intento}/{MAX_REGISTRATION_SUBMISSIONS}...")
        boton.scroll_into_view_if_needed()
        boton.click()
        envios += 1

        for _ in range(REGISTRATION_RESPONSE_TIMEOUT_SECONDS * 2):
            page.wait_for_timeout(500)
            if registro_confirmado(page):
                return "confirmado", envios, []
            errores = error_validacion_registro(page, texto_antes)
            if errores:
                return "validacion", envios, errores
            if not formulario_visible(page):
                page.wait_for_timeout(2000)
                if registro_confirmado(page):
                    return "confirmado", envios, []
                return "pagina_cambio", envios, []

        if intento < MAX_REGISTRATION_SUBMISSIONS:
            print("[WARN] Sin confirmación explícita y el formulario sigue en pantalla; se volverá a enviar.")

    return "sin_confirmacion", envios, []


def mostrar_ventana_navegador(page):
    if HEADLESS:
        print("[WARN] No se puede mostrar Chrome porque HEADLESS=true.")
        return
    page.bring_to_front()


def pausa_para_intervencion(page, motivo: str) -> None:
    mostrar_ventana_navegador(page)
    if not HEADLESS:
        print(f"[PAUSA] Manteniendo navegador abierto hasta 240 segundos para {motivo}...")
        page.wait_for_timeout(240000)


def nota_headless() -> str:
    if HEADLESS:
        return (
            "\nChromium está oculto (HEADLESS=true): no se puede intervenir en esta corrida. "
            "El HTML quedó guardado en la carpeta debug/ para revisarlo."
        )
    return "\nChrome queda abierto durante 4 minutos para que revises la página."


def procesar_cupo(page) -> None:
    print("\n=======================================================")
    print("[ALERTA] ¡HAY LUGAR DISPONIBLE EN LA LISTA DE ESPERA!")
    print("=======================================================")

    if not esperar_formulario(page):
        titulos = titulos_pagina(page)
        print(
            f"[ERROR] El formulario no apareció en {FORM_LOAD_TIMEOUT_SECONDS}s. "
            f"Títulos visibles: {titulos or 'ninguno'}"
        )
        guardar_dump(page, "formulario_no_cargo")
        enviar_telegram(
            "🚨 *¡ATENCIÓN! SE ABRIÓ CUPO EN e-KONSULAT*\n"
            f"⚠️ El formulario no apareció en {FORM_LOAD_TIMEOUT_SECONDS} segundos."
            + escapar_markdown(nota_headless())
        )
        pausa_para_intervencion(page, "que completes el formulario")
        return

    print("[INFO] Completando formulario automáticamente...")
    fallidos = completar_formulario(page)
    page.wait_for_timeout(800)

    # Errores que el sitio ya muestra antes de enviar (por ejemplo, formato de fecha).
    errores_previos = errores_formulario(page)
    if errores_previos:
        print("[WARN] El sitio marca errores antes de enviar: " + "; ".join(errores_previos))

    if fallidos:
        print("[ERROR] No se enviará el formulario; faltan completar: " + ", ".join(fallidos))
        guardar_dump(page, "campos_fallidos")
        detalle = ", ".join(fallidos)
        if errores_previos:
            detalle += "\nErrores del sitio: " + "; ".join(errores_previos)
        enviar_telegram(
            "🚨 *¡ATENCIÓN! SE ABRIÓ CUPO EN e-KONSULAT*\n"
            "⚠️ *El formulario requiere revisión humana.*\n"
            "No se pudo completar/verificar: " + escapar_markdown(detalle + nota_headless())
        )
        print("\n🚨 [INTERVENCIÓN HUMANA REQUERIDA] No se puede continuar con el formulario.")
        pausa_para_intervencion(page, "que intervengas")
        return

    estado, envios, errores = enviar_formulario(page)

    if estado == "confirmado":
        print("[REGISTRO CONFIRMADO] e-Konsulat confirmó la inscripción en la lista de espera.")
        enviar_telegram(
            "✅ *e-Konsulat confirmó el registro en la lista de espera.*\n"
            f"Envíos realizados: {envios}."
        )
        return

    if estado == "validacion":
        print("[ERROR] e-Konsulat rechazó el formulario: " + "; ".join(errores))
        guardar_dump(page, "validacion")
        print("\n🚨 [INTERVENCIÓN HUMANA REQUERIDA] No se puede continuar con el formulario.")
        enviar_telegram(
            "🚨 *¡ATENCIÓN! SE ABRIÓ CUPO EN e-KONSULAT*\n"
            "⚠️ *e-Konsulat rechazó el formulario.*\n"
            + escapar_markdown("Errores: " + "; ".join(errores) + nota_headless())
        )
        pausa_para_intervencion(page, "que corrijas el campo indicado")
        return

    if estado == "pagina_cambio":
        titulos = titulos_pagina(page)
        print(
            "[CONFIRMACION REQUERIDA] El formulario desapareció tras el envío pero no se "
            f"reconoció un mensaje de confirmación. Títulos visibles: {titulos or 'ninguno'}"
        )
        guardar_dump(page, "pagina_cambio")
        enviar_telegram(
            "⚠️ *e-Konsulat: el formulario se envió y la página cambió.*\n"
            "No se reconoció un mensaje de confirmación; no se reenvió para evitar duplicados.\n"
            + escapar_markdown(
                f"Títulos visibles: {', '.join(titulos) or 'ninguno'}.\n"
                "Revisá tu email y el estado en e-Konsulat." + nota_headless()
            )
        )
        pausa_para_intervencion(page, "revisar el estado")
        return

    # sin_boton o sin_confirmacion
    print(f"[CONFIRMACION REQUERIDA] No hubo confirmación explícita tras {envios} envío(s) ({estado}).")
    guardar_dump(page, estado)
    enviar_telegram(
        "⚠️ *e-Konsulat: registro no confirmado.*\n"
        + escapar_markdown(
            f"El bot realizó {envios} de {MAX_REGISTRATION_SUBMISSIONS} envíos permitidos "
            "y no encontró una confirmación explícita. Verificá el estado en e-Konsulat "
            "y el email antes de iniciar otra inscripción." + nota_headless()
        )
    )
    pausa_para_intervencion(page, "revisar el estado")


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------

def ejecutar():
    faltan = faltan_variables()
    if faltan:
        print(f"[ERROR] Faltan variables obligatorias: {', '.join(faltan)}")
        return

    with sync_playwright() as p:
        print(f"[INFO] Iniciando navegador (modo silencioso: {HEADLESS})...")
        argumentos = [] if HEADLESS else ["--start-minimized"]
        browser = p.chromium.launch(headless=HEADLESS, args=argumentos)
        context = browser.new_context(
            viewport={"width": 1280, "height": 1050},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
        )
        page = context.new_page()

        try:
            print("[INFO] Accediendo a e-Konsulat...")
            page.goto(URL, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(2500)

            if not superar_captcha(page):
                print("[ERROR] No se pudo validar el captcha tras 8 intentos.")
                return

            seleccionar_servicio(page)

            html_content = page.content()
            if "Lista oczekujących" in html_content and "jest pełna" in html_content:
                print("\n[REPORTE] Cola llena: sin novedades, se reintenta en la próxima corrida.")
                return

            if "Czy chcesz zapisać się na listę oczekujących?" in html_content:
                procesar_cupo(page)

        except Exception as exc:
            err = sanitize_for_logs(exc)
            print(f"[EXCEPCION] {err}")
            try:
                guardar_dump(page, "excepcion")
            except Exception:
                pass
            enviar_telegram(
                "⚠️ *e-Konsulat Excepción:* " + escapar_markdown(err) + "\nRevisá el mensaje de error."
            )
            if not HEADLESS:
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
