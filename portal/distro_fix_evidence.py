"""SQL predicate for explicit vendor fix evidence."""

from django.db.models import BooleanField, Func


class HasVendorFix(Func):
    """Same explicit fixed-note/strict satisfied-bound contract as update_context.

    Evaluate in the database before counts, filtering and pagination; never fetch
    every retained proof or infer an installable repository candidate.
    """

    arity = 1
    output_field = BooleanField()

    def as_postgresql(self, compiler, connection, **extra):
        source, params = compiler.compile(self.source_expressions[0])

        def array(path):
            return f"CASE WHEN jsonb_typeof({source} #> '{{package_check,{path}}}') = 'array' THEN {source} #> '{{package_check,{path}}}' ELSE '[]'::jsonb END"

        sql = f"""EXISTS(SELECT 1 FROM jsonb_array_elements({array("comparisons")}) hc(value),
            jsonb_array_elements({array("vendor_comments")}) hn(value)
            WHERE jsonb_typeof(hc.value->'vendor_version')='string'
            AND hc.value->>'vendor_version' <> ''
            AND hc.value->>'operation'='less than' AND hc.value->'matches'='true'::jsonb
            AND jsonb_typeof(hn.value)='string'
            AND strpos(hn.value #>> '{{}}', %s || (hc.value->>'vendor_version') || %s)>0)"""
        return sql, [*params, *params, *params, *params, "has been fixed (note: '", "')"]

    def as_sqlite(self, compiler, connection, **extra):
        source, params = compiler.compile(self.source_expressions[0])

        def array(path):
            return f"CASE WHEN json_type({source}, '$.package_check.{path}')='array' THEN json_extract({source}, '$.package_check.{path}') ELSE '[]' END"

        comparison = "CASE WHEN hc.type='object' THEN hc.value ELSE '{}' END"
        sql = f"""EXISTS(SELECT 1 FROM json_each({array("comparisons")}) hc,
            json_each({array("vendor_comments")}) hn
            WHERE json_type({comparison}, '$.vendor_version')='text'
            AND json_extract({comparison}, '$.vendor_version') <> ''
            AND json_extract({comparison}, '$.operation')='less than'
            AND json_type({comparison}, '$.matches')='true' AND hn.type='text'
            AND instr(hn.value, %s || json_extract({comparison}, '$.vendor_version') || %s)>0)"""
        return sql, [*params, *params, *params, *params, "has been fixed (note: '", "')"]
