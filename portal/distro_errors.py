"""Allowlisted local evaluator diagnostics; never publish arbitrary exception text."""

from .connectors.http import ConnectorError


CAUSES = {
    "kernel_evidence_limit": (
        "Kernel evidence budget exceeded; no partial evaluation published",
        "Running-kernel evidence exceeded its 16 MiB retention limit.",
        "The platform operator must inspect kernel rule expansion; the complete device transaction was rolled back.",
    ),
    "kernel_accounting": (
        "Kernel definition accounting incomplete",
        "The compiled kernel definition count does not agree with the evaluated cache.",
        "The platform operator must inspect cache integrity and recompile before retrying; no partial check was published.",
    ),
    "ubuntu_status_limit": (
        "Ubuntu status lookup budget exceeded",
        "Supplementary Ubuntu status exceeded its bounded lookup capacity.",
        "The platform operator must inspect source expansion; no partial device check was published.",
    ),
    "advisory_limit": (
        "Device advisory evaluation budget exceeded",
        "The host requires more than 30,000 vendor definitions, exceeding the evaluator's safety limit.",
        "The platform operator must inspect the feed scope and evaluation capacity; restarting the Linux client will not change this limit.",
    ),
    "evaluation_timeout": (
        "Device evaluation time budget exceeded",
        "Local vendor-rule evaluation exceeded its 120-second time limit.",
        "The platform operator must inspect evaluator/database performance and rule volume before retrying.",
    ),
    "match_limit": (
        "Device CVE result budget exceeded; no partial evaluation published",
        "The host produced more than 10,000 package/definition/CVE matches, exceeding the publication safety limit.",
        "The platform operator must inspect match volume and publication capacity. These are match records, not 10,000 confirmed vulnerabilities; restarting the Linux client will not change this limit.",
    ),
    "publication_timeout": (
        "Device publication time budget exceeded",
        "Evaluation and database publication exceeded their shared 120-second time limit.",
        "The platform operator must inspect publication/database performance and result volume before retrying.",
    ),
    "proof_limit": (
        "Package proof budget exceeded; no partial checks published",
        "The host exceeded the 100,000 package/definition proof limit.",
        "The platform operator must inspect vendor-rule expansion and evaluation capacity before retrying.",
    ),
    "result_limit": (
        "Package result budget exceeded; no partial checks published",
        "The host exceeded the 100,000 package/CVE result limit.",
        "The platform operator must inspect vendor-rule expansion and evaluation capacity before retrying.",
    ),
    "identity_limit": (
        "Definition source identity too long",
        "A vendor definition's source identity exceeded the supported length.",
        "The platform operator must inspect the vendor definition and source-identity handling before retrying.",
    ),
}


def diagnostic(code):
    row = CAUSES.get(code) if isinstance(code, str) else None
    if row:
        return {"error_code": code, "message": row[1], "next_action": row[2]}
    return {}


def failure(exc):
    if isinstance(exc, ConnectorError):
        for code, row in CAUSES.items():
            if str(exc) == row[0]:
                return diagnostic(code)
    # Keep the legacy safe class label for existing consumers; no exception values.
    kind = type(exc).__name__
    kind = (
        kind
        if kind
        in {"ConnectorError", "ValueError", "TypeError", "KeyError", "AttributeError", "InvalidVersion"}
        else "UnclassifiedError"
    )
    return {
        "error_code": "unclassified",
        "message": f"Evaluation deferred ({kind}); retained evidence needs review.",
        "next_action": "No classified cause was recorded. The platform operator must inspect evaluator diagnostics before retrying; do not infer a network outage from an exception class.",
    }
