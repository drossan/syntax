# Session log — backend-agent-graph-02

## 2026-08-27
- Verificado antes de implementar: `RankedHit.hit.score` (similitud cruda) vs `weighted_score`
  (`app/rag/reranker.py:35-42`) — la spec pide el crudo para no contar el peso de `estado` dos veces.
- Red: `tests/test_confidence.py` (5 tests, 1 parametrizado) — `ImportError` de colección confirmado
  (`compute_confidence` no existía).
- Green: `app/rag/confidence.py::compute_confidence` — veto de `grade_suficiente`, guarda para
  `retrieved=[]` (evita `ValueError` de `max()` sobre vacío), `max(hit.score)` puro sin I/O.
- Verificación: `pytest tests/test_confidence.py` → 5 passed. Suite completa `pytest -q` → exit 0.
  `ruff check` + `mypy --strict` limpios; `ruff format` corrigió una línea larga en el test, reverificado.
- Gate mutation (`cosmic-ray`, `module-path=app/rag/confidence.py`): 0.00% survivors.
- `/sdd-lint`: N/A — sin CU propio (función pura interna, declarado en la tarea); referencia a ADR-0009
  verificada (`.claude/specs/adr/0009-confianza-hibrida-y-auto-approve-por-tenant.md` existe).
- `fact-checker`: 10/10 VERIFICADO, 0 INCORRECTO.

## Cierre
- DoD completa. Tarea movida a `completed/`, `status: done`, `[x]` en el plan.
- Ficheros tocados: `backend/app/rag/confidence.py`, `backend/tests/test_confidence.py` (nuevo), `backend/cosmic-ray.toml`.
- Follow-ups: ninguno. Sigue la tarea 03 (`app/rag/citations.py`).
