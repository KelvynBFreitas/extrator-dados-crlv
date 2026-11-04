"""Exceções públicas do extrator de dados de CRLV-e."""

from __future__ import annotations


class ErroCRLV(Exception):
    """Erro base para falhas ao ler ou extrair dados de um CRLV."""


class CRLVInvalidoError(ErroCRLV, ValueError):
    """O conteúdo informado não é um PDF válido ou não pôde ser lido."""


class CRLVProtegidoError(CRLVInvalidoError):
    """O PDF está protegido por senha."""


class CRLVSemTextoError(CRLVInvalidoError):
    """O PDF não possui camada de texto (provavelmente é digitalizado)."""


class Base64InvalidoError(CRLVInvalidoError):
    """O conteúdo base64 é inválido ou não representa um PDF."""


__all__ = [
    "Base64InvalidoError",
    "CRLVInvalidoError",
    "CRLVProtegidoError",
    "CRLVSemTextoError",
    "ErroCRLV",
]
