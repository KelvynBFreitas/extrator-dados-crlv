"""Modelo de dados retornado pela biblioteca."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class DadosVeiculo:
    """Dados extraídos de um CRLV-e.

    Campos não encontrados no documento ficam como ``None``. Use a propriedade
    :attr:`completo` para verificar se placa e chassi foram localizados.
    """

    arquivo: str
    placa: str | None = None
    chassi: str | None = None
    renavam: str | None = None
    numero_crv: str | None = None
    exercicio: str | None = None
    marca_modelo: str | None = None
    ano_fabricacao: str | None = None
    ano_modelo: str | None = None
    cor: str | None = None
    combustivel: str | None = None
    categoria: str | None = None
    especie_tipo: str | None = None
    local: str | None = None
    proprietario: str | None = None
    cpf_cnpj: str | None = None

    @property
    def completo(self) -> bool:
        """Indica se os dois campos críticos (placa e chassi) foram encontrados."""
        return bool(self.placa and self.chassi)

    def para_dict(self) -> dict[str, str | None]:
        """Retorna os dados como um dicionário serializável."""
        return asdict(self)


__all__ = ["DadosVeiculo"]
