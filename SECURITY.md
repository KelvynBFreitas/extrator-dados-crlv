# Segurança

## Reportando vulnerabilidades

Não abra uma issue pública para relatar vulnerabilidades de segurança.

Use o recurso **Security Advisories** do GitHub para enviar um relato privado
ao mantenedor do projeto. Inclua:

- versão afetada;
- forma de reprodução;
- impacto esperado;
- sugestão de correção, se houver.

## Escopo

O `extrator-dados-crlv` processa PDFs não confiáveis. Se a biblioteca for
exposta diretamente a usuários externos:

- limite o tamanho do arquivo/base64 recebido;
- execute a extração em processo isolado ou com limites de memória;
- não confie nos dados extraídos para decisões de segurança;
- valide a autenticidade do CRLV nos canais oficiais do DETRAN/SENATRAN.

A biblioteca não valida assinatura digital, QR Code, autenticidade ou situação
do veículo.
