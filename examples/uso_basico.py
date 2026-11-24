"""Exemplo de uso da biblioteca extrator-dados-crlv."""

from __future__ import annotations

from pathlib import Path

from extrator_dados_crlv import (
    ErroCRLV,
    extrair_dados,
    extrair_dados_base64,
    extrair_dados_base64_robusto,
    extrair_dados_robusto,
)


def ler_arquivo(caminho: str | Path) -> None:
    dados = extrair_dados(caminho)

    if not dados.completo:
        print("Placa ou chassi não encontrados no documento.")
        return

    print(f"Placa:  {dados.placa}")
    print(f"Chassi: {dados.chassi}")
    print(f"Dados completos: {dados.para_dict()}")


def ler_base64(conteudo_base64: str) -> None:
    dados = extrair_dados_base64(conteudo_base64)
    print(f"Placa:  {dados.placa}")
    print(f"Chassi: {dados.chassi}")


def ler_digitalizado(caminho: str | Path) -> None:
    """Usa OCR se o PDF não tiver camada de texto (requer o extra 'ocr')."""
    dados = extrair_dados_robusto(caminho)
    print(f"Placa:  {dados.placa}")
    print(f"Chassi: {dados.chassi}")


def ler_base64_digitalizado(conteudo_base64: str) -> None:
    """Usa OCR em um base64 de PDF digitalizado (requer o extra 'ocr')."""
    dados = extrair_dados_base64_robusto(conteudo_base64)
    print(f"Placa:  {dados.placa}")
    print(f"Chassi: {dados.chassi}")


# Para testar base64, chame ler_base64(conteudo_base64) com o conteúdo da API.


def main() -> None:
    caminho = Path("crlv.pdf")

    try:
        ler_arquivo(caminho)
    except FileNotFoundError:
        print(f"Arquivo não encontrado: {caminho}")
    except ErroCRLV as erro:
        print(f"Não foi possível ler o CRLV: {erro}")


if __name__ == "__main__":
    main()
