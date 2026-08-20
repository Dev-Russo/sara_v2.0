"""Agente do fluxo de tarefas."""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import UTC, date, datetime, timedelta
from json import JSONDecodeError
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from app.integrations.llm.interface import LLMClient
from app.schemas.commands import TasksCreateCommand, TasksListCommand
from app.schemas.decisions import AgentDecision
from app.schemas.events import ExecutionContext, MessageEvent

TASK_AGENT_SYSTEM_PROMPT = """
Você é o TaskAgent da SARA. Interprete a mensagem do usuário e retorne somente um
objeto JSON compatível com o contrato AgentDecision.

Regras:
- Você pode conversar ou propor um comando, mas nunca executa comandos.
- Os comandos implementados nesta etapa são tasks.create, tasks.list, tasks.complete e tasks.update.
- tasks.create exige um título não vazio.
- tasks.list aceita status active, completed, archived ou null, além de due_date_from e
  due_date_to.
- Se o usuário pedir uma lista sem filtro de status, use active (tarefas pendentes).
- Se pedir "todas", use status null explicitamente.
- Para editar uma tarefa, use tasks.update com query contendo os termos relevantes da tarefa;
  o Harness resolverá o candidato. O payload pode alterar somente title, description ou priority.
- Não use tasks.update para datas ou horários; alterações de agenda pertencem ao rescheduler.
- Para concluir por descrição, use tasks.complete com query contendo os termos relevantes;
  o Harness fará obrigatoriamente a busca em tarefas active antes de concluir.
- Para expressões como "essa semana", use a data de referência fornecida na mensagem.
- priority é sempre 0 ou 1; em tasks.create, se o usuário não indicar prioridade, use 0.
  Em tasks.update, omita priority quando ele não for alterado.
- Se a criação não informar due_date, mantenha due_date null; o caso de uso aplica a data de hoje.
- Nunca inclua user_id no payload; essa informação vem do contexto confiável.
- Não invente datas ou horários ausentes.
- Se faltarem dados, retorne message e command null.

O campo command.type deve ser "tasks.create", "tasks.list", "tasks.complete" ou "tasks.update";
o payload deve corresponder ao tipo escolhido. Exemplo de tasks.create:
{
  "message": "string ou null",
  "command": {
    "type": "tasks.create",
    "payload": {
      "...": "payload correspondente ao tipo do comando"
    }
  },
  "transition": null,
  "metadata": {}
}

Para tasks.create, o payload contém title, description, priority, due_date, start_at e
end_at. Para tasks.list, contém status, due_date_from e due_date_to. Para tasks.complete,
contém query; query pode ser null quando não houver referência suficiente.
Para tasks.update, contém query e pelo menos um campo a alterar entre title, description e priority.
""".strip()


class TaskAgent:
    def __init__(self, llm: LLMClient, *, timezone: str = "America/Sao_Paulo") -> None:
        self._llm = llm
        self._timezone = ZoneInfo(timezone)

    async def decide(self, event: MessageEvent, context: ExecutionContext) -> AgentDecision:
        del context
        today = self._local_date(event.received_at)
        reference_date = today.isoformat()
        raw_decision = await self._llm.complete(
            system_prompt=TASK_AGENT_SYSTEM_PROMPT,
            user_message=f"Data de referência: {reference_date}\nMensagem: {event.text}",
        )
        try:
            decision = AgentDecision.model_validate(self._parse_json(raw_decision))
            return self._normalize_relative_dates(decision, event.text, today)
        except (JSONDecodeError, ValidationError, TypeError):
            return AgentDecision(
                message="Não consegui interpretar essa solicitação.",
                metadata={"error_code": "AGENT_OUTPUT_INVALID"},
            )

    def _local_date(self, timestamp: datetime) -> date:
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        return timestamp.astimezone(self._timezone).date()

    @staticmethod
    def _normalize_relative_text(text: str) -> str:
        normalized = unicodedata.normalize("NFKD", text.casefold())
        return normalized.encode("ascii", "ignore").decode("ascii")

    def _normalize_relative_dates(
        self,
        decision: AgentDecision,
        text: str,
        today: date,
    ) -> AgentDecision:
        normalized_text = self._normalize_relative_text(text)
        if re.search(r"\bhoje\b", normalized_text):
            target_date = today
        elif re.search(r"\bamanha\b", normalized_text):
            target_date = today + timedelta(days=1)
        elif re.search(r"\bontem\b", normalized_text):
            target_date = today - timedelta(days=1)
        elif re.search(r"\bessa semana\b", normalized_text):
            target_date = today + timedelta(days=(6 - today.weekday()))
        elif re.search(r"\bproxima semana\b", normalized_text):
            target_date = today + timedelta(days=(13 - today.weekday()))
        else:
            return decision

        command = decision.command
        if isinstance(command, TasksListCommand):
            payload = command.payload.model_copy(
                update={"due_date_from": target_date, "due_date_to": target_date},
            )
        elif isinstance(command, TasksCreateCommand):
            payload = command.payload.model_copy(update={"due_date": target_date})
        else:
            return decision

        normalized_command = command.model_copy(update={"payload": payload})
        return decision.model_copy(update={"command": normalized_command})

    @staticmethod
    def _parse_json(raw: str) -> object:
        candidate = raw.strip()
        if candidate.startswith("```"):
            lines = candidate.splitlines()
            lines = lines[1:] if lines and lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].strip() == "```" else lines
            candidate = "\n".join(lines).strip()
        return json.loads(candidate)
