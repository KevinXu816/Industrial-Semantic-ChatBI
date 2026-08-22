import pytest
from app.guardrail import SQLGuardrail


def test_guardrail_accepts_cte_select():
    SQLGuardrail().validate("WITH x AS (SELECT 1 AS v) SELECT v FROM x")


def test_guardrail_rejects_multi_statement():
    with pytest.raises(ValueError):
        SQLGuardrail().validate("SELECT 1; DROP TABLE x")
