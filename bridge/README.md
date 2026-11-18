# BRIDGE — Comunicação bilíngue em tempo real (pt-BR ⇄ uk-UA)

Aplicativo privado para duas pessoas (Cauã — pt-BR, Katya — uk-UA) conversarem
com legendas traduzidas (Fase 1), voz traduzida (Fase 2) e conversa quase natural (Fase 3).

## Status atual

| Item | Estado |
|---|---|
| Etapa 1 — Planejamento técnico | **Concluído (este documento)** |
| Etapa 2 — MVP | Não iniciado — nenhum código de aplicativo existe ainda |
| Etapa 3 — Testes | Plano definido, nada implementado |
| Etapa 4 — Evolução (voz, clonagem) | Apenas pesquisa |

> Regra do projeto: nada aqui deve ser descrito como funcional antes de existir código e teste que comprovem.

## Documentos

1. [Viabilidade e limitações de Android/iOS](docs/01-viabilidade.md) — a resposta à pergunta principal.
2. [Arquitetura, tecnologias, fluxo de áudio e estrutura de pastas](docs/02-arquitetura.md)
3. [Modelo de segurança e privacidade](docs/03-seguranca.md)
4. [Plano de testes](docs/04-testes.md)
5. [Custos, roadmap e pesquisa das Fases 2 e 3](docs/05-custos-roadmap.md)

## Resposta curta

**Capturar o áudio de uma chamada do Instagram no mesmo celular e legendar por cima: não é viável de forma confiável.**
No iOS é impossível para apps de terceiros; no Android o sistema bloqueia a captura de áudio de chamadas
(VoIP) e silencia o microfone para outros apps durante a chamada.

**O que é viável e será construído:**

- **Modo Chamada BRIDGE (recomendado):** a chamada de vídeo acontece dentro do próprio BRIDGE (WebRTC,
  ponta a ponta). Cada celular processa só a voz do seu dono — áudio limpo, falante e idioma conhecidos —
  e envia a legenda criptografada para o outro.
- **Modo Computador (compatível com Instagram):** chamada do Instagram no navegador do notebook; o BRIDGE
  desktop captura o áudio do sistema (voz dela) e o microfone (sua voz) por canais separados.
- **Modo Ambiente (segundo dispositivo):** um segundo aparelho ao lado do celular em viva-voz escuta a
  conversa pelo microfone e legenda. Funciona com qualquer app, com qualidade menor.
