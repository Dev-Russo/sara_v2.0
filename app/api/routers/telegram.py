"""Entrada do webhook Telegram; o processamento será encaminhado ao Graph."""

from fastapi import APIRouter, Header, HTTPException, Request, status

from app.config import Settings

router = APIRouter(tags=["telegram"])


@router.post("/telegram", status_code=status.HTTP_202_ACCEPTED)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Valida o segredo do webhook e reserva o seam de entrada do Graph."""

    settings: Settings = request.app.state.settings
    expected_secret = settings.telegram_webhook_secret
    if expected_secret and x_telegram_bot_api_secret_token != expected_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid webhook secret")

    # O corpo ainda não é interpretado nesta fundação. O adapter deve produzir um evento
    # interno e entregá-lo ao Graph, sem deixar tipos do Telegram vazarem para o domínio.
    return {"accepted": False}

