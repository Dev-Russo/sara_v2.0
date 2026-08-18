"""Agente do fluxo de tarefas."""

from __future__ import annotations

import json
from json import JSONDecodeError

from pydantic import ValidationError

from app.integrations.llm.interface import LLMClient
from app.schemas.decisions import AgentDecision
from app.schemas.events import ExecutionContext, MessageEvent

TASK_AGENT_SYSTEM_PROMPT = """
Você é o TaskAgent da SARA. Interprete a mensagem do usuário e retorne somente um
objeto JSON compatível com o contrato AgentDecision.

Regras:
- Você pode conversar ou propor um comando, mas nunca executa comandos.
- O único comando implementado nesta etapa é tasks.create.
- tasks.create exige um título não vazio.
- priority é sempre 0 ou 1; se o usuário não indicar prioridade, use 0.
- Nunca inclua user_id no payload; essa informação vem do contexto confiável.
- Não invente datas ou horários ausentes.
- Se faltarem dados, retorne message e command null.

Formato:
{
  "message": "string ou null",
  "command": {
    "type": "tasks.create",
    "payload": {
      "title": "string",
      "description": "string ou null",
      "priority": 0,
      "due_date": "YYYY-MM-DD ou null",
      "start_at": "ISO-8601 ou null",
      "end_at": "ISO-8601 ou null"
    }
  },
  "transition": null,
  "metadata": {}
}
""".strip()


class TaskAgent:
    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def decide(self, event: MessageEvent, context: ExecutionContext) -> AgentDecision:
        del context
        raw_decision = await self._llm.complete(
            system_prompt=TASK_AGENT_SYSTEM_PROMPT,
            user_message=event.text,
        )
        try:
            return AgentDecision.model_validate(self._parse_json(raw_decision))
        except (JSONDecodeError, ValidationError, TypeError):
            return AgentDecision(
                message="Não consegui interpretar essa solicitação.",
                metadata={"error_code": "AGENT_OUTPUT_INVALID"},
            )

    @staticmethod
    def _parse_json(raw: str) -> object:
        candidate = raw.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            lines = lines[1:] if lines and lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
            candidate = "\n".join(lines).strip()
        return json.loads(candidate)
