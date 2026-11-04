# Changelog

Todas as mudanças relevantes deste projeto são documentadas neste arquivo.

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e o projeto usa [Versionamento Semântico](https://semver.org/lang/pt-BR/).

## [0.1.0] - 2026-11-03

### Adicionado

- Extração de placa, chassi, RENAVAM, marca/modelo, anos, cor, combustível,
  categoria, espécie/tipo, local, proprietário e CPF/CNPJ de CRLV-e em PDF.
- Leitura a partir de arquivo, bytes, base64 padrão/URL-safe e data URI.
- Validação de placa (padrão antigo e Mercosul) e chassi (VIN de 17 caracteres).
- Exceções específicas para PDF inválido, protegido por senha e sem texto.
- Modelo imutável `DadosVeiculo` com `completo` e `para_dict()`.
- CLI opcional `extrator-crlv` e suporte a `python -m extrator_dados_crlv`.
- Tipagem PEP 561 (`py.typed`).
- Suíte de testes com CRLV sintético e notebook de validação manual.
