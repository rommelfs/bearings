"""Versioned, database-generated selection of queue facts from retained proofs.

V1 is migration-owned: keep its paths/semantics stable. Add a new expression and
migration if the proof contract changes. No application-maintained cache is used.
"""

import json
from django.db import NotSupportedError
from django.db.models import Func, JSONField


class ComparableJSON(Func):
    """SQLite JSON equality needs compact JSON text on both sides of an expression."""

    arity = 1
    output_field = JSONField()

    def as_sql(self, compiler, connection, **extra_context):
        return compiler.compile(self.source_expressions[0])

    def as_sqlite(self, compiler, connection, **extra_context):
        sql, params = compiler.compile(self.source_expressions[0])
        return f"JSON({sql})", params


class DistroQueueProofV1(Func):
    arity = 1
    output_field = JSONField()
    paths = (
        ("evaluator_version", ("evaluator_version",)),
        ("version", ("version",)),
        ("package", ("package",)),
        ("source_package", ("source_package",)),
        ("os", ("os",)),
        ("inventory_sequence", ("inventory_sequence",)),
        ("feed", ("feed",)),
        ("rule_sha256", ("rule_sha256",)),
        ("schema", ("package_check", "schema")),
        ("verdict", ("package_check", "verdict")),
        ("ubuntu_cve", ("package_check", "ubuntu_status", "cve")),
        ("ubuntu_hash", ("package_check", "ubuntu_status", "sha256")),
    )

    def as_postgresql(self, compiler, connection, **extra_context):
        source, source_params = compiler.compile(self.source_expressions[0])
        parts, params = [], []
        for key, path in self.paths:
            # jsonb_build_object(any...) is STABLE, not IMMUTABLE in PostgreSQL.
            # JSONB extraction/output and text concatenation are immutable for
            # these already-JSONB inputs, so are valid for a stored column.
            parts.append(f"%s || COALESCE(({source} #> %s)::text, 'null')")
            params.extend([json.dumps(key) + ":", *source_params, list(path)])
        parts.append(f"%s || CASE WHEN ({source} #> %s) IS NULL THEN 'true' ELSE 'false' END")
        params.extend(['"ubuntu_missing":', *source_params, ["package_check", "ubuntu_status"]])
        return "('{' || " + " || ',' || ".join(parts) + " || '}')::jsonb", params

    def as_sqlite(self, compiler, connection, **extra_context):
        source, source_params = compiler.compile(self.source_expressions[0])
        parts, params = [], []
        for key, path in self.paths:
            # JSON_EXTRACT alone turns JSON booleans into SQL integers. Preserve
            # their type, as well as object/array subtypes and ordinary strings.
            parts.append(
                f"%s, CASE JSON_TYPE({source}, %s) "
                "WHEN 'true' THEN JSON('true') WHEN 'false' THEN JSON('false') "
                f"ELSE JSON_EXTRACT({source}, %s) END"
            )
            json_path = "$." + ".".join(path)
            params.extend([key, *source_params, json_path, *source_params, json_path])
        parts.append(f"%s, JSON(CASE WHEN JSON_TYPE({source}, %s) IS NULL THEN 'true' ELSE 'false' END)")
        params.extend(["ubuntu_missing", *source_params, "$.package_check.ubuntu_status"])
        return "JSON_OBJECT(" + ", ".join(parts) + ")", params

    def as_sql(self, compiler, connection, **extra_context):
        raise NotSupportedError("Distribution queue proofs require PostgreSQL or SQLite")


class DistroVendorFixInputsV1(Func):
    """Compact the exact JSON paths used to confirm documented vendor fixes."""

    arity = 1
    output_field = JSONField()

    def as_postgresql(self, compiler, connection, **extra_context):
        source, params = compiler.compile(self.source_expressions[0])
        sql = f"""jsonb_set('{{}}'::jsonb, '{{package_check}}', jsonb_set(
            jsonb_set('{{}}'::jsonb, '{{comparisons}}',
                      COALESCE({source} #> '{{package_check,comparisons}}', 'null'::jsonb)),
            '{{vendor_comments}}',
            COALESCE({source} #> '{{package_check,vendor_comments}}', 'null'::jsonb)))"""
        return sql, [*params, *params]

    def as_sqlite(self, compiler, connection, **extra_context):
        source, params = compiler.compile(self.source_expressions[0])
        sql = f"""JSON_OBJECT('package_check', JSON_OBJECT(
            'comparisons', JSON_EXTRACT({source}, '$.package_check.comparisons'),
            'vendor_comments', JSON_EXTRACT({source}, '$.package_check.vendor_comments')))"""
        return sql, [*params, *params]

    def as_sql(self, compiler, connection, **extra_context):
        raise NotSupportedError("Distribution vendor fix inputs require PostgreSQL or SQLite")
