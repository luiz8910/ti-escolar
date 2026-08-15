"""Retomada de disparos interrompidos pela cota diária (§9a-quinquies).

O teto da Meta é de **destinatários únicos por 24h** e hoje vale **250 no portfólio
inteiro** (§9e.3). Uma escola de 600 responsáveis não cabe num dia — e o produto já sabia
disso: ``EnviarBroadcast`` conta os excedentes em ``bloqueados_por_limite``, deixa os
destinatários em ``PENDENTE`` e marca o broadcast como ``PARCIAL_LIMITE``.

**O que faltava era alguém voltar no dia seguinte.** Sem isso, "espera a próxima janela"
significava, na prática, alguém lembrar de re-disparar à mão — e o aviso da reunião chegava
a metade da escola. Enquanto o teto era teoricamente 1000 dava para adiar; com 250 real,
virou requisito para o disparo funcionar como vendido.

A retomada é barata porque ``EnviarBroadcast`` **já é idempotente por destinatário**: ele
pula quem está em ``ENVIADO``/``ENTREGUE``/``LIDO``. Reexecutar o mesmo broadcast continua
de onde parou, sem reenviar para ninguém.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.application.use_cases import EnviarBroadcast
from app.domain.ports import BroadcastRepository

logger = logging.getLogger("broadcast.retomada")


@dataclass(frozen=True)
class ResultadoRetomada:
    broadcasts: int  # quantos foram retomados nesta passada
    enviados: int
    falhas: int
    ainda_bloqueados: int  # continuam esperando a próxima janela


class RetomarBroadcastsPendentes:
    """Continua os disparos que a cota diária interrompeu.

    ``janela_dias`` é um **prazo de validade**, não uma otimização: um aviso de três semanas
    atrás entregue hoje é pior do que não entregue — a reunião já passou, e o responsável
    recebe da escola uma mensagem que não faz sentido. Passado o prazo, o disparo é
    abandonado onde está (o histórico continua mostrando quem recebeu e quem não).
    """

    def __init__(
        self,
        *,
        broadcasts: BroadcastRepository,
        enviar: EnviarBroadcast,
        janela_dias: int = 7,
    ) -> None:
        self._broadcasts = broadcasts
        self._enviar = enviar
        self._janela_dias = janela_dias

    async def executar(self) -> ResultadoRetomada:
        desde = datetime.now(timezone.utc) - timedelta(days=self._janela_dias)
        pendentes = await self._broadcasts.listar_retomaveis(desde=desde)
        if not pendentes:
            return ResultadoRetomada(0, 0, 0, 0)

        retomados = enviados = falhas = bloqueados = 0
        # Escolas cuja cota acabou nesta passada. A cota é **por escola**, então parar a
        # fila inteira faria uma escola grande travar o aviso das outras — mas insistir na
        # mesma depois de ela estourar é percorrer destinatários só para contar zeros.
        sem_cota: set = set()
        for broadcast in pendentes:
            if broadcast.tenant_id in sem_cota:
                continue
            try:
                resultado = await self._enviar.executar(broadcast=broadcast)
            except Exception as exc:  # noqa: BLE001 — um disparo ruim não trava a fila
                # Template desmentido, escola bloqueada, conta sem id: causas que impedem
                # **este** broadcast e não têm relação com os outros da fila.
                logger.warning(
                    "Não foi possível retomar o broadcast %s: %s", broadcast.id, exc
                )
                continue
            retomados += 1
            enviados += resultado.enviados
            falhas += resultado.falhas
            bloqueados += resultado.bloqueados_por_limite
            if resultado.bloqueados_por_limite:
                sem_cota.add(broadcast.tenant_id)
                logger.info(
                    "Cota diária esgotada durante a retomada; %d destinatário(s) seguem "
                    "esperando no broadcast %s",
                    resultado.bloqueados_por_limite,
                    broadcast.id,
                )

        if retomados:
            logger.info(
                "Retomada de disparos: %d broadcast(s), %d enviado(s), %d falha(s), "
                "%d ainda bloqueado(s) pela cota",
                retomados,
                enviados,
                falhas,
                bloqueados,
            )
        return ResultadoRetomada(
            broadcasts=retomados,
            enviados=enviados,
            falhas=falhas,
            ainda_bloqueados=bloqueados,
        )
