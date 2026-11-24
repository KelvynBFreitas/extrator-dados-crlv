"""OCR opcional para CRLVs digitalizados, usando RapidOCR (ONNX).

O texto reconhecido é injetado de volta no PDF como uma camada invisível
(``render_mode=3``), preservando as coordenadas originais. Assim, a extração
continua usando a mesma lógica de leitura por rótulos e posição.
"""

from __future__ import annotations

import threading
from os import PathLike
from pathlib import Path
from typing import Any

try:  # PyMuPDF >= 1.24 expõe o pacote como "pymupdf"
    import pymupdf as fitz
except ImportError:  # versões antigas só têm o módulo "fitz"
    import fitz  # type: ignore[no-redef]

from .erros import (
    CRLVInvalidoError,
    CRLVProtegidoError,
    CRLVSemTextoError,
    OCRError,
    OCRIndisponivelError,
)

DPI_OCR_PADRAO = 300
_DPI_MINIMO = 72
_DPI_MAXIMO = 600
_FONTE = "helv"
_TAMANHO_FONTE_MINIMO = 6.0
_ESCALA_HORIZONTAL_MINIMA = 0.1
_ESCALA_HORIZONTAL_MAXIMA = 10.0

_engine: Any | None = None
_engine_lock = threading.Lock()


def _carregar_engine() -> Any:
    """Importa e inicializa o RapidOCR somente quando o OCR for necessário."""
    # rapidocr-onnxruntime é a API 1.x (usada em Python < 3.13); rapidocr >= 3
    # é a API atual e também cobre Python 3.13+.
    try:
        from rapidocr_onnxruntime import RapidOCR as RapidOCRLegado
    except ImportError:
        RapidOCRLegado = None

    if RapidOCRLegado is not None:
        return RapidOCRLegado()

    try:
        from rapidocr import RapidOCR
    except ImportError as erro:
        raise OCRIndisponivelError(
            "O OCR opcional não está instalado. Instale com "
            "'pip install \"extrator-dados-crlv[ocr]\"'."
        ) from erro

    # RapidOCR >= 3 usa logging; mantém a saída da biblioteca silenciosa.
    return RapidOCR(params={"Global.log_level": "error"})


def _obter_engine() -> Any:
    """Retorna uma instância única (lazy) do motor de OCR."""
    global _engine

    if _engine is not None:
        return _engine

    with _engine_lock:
        if _engine is None:
            try:
                _engine = _carregar_engine()
            except OCRIndisponivelError:
                raise
            except Exception as erro:
                raise OCRError("Não foi possível inicializar o motor de OCR.") from erro

    return _engine


def _validar_dpi(dpi: int) -> int:
    if isinstance(dpi, bool) or not isinstance(dpi, int):
        raise TypeError("O dpi deve ser um número inteiro.")
    if not _DPI_MINIMO <= dpi <= _DPI_MAXIMO:
        raise ValueError(f"O dpi deve estar entre {_DPI_MINIMO} e {_DPI_MAXIMO}.")
    return dpi


def _texto_para_pdf(texto: object) -> str:
    """Mantém o texto em uma linha e apenas com caracteres Latin-1."""
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8", "replace")
    normalizado = " ".join(str(texto).replace("\u00ad", "").split())
    if not normalizado:
        return ""
    return normalizado.encode("latin-1", "replace").decode("latin-1")


def _limites_caixa(caixa: object) -> tuple[float, float, float, float] | None:
    try:
        pontos = [(float(ponto[0]), float(ponto[1])) for ponto in caixa]  # type: ignore[union-attr]
    except (TypeError, ValueError, IndexError):
        return None

    if len(pontos) < 2:
        return None

    xs = [ponto[0] for ponto in pontos]
    ys = [ponto[1] for ponto in pontos]
    return min(xs), min(ys), max(xs), max(ys)


def _normalizar_resultado(saida: Any) -> list[Any]:
    """Aceita a saída do rapidocr-onnxruntime (1.x) e do rapidocr (3.x)."""
    if isinstance(saida, tuple):  # API antiga: (lista_de_resultados, tempos)
        resultado, _ = saida
        return list(resultado or [])

    # API nova: objeto com boxes/txts/scores.
    caixas = getattr(saida, "boxes", None)
    textos = getattr(saida, "txts", None)
    if caixas is None or textos is None:
        return []

    pontuacoes = getattr(saida, "scores", None)
    if pontuacoes is None:
        pontuacoes = [1.0] * len(textos)
    return list(zip(caixas, textos, pontuacoes, strict=False))


def _executar_engine(engine: Any, imagem: bytes, numero_pagina: int) -> list[Any]:
    try:
        return _normalizar_resultado(engine(imagem))
    except Exception as erro:
        raise OCRError(f"Falha ao executar o OCR na página {numero_pagina}.") from erro


def _inserir_resultado(
    pagina: fitz.Page,
    resultado: list[Any],
    fator_escala: float,
) -> int:
    insertados = 0

    for item in resultado:
        try:
            caixa, texto, _ = item
        except (TypeError, ValueError):
            continue

        texto = _texto_para_pdf(texto)
        limites = _limites_caixa(caixa)
        if not texto or limites is None:
            continue

        x0, y0, x1, y1 = limites
        altura = max((y1 - y0) * fator_escala, _TAMANHO_FONTE_MINIMO)
        largura = (x1 - x0) * fator_escala
        ponto = fitz.Point(x0 * fator_escala, y1 * fator_escala)

        # Ajusta a largura do texto à caixa detectada. Sem isso, rótulos
        # vizinhos podem se fundir em uma única linha ao reler o PDF.
        morph = None
        if largura > 0:
            largura_texto = fitz.get_text_length(texto, fontname=_FONTE, fontsize=altura)
            if largura_texto > 0:
                escala_x = largura / largura_texto
                if _ESCALA_HORIZONTAL_MINIMA <= escala_x <= _ESCALA_HORIZONTAL_MAXIMA:
                    morph = (ponto, fitz.Matrix(escala_x, 1))

        pagina.insert_text(
            ponto,
            texto,
            fontsize=altura,
            fontname=_FONTE,
            render_mode=3,
            morph=morph,
        )
        insertados += 1

    return insertados


def _aplicar_ocr_bytes(conteudo: bytes, *, dpi: int) -> bytes:
    try:
        documento = fitz.open(stream=conteudo, filetype="pdf")
    except Exception as erro:  # PyMuPDF levanta tipos variados para PDF inválido
        raise CRLVInvalidoError("O conteúdo informado não é um PDF válido.") from erro

    with documento:
        if documento.needs_pass:
            raise CRLVProtegidoError("O PDF está protegido por senha.")
        if documento.page_count == 0:
            raise CRLVInvalidoError("O PDF não possui páginas.")

        engine = _obter_engine()
        total_insertados = 0
        fator_escala = 72.0 / dpi

        for numero_pagina, pagina in enumerate(documento, start=1):
            if pagina.rotation:
                # Corrige a orientação visual para que as coordenadas do OCR
                # coincidam com o sistema de coordenadas da página.
                pagina.remove_rotation()

            try:
                pix = pagina.get_pixmap(dpi=dpi, alpha=False)
                imagem = pix.tobytes("png")
            except Exception as erro:
                raise OCRError(
                    f"Não foi possível renderizar a página {numero_pagina} para OCR."
                ) from erro

            resultado = _executar_engine(engine, imagem, numero_pagina)
            total_insertados += _inserir_resultado(pagina, resultado, fator_escala)

        if total_insertados == 0:
            raise CRLVSemTextoError(
                "O OCR não reconheceu texto no PDF. Verifique a qualidade da digitalização."
            )

        try:
            return documento.tobytes()
        except Exception as erro:
            raise OCRError("Não foi possível gerar o PDF com a camada de texto do OCR.") from erro


def aplicar_ocr(
    origem: str | PathLike[str] | bytes | bytearray | memoryview,
    *,
    dpi: int = DPI_OCR_PADRAO,
) -> bytes:
    """Aplica OCR em um PDF digitalizado e retorna os novos bytes.

    O texto reconhecido é inserido como uma camada invisível sobre a imagem,
    mantendo a posição aproximada de cada linha detectada. O PDF original não
    é alterado.

    Args:
        origem: caminho do arquivo ou conteúdo binário do PDF.
        dpi: resolução usada para rasterizar as páginas antes do OCR
            (entre 72 e 600; padrão 300).

    Returns:
        Bytes do PDF com a camada de texto OCR.

    Raises:
        CRLVInvalidoError: o conteúdo não é um PDF válido ou está vazio.
        CRLVProtegidoError: o PDF exige senha.
        CRLVSemTextoError: o OCR não reconheceu nenhum texto.
        OCRIndisponivelError: o extra ``ocr`` não está instalado.
        OCRError: falha ao renderizar, executar ou gravar o PDF.
        FileNotFoundError: o arquivo informado não existe.
        IsADirectoryError: o caminho informado não é um arquivo.
        TypeError: tipo de origem ou valor de ``dpi`` inválido.
        ValueError: ``dpi`` fora do intervalo permitido.
    """
    dpi = _validar_dpi(dpi)

    if isinstance(origem, (str, PathLike)):
        caminho = Path(origem)
        if not caminho.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")
        if not caminho.is_file():
            raise IsADirectoryError(f"O caminho não é um arquivo: {caminho}")
        conteudo = caminho.read_bytes()
    elif isinstance(origem, (bytes, bytearray, memoryview)):
        conteudo = bytes(origem)
    else:
        raise TypeError("A origem deve ser caminho, bytes, bytearray ou memoryview.")

    if not conteudo:
        raise CRLVInvalidoError("O conteúdo do PDF está vazio.")

    return _aplicar_ocr_bytes(conteudo, dpi=dpi)


__all__ = ["DPI_OCR_PADRAO", "aplicar_ocr"]
