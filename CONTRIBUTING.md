# Contribuindo

Obrigado pelo interesse em contribuir com o **Extrator de Dados CRLV**.

## Ambiente de desenvolvimento

Requisitos: Python 3.11+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

## Testes

```bash
uv run python -m unittest discover -s tests -v
```

Os testes usam um CRLV sintético gerado em tempo de execução. PDFs reais são
ignorados pelo Git por conterem dados pessoais.

**Não versione PDFs de CRLV reais.** Se precisar adicionar uma fixture,
gere um documento sintético com dados fictícios em `tests/fixtures/` ou
diretamente no teste.

## Lint e formatação

```bash
uv run ruff check .
uv run ruff format --check .
```

Para aplicar a formatação:

```bash
uv run ruff format .
```

## Notebook

```bash
uv run --group notebooks jupyter lab
```

## Pull requests

- Mantenha o foco da mudança e atualize os testes quando necessário.
- Rode testes e lint antes de abrir o PR.
- Descreva o problema e a solução no PR.
- Não inclua dados pessoais, documentos reais ou credenciais.

## Licença

Ao contribuir, você concorda que sua contribuição será distribuída sob a
licença MIT deste projeto.
