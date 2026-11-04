"""Extrator de dados de CRLV-e em PDF.

A API pública principal é composta por:

- :func:`extrair_dados`: aceita caminho, bytes ou base64.
- :func:`extrair_dados_bytes`: aceita o PDF já em memória.
- :func:`extrair_dados_base64`: aceita o PDF em base64.
- :class:`DadosVeiculo`: resultado tipado da extração.
- Exceções específicas em :mod:`extrator_dados_crlv.erros`.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .crlv import extrair_dados, extrair_dados_base64, extrair_dados_bytes
from .erros import (
    Base64InvalidoError,
    CRLVInvalidoError,
    CRLVProtegidoError,
    CRLVSemTextoError,
    ErroCRLV,
)
from .modelos import DadosVeiculo

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
    "__version__",
    "extrair_dados",
    "extrair_dados_base64",
    "extrair_dados_bytes",
]
