"""A fiação do storage: nenhuma rota escolhe o adaptador na mão.

Existe por um furo real, achado na revisão do PR que ligaria o S3 em produção. O
``ARQUIVO_STORAGE`` passou a ser lido por ``criar_arquivo_storage``, mas quatro rotas
seguiam instanciando ``PostgresArquivoStorage(session)`` direto:

- ``GET /api/admin/impressao/{id}/arquivo`` — o professor manda o arquivo pelo WhatsApp e
  ele vai para o bucket, mas o download lia o ``bytea``. Com ``ARQUIVO_STORAGE=s3`` a
  secretaria veria o pedido na fila e receberia **404** ao tentar imprimir.
- as três rotas da foto do aluno — coerentes entre si, então sem 404, mas a foto nunca
  chegava ao S3: seguia inflando o banco cobrado por GB e fora do lifecycle do bucket.

Nenhum teste pegou isso porque a suíte exercita os **casos de uso** com fakes, e o defeito
estava na borda HTTP, onde se decide qual adaptador entra. Daí este arquivo, que olha o
código das interfaces em vez de rodá-lo: a regra é "quem precisa de storage, pede à
fábrica" (§4 — dependências apontam para dentro, adaptador se escolhe num lugar só).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

INTERFACES = Path(__file__).resolve().parents[1] / "app" / "interfaces"

# Adaptadores concretos: só a fábrica (`app/infrastructure/factories.py`) pode construí-los.
ADAPTADORES = {"PostgresArquivoStorage", "S3ArquivoStorage", "ArquivoStorageMemoria"}


def _modulos() -> list[Path]:
    return sorted(INTERFACES.rglob("*.py"))


def _instanciacoes(caminho: Path) -> list[tuple[str, int]]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    achados: list[tuple[str, int]] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name):
            if no.func.id in ADAPTADORES:
                achados.append((no.func.id, no.lineno))
    return achados


@pytest.mark.parametrize("modulo", _modulos(), ids=lambda p: p.name)
def test_interface_nao_instancia_adaptador_de_storage(modulo: Path):
    """A borda HTTP pede o storage por ``Depends(get_arquivo_storage)``, nunca na mão."""
    achados = _instanciacoes(modulo)
    assert not achados, (
        f"{modulo.name} instancia {achados} direto. Use "
        "`storage: ArquivoStorage = Depends(get_arquivo_storage)` — adaptador na mão "
        "ignora ARQUIVO_STORAGE e volta a quebrar o download quando o S3 estiver ligado."
    )


def test_as_rotas_de_arquivo_dependem_da_fabrica():
    """O caminho positivo: quem serve bytes declara a dependência da fábrica.

    Sem isto, apagar a rota passaria no teste acima por vacuidade.
    """
    from app.interfaces.api import cadastro, impressao
    from app.interfaces.deps import get_arquivo_storage

    # Olha os routers, e não ``app.routes``: desde o FastAPI 0.135 o ``include_router``
    # guarda um ``_IncludedRouter`` e as rotas só existem depois que o app é montado —
    # procurá-las ali passaria por vacuidade.
    esperadas = {
        ("/api/admin/impressao/{solicitacao_id}/arquivo", "GET"),
        ("/api/admin/alunos/{aluno_id}/foto", "PUT"),
        ("/api/admin/alunos/{aluno_id}/foto", "GET"),
        ("/api/admin/alunos/{aluno_id}/foto", "DELETE"),
    }
    vistas: set[tuple[str, str]] = set()
    for modulo in (impressao, cadastro):
        for rota in modulo.router.routes:
            for metodo in getattr(rota, "methods", set()):
                chave = (getattr(rota, "path", ""), metodo)
                if chave not in esperadas:
                    continue
                dependencias = [d.call for d in rota.dependant.dependencies]
                assert get_arquivo_storage in dependencias, (
                    f"{chave} não pede o storage à fábrica"
                )
                vistas.add(chave)
    assert vistas == esperadas, f"rotas de arquivo não encontradas: {esperadas - vistas}"
