"""Extrator de dados de CRLV-e em PDF.

A API pública principal é composta por:

- :func:`extrair_dados`: aceita caminho, bytes ou base64.
- :func:`extrair_dados_bytes`: aceita o PDF já em memória.
- :func:`extrair_dados_base64`: aceita o PDF em base64.
- :func:`extrair_dados_robusto`: idem, com fallback de OCR.
- :func:`extrair_dados_base64_robusto`: base64 com fallback de OCR.
- :func:`aplicar_ocr`: injeta uma camada de texto em PDF digitalizado.
- :class:`DadosVeiculo`: resultado tipado da extração.
- Exceções específicas em :mod:`extrator_dados_crlv.erros`.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .crlv import (
    extrair_dados,
    extrair_dados_base64,
    extrair_dados_base64_robusto,
    extrair_dados_bytes,
    extrair_dados_robusto,
)
from .erros import (
    Base64InvalidoError,
    CRLVInvalidoError,
    CRLVProtegidoError,
    CRLVSemTextoError,
    ErroCRLV,
    OCRError,
    OCRIndisponivelError,
)
from .modelos import DadosVeiculo
from .ocr import aplicar_ocr

try:
    __version__ = version("extrator-dados-crlv")
except PackageNotFoundError:  # execução direta do código-fonte sem instalação
    __version__ = "0.1.0"

__all__ = [
    "Base64InvalidoError",
    "CRLVInvalidoError",
    "CRLVProtegidoError",
    "CRLVSemTextoError",
    "DadosVeiculo",
    "ErroCRLV",
    "OCRError",
    "OCRIndisponivelError",
    "__version__",
    "aplicar_ocr",
    "extrair_dados",
    "extrair_dados_base64",
    "extrair_dados_base64_robusto",
    "extrair_dados_bytes",
    "extrair_dados_robusto",
]
