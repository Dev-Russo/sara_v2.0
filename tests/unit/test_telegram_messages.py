from uuid import uuid4

from app.integrations.telegram.messages import build_outgoing_message
from app.schemas.results import HarnessResult, ResponseDecision


def test_build_outgoing_message_adds_confirmation_keyboard_from_harness_result() -> None:
    confirmation_id = uuid4()
    message = build_outgoing_message(
        response=ResponseDecision(message="Confirma a exclusão?"),
        harness_result=HarnessResult(
            status="awaiting_confirmation",
            command_id=uuid4(),
            command_type="tasks.delete",
            confirmation_id=confirmation_id,
        ),
    )

    assert message.text == "Confirma a exclusão?"
    assert message.reply_markup == {
        "inline_keyboard": [
            [
                {
                    "text": "Confirmar",
                    "callback_data": f"confirmation:confirm:{confirmation_id}",
                },
                {
                    "text": "Cancelar",
                    "callback_data": f"confirmation:cancel:{confirmation_id}",
                },
            ],
        ],
    }


def test_build_outgoing_message_does_not_add_keyboard_to_regular_response() -> None:
    message = build_outgoing_message(
        response=ResponseDecision(message="Tarefa criada."),
        harness_result=HarnessResult(
            status="executed",
            command_id=uuid4(),
            command_type="tasks.create",
        ),
    )

    assert message.text == "Tarefa criada."
    assert message.reply_markup is None
