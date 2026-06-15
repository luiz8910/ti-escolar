"""Adaptador mock de ``DocumentSource``.

Simula a integração com sistemas externos (acadêmico, drive). Substituível por um adaptador
real sem tocar em domínio/aplicação.
"""

from __future__ import annotations

import uuid

from app.domain.entities import Documento

# Mapa simples consulta -> categoria de documento.
_CATEGORIAS = {
    "boletim": ("Boletim do 1º bimestre", "boletim"),
    "declaraç": ("Declaração de matrícula", "declaracao"),
    "histórico": ("Histórico escolar", "historico"),
    "historico": ("Histórico escolar", "historico"),
    "comprovante": ("Comprovante de matrícula", "comprovante"),
    "documento": ("Documentos disponíveis", "geral"),
}


class MockDocumentSource:
    async def buscar_documentos(
        self, *, tenant_id: uuid.UUID, contato: str, consulta: str
    ) -> list[Documento]:
        consulta_low = consulta.lower()
        encontrados: list[Documento] = []
        for chave, (nome, categoria) in _CATEGORIAS.items():
            if chave in consulta_low:
                encontrados.append(
                    Documento(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        nome=f"{nome}.pdf",
                        categoria=categoria,
                        url=f"https://exemplo.test/docs/{categoria}/{contato}.pdf",
                    )
                )
        # Evita duplicar a categoria "geral" quando algo específico já casou.
        especificos = [d for d in encontrados if d.categoria != "geral"]
        return especificos or encontrados
