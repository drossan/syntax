"""app.domain.services.approval_service — aprobación humana (HITL) de drafts IA.

GUIÓN (→ tarea 10; integra con el HITL del grafo, 16)
-----------------------------------------------------
Qué implementar (sobre ``ApprovalRepository`` + ``TicketRepository`` + ``MessageRepository``):
  - **Cola**: listar ``ApprovalTask`` pendientes (orden `sla_due, confidence` — 06); solo sujetos con
    ``approval.decide`` (Grippo/Soporte, 02).
  - **``auto_approve`` por tenant** (default **false**): si false, todo draft crea una ``ApprovalTask``
    pendiente (el grafo hace ``interrupt``, 05/16); si true, se auto-materializa (riesgo prompt-injection).
  - **Decidir** (idempotente — 03/06):
      - ``approve`` → reanuda el grafo (``resume``); **materializa ``Message(visibility=public,
        is_ai_draft=True, author=IA/agente)``** + transición del ticket (via ``ticket_service``). [A1.1]
      - ``edit``   → igual pero con ``final_body`` editado.
      - ``reject`` → reanuda sin emitir mensaje público; ``human_note`` obligatorio; ``AgentRun`` superado.
    Decidir una tarea ya no-``pending`` = **no-op**; en carrera, la 2ª decisión → 409 (una sola vez el
    ``resume`` sobre el thread; ver 05/16).
  - **Límite de ai-draft** (B.1): política de tope por ticket/tenant (aplicada por 12).

Anti-patrón: emitir el mensaje público sin pasar por la decisión humana cuando ``auto_approve=false``;
reanudar el grafo dos veces; olvidar la transición del ticket tras aprobar.
"""
