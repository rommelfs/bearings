import logging
import sys
from types import SimpleNamespace
from django.test import SimpleTestCase
from config.request_errors import SafeRequestErrorFormatter


class RequestErrorTests(SimpleTestCase):
    def test_code_locations_and_exception_chain_are_kept_but_sensitive_data_is_not(self):
        secret = "PRIVATE-KEY-NEVER-LOG-THIS"
        try:
            try:
                raise ValueError(secret)
            except ValueError:
                raise AttributeError(secret)
        except AttributeError:
            record = logging.LogRecord(
                "django.request",
                logging.ERROR,
                __file__,
                1,
                "request path and payload " + secret,
                (),
                sys.exc_info(),
            )
        record.status_code = 500
        record.request = SimpleNamespace(
            resolver_match=SimpleNamespace(view_name="company-merge", kwargs={"token": secret}),
            POST={"key": secret},
            path="/" + secret,
        )
        result = SafeRequestErrorFormatter().format(record)
        self.assertIn("status=500 route=company-merge", result)
        self.assertIn("AttributeError", result)
        self.assertIn("ValueError", result)
        self.assertIn("test_request_errors.py", result)
        self.assertNotIn(secret, result)
        self.assertNotIn("raise ValueError", result)

    def test_error_without_traceback_does_not_fall_back_to_raw_message(self):
        record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "SENSITIVE", (), None)
        self.assertEqual(
            SafeRequestErrorFormatter().format(record), "Request failed status=unknown route=unresolved"
        )
