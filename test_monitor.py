import contextlib
import io
import unittest
from unittest.mock import Mock, patch

import monitor


class FakeField:
    def __init__(self):
        self.value = ""

    @property
    def first(self):
        return self

    def count(self):
        return 1

    def scroll_into_view_if_needed(self):
        pass

    def click(self):
        pass

    def fill(self, value):
        self.value = value

    def type(self, value, delay=None):
        self.value += value

    def dispatch_event(self, event):
        pass

    def input_value(self):
        return self.value


class FakePage:
    def __init__(self, body="", errores=None):
        self.body = body
        self.errores = errores or []

    def locator(self, selector):
        locator = Mock()
        locator.inner_text.return_value = self.body
        return locator

    def evaluate(self, script):
        return self.errores


class MonitorTests(unittest.TestCase):
    def test_apellido_madre_selector_has_placeholder_and_input_id_fallbacks(self):
        selector = monitor.SELECTORS["apellido_madre"]
        self.assertIn("input[placeholder*='Nazwisko rodowe matki' i]", selector)
        self.assertIn("#mat-input-9", selector)

    def test_escribir_campo_verifies_value(self):
        field = FakeField()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(monitor.escribir_campo(field, "Ana", "Nombre"))
        self.assertEqual(field.value, "Ana")

    def test_escribir_campo_fails_when_missing(self):
        field = Mock()
        field.count.return_value = 0
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(monitor.escribir_campo(field, "Ana", "Nombre"))

    def test_detects_dom_validation_errors_with_field_names(self):
        page = FakePage(errores=["Data urodzenia: Niepoprawny format"])
        self.assertEqual(
            monitor.error_validacion_registro(page), ["Data urodzenia: Niepoprawny format"]
        )

    def test_static_required_legend_is_not_a_validation_error(self):
        # "* pole wymagane" como leyenda fija antes y después del envío.
        page = FakePage("* pole wymagane")
        self.assertEqual(monitor.error_validacion_registro(page, "* pole wymagane"), [])

    def test_new_validation_text_after_submit_is_an_error(self):
        page = FakePage("* pole wymagane\nPole wymagane")
        self.assertTrue(monitor.error_validacion_registro(page, "* pole wymagane"))
        self.assertFalse(monitor.error_validacion_registro(FakePage("Formulario válido")))

    def test_date_variants_start_with_iso_and_include_polish_format(self):
        self.assertEqual(
            monitor.variantes_fecha("1990-05-12"),
            ["1990-05-12", "12.05.1990", "12/05/1990"],
        )
        self.assertEqual(monitor.variantes_fecha("12.05.1990")[0], "1990-05-12")
        self.assertEqual(monitor.variantes_fecha("raro"), ["raro"])

    def test_escape_markdown(self):
        self.assertEqual(monitor.escapar_markdown("a_b*c"), "a\\_b\\*c")

    def test_unsolvable_captcha_is_retryable(self):
        response = Mock()
        response.json.return_value = {
            "status": 0,
            "request": "ERROR_CAPTCHA_UNSOLVABLE",
        }
        with patch.object(monitor, "API_KEY_2CAPTCHA", "test-key"), patch.object(
            monitor.session, "post", return_value=response
        ), self.assertRaises(monitor.CaptchaServiceError) as error:
            monitor.resolver_captcha_2captcha("base64")
        self.assertTrue(error.exception.retryable)

    def test_telegram_requires_positive_api_confirmation(self):
        response = Mock()
        response.json.return_value = {"ok": True}
        with patch.object(monitor, "TELEGRAM_BOT_TOKEN", "test-token"), patch.object(
            monitor, "TELEGRAM_CHAT_ID", "test-chat"
        ), patch.object(monitor.session, "post", return_value=response):
            self.assertTrue(monitor.enviar_telegram("test"))

        response.json.return_value = {"ok": False}
        with patch.object(monitor, "TELEGRAM_BOT_TOKEN", "test-token"), patch.object(
            monitor, "TELEGRAM_CHAT_ID", "test-chat"
        ), patch.object(monitor.session, "post", return_value=response), contextlib.redirect_stdout(
            io.StringIO()
        ):
            self.assertFalse(monitor.enviar_telegram("test"))


if __name__ == "__main__":
    unittest.main()
