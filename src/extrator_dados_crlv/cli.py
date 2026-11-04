"""Interface de linha de comando do extrator de dados de CRLV-e."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from .crlv import extrair_dados
from .erros import ErroCRLV
from .modelos import DadosVeiculo


def _formatar(dados: DadosVeiculo) -> str:
    linhas = [
        f"Arquivo: {dados.arquivo}",
        f"Placa:   {dados.placa or 'não encontrada'}",
        f"Chassi:  {dados.chassi or 'não encontrado'}",
    ]
    extras = (
        ("RENAVAM", dados.renavam),
        ("Nº do CRV", dados.numero_crv),
        ("Exercício", dados.exercicio),
        ("Marca/Modelo", dados.marca_modelo),
        ("Ano fab./modelo", _juntar_anos(dados.ano_fabricacao, dados.ano_modelo)),
        ("Cor", dados.cor),
        ("Combustível", dados.combustivel),
        ("Categoria", dados.categoria),
        ("Espécie/Tipo", dados.especie_tipo),
        ("Local", dados.local),
        ("Proprietário", dados.proprietario),
        ("CPF/CNPJ", dados.cpf_cnpj),
    )
    for rotulo, valor in extras:
        if valor:
            linhas.append(f"{rotulo}: {valor}")
    return "\n".join(linhas)


def _juntar_anos(fabricacao: str | None, modelo: str | None) -> str | None:
    if fabricacao and modelo:
        return f"{fabricacao}/{modelo}"
    return fabricacao or modelo


def _criar_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="extrator-crlv",
        description=(
            "Extrai placa, chassi e outros dados de um CRLV-e em PDF, "
            "a partir de arquivo ou conteúdo base64."
        ),
    )
    parser.add_argument(
        "arquivos",
        nargs="*",
        metavar="PDF",
        help="arquivo(s) PDF do CRLV-e",
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--base64",
        metavar="CONTEUDO",
        help="conteúdo base64 do PDF; use '-' para ler da entrada padrão",
    )
    grupo.add_argument(
        "--base64-arquivo",
        metavar="TXT",
        help="arquivo de texto contendo o conteúdo base64",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="imprime o resultado em JSON (útil para integrações)",
    )
    return parser


def _ler_entrada_base64(args: argparse.Namespace) -> str:
    if args.base64 is not None:
        return sys.stdin.read() if args.base64 == "-" else args.base64

    caminho = Path(args.base64_arquivo)
    if str(caminho) == "-":
        return sys.stdin.read()
    return caminho.read_text(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = _criar_parser()
    args = parser.parse_args(argv)

    modo_base64 = args.base64 is not None or args.base64_arquivo is not None
    if modo_base64 and args.arquivos:
        parser.error("use arquivos PDF ou --base64/--base64-arquivo, não ambos")
    if not modo_base64 and not args.arquivos:
        parser.error("informe um ou mais PDFs ou --base64/--base64-arquivo")

    resultados: list[DadosVeiculo] = []
    houve_erro = False

    if modo_base64:
        try:
            resultados.append(extrair_dados(_ler_entrada_base64(args), base64=True))
        except (ErroCRLV, OSError, TypeError, UnicodeError) as erro:
            print(f"Erro ao ler base64: {erro}", file=sys.stderr)
            houve_erro = True
    else:
        for nome_arquivo in args.arquivos:
            try:
                resultados.append(extrair_dados(Path(nome_arquivo)))
            except (ErroCRLV, OSError) as erro:
                print(f"Erro ao ler {nome_arquivo}: {erro}", file=sys.stderr)
                houve_erro = True

    if args.json:
        conteudo: object
        if len(resultados) == 1:
            conteudo = resultados[0].para_dict()
        else:
            conteudo = [dados.para_dict() for dados in resultados]
        print(json.dumps(conteudo, ensure_ascii=False, indent=2))
    else:
        for indice, dados in enumerate(resultados):
            if indice:
                print()
            print(_formatar(dados))

    if houve_erro or not resultados:
        return 1
    if any(not dados.completo for dados in resultados):
        return 1
    return 0
