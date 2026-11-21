"""Journal diagnostics without request payloads, exception messages or local variables."""

import logging
from pathlib import Path
import re
import traceback


def label(value):
    return re.sub(r"[^A-Za-z0-9_./:<>-]", "?", str(value))[:180]


class SafeRequestErrorFormatter(logging.Formatter):
    def format(self, record):
        request = getattr(record, "request", None)
        match = getattr(request, "resolver_match", None)
        route = label(getattr(match, "view_name", None) or "unresolved")
        status = getattr(record, "status_code", None)
        status = status if isinstance(status, int) and 100 <= status <= 599 else "unknown"
        lines = [f"Request failed status={status} route={route}"]
        if not record.exc_info:
            return "\n".join(lines)
        error = record.exc_info[1]
        seen = set()
        for _ in range(4):
            if error is None or id(error) in seen:
                break
            seen.add(id(error))
            lines.append("Exception type: " + label(type(error).__name__))
            for index, (frame, number) in enumerate(traceback.walk_tb(error.__traceback__)):
                if index >= 50:
                    lines.append("  [remaining frames omitted]")
                    break
                filename = "/".join(Path(frame.f_code.co_filename).parts[-2:])
                lines.append(f"  {label(filename)}:{number} in {label(frame.f_code.co_name)}")
            error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
        return "\n".join(lines)
