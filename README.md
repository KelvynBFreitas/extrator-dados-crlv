# Extrator de Dados CRLV

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Biblioteca Python para extrair **placa**, **chassi** e outros dados de um
**CRLV-e** (Certificado de Registro e Licenciamento de Veículo) em PDF.

A leitura principal usa a camada de texto do PDF. Para PDFs digitalizados, há
um fallback opcional de OCR com RapidOCR (ONNX).

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

### OCR opcional

Para ler CRLVs digitalizados (PDF sem camada de texto), instale o extra
`ocr`, que adiciona o RapidOCR e o ONNX Runtime:

```bash
pip install ".[ocr]"
```

```bash
uv add "extrator-dados-crlv[ocr]"
```

O primeiro uso do OCR inicializa os modelos ONNX e pode levar alguns segundos.
Depois o motor fica em memória.

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
| Arquivo digitalizado | `extrair_dados("crlv.pdf", ocr=True)` |
| Base64 digitalizado | `extrair_dados_base64_robusto(conteudo_b64)` |

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

### PDFs digitalizados (OCR)

Quando o PDF não possui camada de texto, use `ocr=True` (ou uma das funções
`*_robusto`, que são atalhos) para acionar o RapidOCR:

```python
from pathlib import Path

from extrator_dados_crlv import (
    aplicar_ocr,
    extrair_dados,
    extrair_dados_base64_robusto,
    extrair_dados_robusto,
)

# Arquivo digitalizado
dados = extrair_dados("crlv-digitalizado.pdf", ocr=True)
dados = extrair_dados_robusto("crlv-digitalizado.pdf")  # equivalente

# Base64 digitalizado
dados = extrair_dados_base64_robusto(conteudo_base64)

# Bytes digitalizados
dados = extrair_dados(conteudo_pdf, ocr=True)

# Útil para pré-processar e salvar o PDF com a camada de texto invisível
pdf_com_texto = aplicar_ocr("crlv-digitalizado.pdf")
Path("crlv-ocr.pdf").write_bytes(pdf_com_texto)
```

O OCR é executado a 300 DPI por padrão e pode ser ajustado com `dpi=...`
(entre 72 e 600). O texto reconhecido é inserido de forma invisível nas
coordenadas da imagem; a extração então é executada novamente. Se o PDF já
possui texto, o OCR não é acionado.

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
| `OCRError` | Falha ao renderizar, executar ou gravar o OCR |
| `OCRIndisponivelError` | OCR solicitado, mas o extra `ocr` não está instalado |
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
extrator-crlv --ocr "crlv-digitalizado.pdf" --json
extrator-crlv --base64 "JVBERi0xLjQK..." --json
extrator-crlv --base64-arquivo crlv_base64.txt --ocr --json
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

Se não houver camada de texto e o OCR estiver habilitado, o RapidOCR rasteriza
as páginas (300 DPI por padrão), injeta o texto reconhecido de forma invisível,
preservando as coordenadas, e a extração é executada novamente.

## Desenvolvimento

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run ruff check .
uv run ruff format --check .
```

Para executar também o teste de integração com o OCR real:

```bash
uv sync --extra ocr
uv run python -m unittest discover -s tests -v
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

- PDFs digitalizados dependem do extra `ocr`; a qualidade varia com a
  resolução, o contraste e a orientação da digitalização.
- O OCR é mais lento e consome mais memória que a leitura direta da camada de
  texto.
- PDFs protegidos por senha não são suportados.
- Layouts muito diferentes do CRLV padrão podem exigir ajuste nos rótulos.
- A biblioteca apenas extrai texto; **não valida assinatura digital, QR Code,
  autenticidade ou situação do veículo** no DETRAN/SENATRAN.
- PDFs são entradas não confiáveis. Se a leitura for exposta diretamente a
  usuários externos, aplique limite de tamanho e isolamento de processo.
