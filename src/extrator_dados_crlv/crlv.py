"""Núcleo de leitura e extração de dados de CRLV-e em PDF."""

from __future__ import annotations

import binascii
import re
import unicodedata
from base64 import b64decode, urlsafe_b64decode
from collections import Counter
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

try:  # PyMuPDF >= 1.24 expõe o pacote como "pymupdf"
    import pymupdf as fitz
except ImportError:  # versões antigas só têm o módulo "fitz"
    import fitz  # type: ignore[no-redef]

from .erros import (
    Base64InvalidoError,
    CRLVInvalidoError,
    CRLVProtegidoError,
    CRLVSemTextoError,
)
from .modelos import DadosVeiculo

# Placa antiga (ABC1234) e Mercosul (ABC1D23).
_PLACA_RE = re.compile(r"\b([A-Z]{3}[0-9][A-Z0-9][0-9]{2})\b")
# Chassi/VIN: 17 caracteres, sem as letras I, O e Q.
_CHASSI_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_BASE64_RE = re.compile(r"[A-Za-z0-9+/=_-]+")

_ORIGEM_BASE64 = "<base64>"
_ORIGEM_BYTES = "<bytes>"


def _normalizar(texto: str) -> str:
    """Remove acentos, pontuação e diferenças de caixa para comparar rótulos."""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caractere for caractere in texto if not unicodedata.combining(caractere))
    texto = texto.upper().replace("\u00ad", "")
    return re.sub(r"[^A-Z0-9]+", " ", texto).strip()


# Rótulos do CRLV -> campo do resultado.
_CAMPOS: dict[str, tuple[str, ...]] = {
    "placa": ("PLACA",),
    "chassi": ("CHASSI",),
    "renavam": ("CÓDIGO RENAVAM",),
    "numero_crv": ("NÚMERO DO CRV",),
    "exercicio": ("EXERCÍCIO",),
    "marca_modelo": ("MARCA / MODELO / VERSÃO", "MARCA / MODELO"),
    "ano_fabricacao": ("ANO FABRICAÇÃO",),
    "ano_modelo": ("ANO MODELO",),
    "cor": ("COR PREDOMINANTE",),
    "combustivel": ("COMBUSTÍVEL",),
    "categoria": ("CATEGORIA",),
    "especie_tipo": ("ESPÉCIE / TIPO",),
    "local": ("LOCAL",),
    "proprietario": ("NOME",),
    "cpf_cnpj": ("CPF / CNPJ",),
}

_CAMPOS_NORMALIZADOS: dict[str, frozenset[str]] = {
    campo: frozenset(_normalizar(alias) for alias in aliases) for campo, aliases in _CAMPOS.items()
}

# Todos os rótulos conhecidos (inclusive os que não são extraídos) para não
# confundir um rótulo vizinho com o valor de outro campo.
_ROTULOS = frozenset(
    rotulo for aliases in _CAMPOS_NORMALIZADOS.values() for rotulo in aliases
) | frozenset(
    _normalizar(rotulo)
    for rotulo in (
        "PLACA ANTERIOR / UF",
        "CÓDIGO DE SEGURANÇA DO CLA",
        "NÚMERO DE SEGURANÇA DO CRV",
        "POTÊNCIA/CILINDRADA",
        "PESO BRUTO TOTAL",
        "CAPACIDADE",
        "CMT",
        "EIXOS",
        "LOTAÇÃO",
        "MOTOR",
        "CARROCERIA",
        "DATA",
        "CAT",
        "OBSERVAÇÕES DO VEÍCULO",
        "INFORMAÇÕES DO SEGURO DPVAT",
        "DADOS DO SEGURO DPVAT",
        "MENSAGENS SENATRAN",
    )
)


@dataclass(frozen=True, slots=True)
class _Linha:
    pagina: int
    texto: str
    normalizado: str
    x0: float
    y0: float
    x1: float
    y1: float


def _ler_linhas(documento: fitz.Document) -> list[_Linha]:
    linhas: list[_Linha] = []
    for numero_pagina in range(documento.page_count):
        pagina = documento[numero_pagina]
        for bloco in pagina.get_text("dict")["blocks"]:
            if bloco.get("type") != 0:
                continue
            for linha in bloco.get("lines", []):
                texto = "".join(span.get("text", "") for span in linha.get("spans", []))
                texto = " ".join(texto.split())
                if not texto:
                    continue
                x0, y0, x1, y1 = linha["bbox"]
                linhas.append(
                    _Linha(
                        pagina=numero_pagina,
                        texto=texto,
                        normalizado=_normalizar(texto),
                        x0=x0,
                        y0=y0,
                        x1=x1,
                        y1=y1,
                    )
                )
    return linhas


def _valor_do_rotulo(linhas: Sequence[_Linha], rotulos: Collection[str]) -> str | None:
    """Localiza o valor impresso logo abaixo de um rótulo, na mesma coluna.

    ``rotulos`` deve conter textos já normalizados por :func:`_normalizar`.
    """
    melhor: tuple[tuple[float, float, float], _Linha] | None = None

    for rotulo in linhas:
        if rotulo.normalizado not in rotulos:
            continue

        for valor in linhas:
            if valor is rotulo or valor.pagina != rotulo.pagina:
                continue
            if valor.normalizado in _ROTULOS:
                continue

            distancia_vertical = valor.y0 - rotulo.y1
            if distancia_vertical < -1.5 or distancia_vertical > 30.0:
                continue

            sobreposicao = min(valor.x1, rotulo.x1) - max(valor.x0, rotulo.x0)
            alinhamento = min(abs(valor.x0 - rotulo.x0), abs(valor.x1 - rotulo.x1))
            if sobreposicao <= 0 and alinhamento > 30.0:
                continue

            nota = (
                0.0 if sobreposicao > 0 else 1.0,
                distancia_vertical,
                alinhamento,
            )
            if melhor is None or nota < melhor[0]:
                melhor = (nota, valor)

    return melhor[1].texto if melhor else None


def _normalizar_placa(texto: str | None) -> str | None:
    if not texto:
        return None
    candidato = re.sub(r"[^A-Z0-9]", "", texto.upper().split("/")[0])
    encontrado = _PLACA_RE.search(candidato)
    return encontrado.group(1) if encontrado else None


def _normalizar_chassi(texto: str | None) -> str | None:
    if not texto:
        return None
    candidato = re.sub(r"[^A-Z0-9]", "", texto.upper())
    if (
        len(candidato) == 17
        and _CHASSI_RE.fullmatch(candidato)
        and any(caractere.isalpha() for caractere in candidato)
        and any(caractere.isdigit() for caractere in candidato)
    ):
        return candidato

    for encontrado in _CHASSI_RE.finditer(texto.upper()):
        possivel = encontrado.group(1)
        if any(caractere.isalpha() for caractere in possivel) and any(
            caractere.isdigit() for caractere in possivel
        ):
            return possivel
    return None


def _mais_comum(candidatos: Iterable[str]) -> str | None:
    contagem = Counter(candidatos)
    if not contagem:
        return None
    return contagem.most_common(1)[0][0]


def _placa_nas_linhas(linhas: Sequence[_Linha]) -> str | None:
    candidatos = [
        encontrado.group(1)
        for linha in linhas
        if "ANTERIOR" not in linha.normalizado
        for encontrado in _PLACA_RE.finditer(linha.texto.upper())
    ]
    return _mais_comum(candidatos)


def _chassi_nas_linhas(linhas: Sequence[_Linha]) -> str | None:
    candidatos: list[str] = []
    for linha in linhas:
        for encontrado in _CHASSI_RE.finditer(linha.texto.upper()):
            possivel = encontrado.group(1)
            if any(caractere.isalpha() for caractere in possivel) and any(
                caractere.isdigit() for caractere in possivel
            ):
                candidatos.append(possivel)
    return _mais_comum(candidatos)


def _limpar_campo(campo: str, texto: str | None) -> str | None:
    if not texto:
        return None

    if campo == "placa":
        return _normalizar_placa(texto)
    if campo == "chassi":
        return _normalizar_chassi(texto)
    if campo in {"renavam", "numero_crv"}:
        digitos = re.sub(r"\D", "", texto)
        return digitos or None
    if campo in {"ano_fabricacao", "ano_modelo", "exercicio"}:
        encontrado = re.search(r"\b(19|20)\d{2}\b", texto)
        return encontrado.group(0) if encontrado else texto.strip()
    return texto.strip() or None


def _texto_base64(conteudo: str | bytes | bytearray | memoryview) -> str:
    if isinstance(conteudo, (bytes, bytearray, memoryview)):
        dados = bytes(conteudo)
        if dados.startswith(b"\xef\xbb\xbf"):
            dados = dados[3:]
        try:
            return dados.decode("ascii")
        except UnicodeDecodeError:
            try:
                return dados.decode("utf-8")
            except UnicodeDecodeError as erro:
                raise Base64InvalidoError(
                    "O conteúdo base64 contém caracteres inválidos."
                ) from erro

    if isinstance(conteudo, str):
        return conteudo

    raise TypeError("O conteúdo base64 deve ser str, bytes, bytearray ou memoryview.")


def _decodificar_base64(conteudo: str | bytes | bytearray | memoryview) -> bytes:
    """Decodifica base64 padrão ou URL-safe, com ou sem data URI e padding."""
    texto = _texto_base64(conteudo).strip().lstrip("\ufeff")

    if texto.lower().startswith("data:"):
        cabecalho, separador, dados = texto.partition(",")
        if not separador or "base64" not in cabecalho.lower():
            raise Base64InvalidoError("Data URI não contém dados base64.")
        texto = dados

    texto = "".join(texto.split())
    if not texto:
        raise Base64InvalidoError("O conteúdo base64 está vazio.")
    if not _BASE64_RE.fullmatch(texto):
        raise Base64InvalidoError("O conteúdo base64 contém caracteres inválidos.")

    # Alguns emissores removem o preenchimento "=" final.
    texto += "=" * (-len(texto) % 4)

    try:
        decodificado = b64decode(texto, validate=True)
    except (binascii.Error, ValueError):
        try:
            decodificado = urlsafe_b64decode(texto)
        except (binascii.Error, ValueError) as erro:
            raise Base64InvalidoError("Não foi possível decodificar o conteúdo base64.") from erro

    if b"%PDF-" not in decodificado[:1024]:
        raise Base64InvalidoError("O conteúdo base64 não corresponde a um PDF.")
    return decodificado


def _abrir_pdf(conteudo: bytes) -> fitz.Document:
    if not conteudo:
        raise CRLVInvalidoError("O conteúdo do PDF está vazio.")
    try:
        return fitz.open(stream=conteudo, filetype="pdf")
    except Exception as erro:  # PyMuPDF levanta tipos variados para PDF inválido
        raise CRLVInvalidoError("O conteúdo informado não é um PDF válido.") from erro


def _extrair_do_documento(documento: fitz.Document, identificacao: str) -> DadosVeiculo:
    with documento:
        if documento.needs_pass:
            raise CRLVProtegidoError("O PDF está protegido por senha.")
        if documento.page_count == 0:
            raise CRLVInvalidoError("O PDF não possui páginas.")
        linhas = _ler_linhas(documento)

    if not linhas:
        raise CRLVSemTextoError(
            "O PDF não possui camada de texto. Se for digitalizado, aplique OCR antes da extração."
        )

    valores: dict[str, str | None] = {}
    for campo, rotulos in _CAMPOS_NORMALIZADOS.items():
        bruto = _valor_do_rotulo(linhas, rotulos)
        valores[campo] = _limpar_campo(campo, bruto)

    # Placa e chassi são os dados críticos: se o layout fugir do esperado,
    # procura-se o padrão no documento inteiro como alternativa.
    if not valores["placa"]:
        valores["placa"] = _placa_nas_linhas(linhas)
    if not valores["chassi"]:
        valores["chassi"] = _chassi_nas_linhas(linhas)

    return DadosVeiculo(arquivo=identificacao, **valores)


def _extrair_arquivo(caminho: str | PathLike[str]) -> DadosVeiculo:
    if not isinstance(caminho, (str, PathLike)):
        raise TypeError("O caminho do PDF deve ser str ou PathLike.")

    caminho_pdf = Path(caminho)
    if not caminho_pdf.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho_pdf}")
    if not caminho_pdf.is_file():
        raise IsADirectoryError(f"O caminho não é um arquivo: {caminho_pdf}")

    try:
        documento = fitz.open(caminho_pdf)
    except Exception as erro:  # PyMuPDF levanta tipos variados para PDF inválido
        raise CRLVInvalidoError(f"Não foi possível abrir o PDF: {caminho_pdf}") from erro

    return _extrair_do_documento(documento, str(caminho_pdf))


def extrair_dados(
    origem: str | PathLike[str] | bytes | bytearray | memoryview,
    *,
    base64: bool = False,
) -> DadosVeiculo:
    """Extrai placa, chassi e outros dados de um CRLV-e.

    Args:
        origem: caminho do arquivo, conteúdo binário do PDF ou string base64.
        base64: quando ``True``, interpreta ``origem`` como conteúdo base64.

    Returns:
        :class:`DadosVeiculo` com os campos encontrados. Campos ausentes ficam
        como ``None``; use ``dados.completo`` para validar placa e chassi.

    Raises:
        FileNotFoundError: o arquivo informado não existe.
        IsADirectoryError: o caminho informado não é um arquivo.
        CRLVInvalidoError: o conteúdo não é um PDF válido.
        CRLVProtegidoError: o PDF exige senha.
        CRLVSemTextoError: o PDF não possui camada de texto.
        Base64InvalidoError: o conteúdo base64 é inválido ou não é um PDF.
        TypeError: o tipo da origem ou do conteúdo é incompatível.
    """
    if base64:
        if not isinstance(origem, (str, bytes, bytearray, memoryview)):
            raise TypeError("Com base64=True, a origem deve ser str ou bytes.")
        return extrair_dados_base64(origem)

    if isinstance(origem, (bytes, bytearray, memoryview)):
        return extrair_dados_bytes(origem)

    return _extrair_arquivo(origem)


def extrair_dados_bytes(conteudo: bytes | bytearray | memoryview) -> DadosVeiculo:
    """Extrai os dados de um CRLV-e já carregado em memória.

    Args:
        conteudo: bytes do arquivo PDF.

    Returns:
        :class:`DadosVeiculo` com os campos encontrados.

    Raises:
        CRLVInvalidoError: o conteúdo não é um PDF válido.
        CRLVProtegidoError: o PDF exige senha.
        CRLVSemTextoError: o PDF não possui camada de texto.
        TypeError: ``conteudo`` não é um tipo binário aceito.
    """
    if not isinstance(conteudo, (bytes, bytearray, memoryview)):
        raise TypeError("O conteúdo do PDF deve ser bytes, bytearray ou memoryview.")
    return _extrair_do_documento(_abrir_pdf(bytes(conteudo)), _ORIGEM_BYTES)


def extrair_dados_base64(
    conteudo: str | bytes | bytearray | memoryview,
) -> DadosVeiculo:
    """Extrai os dados de um CRLV-e recebido em base64.

    Aceita base64 padrão ou URL-safe, com ou sem quebras de linha, com ou sem
    preenchimento ``=`` e data URIs no formato
    ``data:application/pdf;base64,...``.

    Args:
        conteudo: string ou bytes contendo o PDF em base64.

    Returns:
        :class:`DadosVeiculo` com os campos encontrados.

    Raises:
        Base64InvalidoError: o conteúdo base64 é inválido ou não é um PDF.
        CRLVInvalidoError: o PDF decodificado não é válido.
        CRLVProtegidoError: o PDF exige senha.
        CRLVSemTextoError: o PDF não possui camada de texto.
        TypeError: ``conteudo`` não é str nem um tipo binário aceito.
    """
    return _extrair_do_documento(
        _abrir_pdf(_decodificar_base64(conteudo)),
        _ORIGEM_BASE64,
    )
