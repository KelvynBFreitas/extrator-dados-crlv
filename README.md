# Extrator de Dados CRLV

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Biblioteca Python para extrair **placa**, **chassi** e outros dados de um
**CRLV-e** (Certificado de Registro e Licenciamento de Veículo) em PDF.

Não usa OCR: funciona em PDFs que possuem camada de texto.

O pacote é importado como `extrator_dados_crlv` e o comando de linha de
comando instalado é `extrator-crlv`.

## Instalação

A partir do código-fonte:

```bash
pip install .
```

Ou, em um projeto gerenciado pelo `uv`:

```bash
uv add "/caminho/para/extrator-dados-crlv"
```

Também é possível instalar direto do GitHub:

```bash
pip install "git+https://github.com/KelvynBFreitas/extrator-dados-crlv.git"
```

Requisitos: **Python 3.11+** e **PyMuPDF**.

## Uso como biblioteca

```python
from extrator_dados_crlv import extrair_dados

dados = extrair_dados("crlv.pdf")

if not dados.completo:
    raise ValueError("Placa ou chassi não encontrados")

print(dados.placa)       # ABC1D23
print(dados.chassi)      # 9BRK3AAG9P0000000
print(dados.para_dict()) # dicionário com todos os campos
```

### Entradas suportadas

| Entrada | Como chamar |
| --- | --- |
| Arquivo (`str` ou `Path`) | `extrair_dados("crlv.pdf")` |
| Bytes do PDF | `extrair_dados_bytes(pdf_bytes)` |
| Base64 | `extrair_dados_base64(conteudo_b64)` |
| Base64 com flag | `extrair_dados(conteudo_b64, base64=True)` |
| Data URI | `extrair_dados_base64("data:application/pdf;base64,...")` |

A leitura por base64 aceita base64 padrão e URL-safe, com ou sem quebras de
linha, com ou sem o preenchimento `=` final e data URIs completas.

```python
from pathlib import Path

from extrator_dados_crlv import (
    extrair_dados,
    extrair_dados_base64,
    extrair_dados_bytes,
)

# Arquivo
dados = extrair_dados(Path("crlv.pdf"))

# Bytes (upload, banco, fila etc.)
dados = extrair_dados_bytes(conteudo_pdf)

# Base64 (API, banco etc.)
dados = extrair_dados_base64(conteudo_base64)

# Ou usando a API unificada
dados = extrair_dados(conteudo_base64, base64=True)
```

### Retorno

`extrair_dados*` retorna um `DadosVeiculo` imutável com os campos:

`arquivo`, `placa`, `chassi`, `renavam`, `numero_crv`, `exercicio`,
`marca_modelo`, `ano_fabricacao`, `ano_modelo`, `cor`, `combustivel`,
`categoria`, `especie_tipo`, `local`, `proprietario` e `cpf_cnpj`.

Campos não encontrados ficam como `None`. O campo `arquivo` contém o caminho
informado ou os marcadores `<bytes>` / `<base64>`, conforme a entrada. Use:

- `dados.completo`: `True` quando placa e chassi foram encontrados;
- `dados.para_dict()`: retorna um dicionário serializável.

### Exceções

| Exceção | Quando ocorre |
| --- | --- |
| `ErroCRLV` | Classe base de todos os erros da biblioteca |
| `CRLVInvalidoError` | PDF inválido ou conteúdo que não pôde ser lido |
| `CRLVProtegidoError` | PDF protegido por senha |
| `CRLVSemTextoError` | PDF sem camada de texto (digitalizado) |
| `Base64InvalidoError` | Base64 inválido ou que não representa um PDF |
| `FileNotFoundError` | Caminho de arquivo inexistente |
| `IsADirectoryError` | O caminho informado não é um arquivo |
| `TypeError` | Tipo de entrada incompatível |

`CRLVInvalidoError` herda de `ValueError`, então integrações que já capturam
`ValueError` continuam funcionando.

```python
from extrator_dados_crlv import ErroCRLV, extrair_dados

try:
    dados = extrair_dados(payload["crv_base64"], base64=True)

    if not dados.completo:
        raise ValueError("Placa ou chassi não encontrados no CRLV")

    # usar dados.placa / dados.chassi
except ErroCRLV as erro:
    # PDF inválido, base64 inválido, PDF protegido ou sem texto
    print(f"Falha ao ler CRLV: {erro}")
except OSError as erro:
    # arquivo inexistente, sem permissão etc.
    print(f"Falha ao acessar o arquivo: {erro}")
```

## CLI (opcional)

O pacote também instala o comando `extrator-crlv`:

```bash
extrator-crlv "crlv.pdf"
extrator-crlv --json "crlv.pdf"
extrator-crlv --base64 "JVBERi0xLjQK..." --json
extrator-crlv --base64-arquivo crlv_base64.txt --json
```

No Windows, para ler o base64 da entrada padrão:

```powershell
Get-Content crlv_base64.txt -Raw | extrator-crlv --base64 - --json
```

Também é possível executar sem instalar o comando:

```bash
python -m extrator_dados_crlv "crlv.pdf"
```

## Como funciona

O PDF do CRLV não mantém o texto na ordem visual: primeiro vêm os rótulos e
depois os valores. Por isso o extrator:

1. Lê cada linha do PDF com suas coordenadas usando PyMuPDF.
2. Localiza o rótulo (`PLACA`, `CHASSI` etc.).
3. Escolhe o valor logo abaixo, na mesma coluna.
4. Valida placa (padrão antigo e Mercosul) e chassi (17 caracteres VIN).
5. Se o layout fugir do esperado, procura os padrões no documento inteiro.

## Desenvolvimento

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
```

Os testes principais usam um CRLV **sintético**, gerado em tempo de execução,
para não versionar documentos reais. PDFs reais são ignorados pelo Git.

O notebook `testar_crlv.ipynb` permite testar a extração manualmente:

```bash
uv run --group notebooks jupyter lab
```

## Contribuindo

Veja [CONTRIBUTING.md](CONTRIBUTING.md) para configurar o ambiente, rodar os
testes e abrir pull requests.

## Licença

Distribuído sob a licença [MIT](LICENSE).

## Limitações e segurança

- PDFs digitalizados (imagem) precisam de OCR antes da extração.
- PDFs protegidos por senha não são suportados.
- Layouts muito diferentes do CRLV padrão podem exigir ajuste nos rótulos.
- A biblioteca apenas extrai texto; **não valida assinatura digital, QR Code,
  autenticidade ou situação do veículo** no DETRAN/SENATRAN.
- PDFs são entradas não confiáveis. Se a leitura for exposta diretamente a
  usuários externos, aplique limite de tamanho e isolamento de processo.
