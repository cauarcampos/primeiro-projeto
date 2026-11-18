# 05 — Custos, roadmap e pesquisa das Fases 2 e 3

## Custos estimados (mensais, uso de ~30 h de conversa/mês)

Preços de referência de nov/2026; confirmar na contratação. Estimativa de 1 h de conversa ≈ 9 mil palavras
≈ 50–60 mil caracteres.

| Item | Opção | Estimativa |
|---|---|---|
| Servidor (API + sinalização + TURN) | VPS pequena (2 vCPU, 2–4 GB) | US$ 5–10/mês |
| Domínio | — | ~US$ 1/mês |
| STT | Local (padrão) | **US$ 0** (custo em bateria/CPU) |
| STT | Nuvem (opcional, só fala com VAD) | ~US$ 10–40/mês |
| Tradução | Claude Haiku 5.5 (US$ 0,10 entrada / 0,50 saída por M tokens), ~0,6 M tokens entrada/h com contexto | **~US$ 0,07/h → ~US$ 2/mês** |
| Tradução | Claude Sonnet 5.5 (US$ 2 / 10 por M tokens) — modo qualidade | ~US$ 1,5/h → ~US$ 45/mês |
| Tradução | DeepL API Pro (~1,7 M caracteres) | ~€ 40/mês (ou Free até 500 mil caracteres) |
| Tradução | NLLB local | US$ 0 |
| iPhone (se ela usar) | Apple Developer Program | US$ 99/ano (necessário para instalar sem expirar a cada 7 dias) |
| Android | Instalação direta do APK (sem Play Store) | US$ 0 |
| **Total MVP típico** | STT local + Haiku 5.5 + VPS | **≈ US$ 10–15/mês** (+ Apple, se aplicável) |
| Fase 2 (voz clonada na nuvem) | ex.: ElevenLabs, ~1,5 M caracteres/mês | ~US$ 100–330/mês ⚠️ — por isso a pesquisa prioriza opções locais |

Prompt caching da instrução fixa e do glossário reduz o custo de entrada do LLM.

## Roadmap

### S0 — Spikes de viabilidade (1–2 semanas)
- [ ] Testar no Android real: AudioPlaybackCapture e microfone durante chamada do Instagram (documentar resultado esperado: bloqueado).
- [ ] Testar Instagram Web no notebook + captura loopback (Windows/macOS).
- [ ] Pipeline Python: microfone/arquivo → Silero VAD → faster-whisper (large-v3-turbo, idiomas {pt, uk}) → tradução → terminal.
- [ ] Gravar o conjunto de frases do casal e medir WER/latência reais.
- **Critério de saída:** WER e latência dentro dos alvos de 04-testes.md com as vozes de vocês.

### S1 — Modo Computador utilizável (2–3 semanas) — primeiro uso real com o Instagram
- [ ] Captura em dois canais (mic = Cauã, loopback = Katya).
- [ ] Janela de legenda semitransparente, sempre no topo, original + tradução, indicador de processamento/incerteza.
- [ ] Servidor mínimo: proxy de tradução autenticado (chaves fora do cliente), TLS 1.3, rate limit.
- [ ] Pausar/retomar, apenas tradução / original + tradução, histórico opcional cifrado.

### S2 — App móvel, Modo Ambiente (3–4 semanas)
- [ ] Flutter: tela inicial, permissões, foreground service, whisper.cpp FFI, legendas, privacidade.
- [ ] Identificação de falante por idioma + embedding local.
- [ ] Pareamento por QR + número de segurança; lista de dispositivos; revogação.

### S3 — Modo Chamada BRIDGE (4–6 semanas)
- [ ] WebRTC P2P com SDP assinado/cifrado, coturn, reconexão.
- [ ] STT local por aparelho, legendas pelo DataChannel.
- [ ] Testes de segurança (MITM, servidor malicioso), bateria, chamadas de 2 h.

### S4 — Fase 2 (voz) e Fase 3 (conversa natural) — só após MVP estável

Prazos são estimativas para uma pessoa em tempo parcial com apoio de IA.

## Fase 2 — pesquisa de voz

| Tecnologia | Local? | pt-BR | uk | Clonagem | Streaming | Licença / observação |
|---|---|---|---|---|---|---|
| **Piper** | Sim (até em celular) | Sim | Sim | Não | Sim, muito rápido | MIT; vozes genéricas — bom fallback |
| **XTTS-v2 (Coqui)** | Sim (GPU) | Sim | **Não** | Sim (6 s de amostra) | Sim | CPML não comercial; empresa encerrada em 2024 — sem ucraniano, inviável para a voz dele em uk |
| **OpenVoice v2** | Sim | Via TTS base | Via TTS base | Converte timbre (tone color) independente do idioma | Quase | MIT; combinação Piper uk + conversão de timbre é a hipótese local mais promissora |
| **Seamless (M4T v2 / Streaming)** | Sim (GPU) | Sim | Sim | Expressive não cobre uk | Sim (Streaming) | CC-BY-NC; speech-to-speech direto |
| **ElevenLabs** (Multilingual / Flash) | Não | Sim | Sim | Sim, cross-lingual, exige verificação/consentimento | Sim, baixa latência | Melhor qualidade hoje, custo alto, voz vai ao provedor |
| Azure Personal Voice | Não | Sim | ⚠️ | Sim, acesso restrito com consentimento gravado | Sim | Requer aprovação da Microsoft |
| Speech-to-speech em tempo real via APIs de LLM de voz | Não | Sim | ⚠️ | Vozes fixas | Sim | Sem preservação de identidade |

**Plano de pesquisa:** (1) baseline Piper (genérico, local); (2) Piper + OpenVoice v2 com amostras dos dois,
avaliação cega por vocês; (3) ElevenLabs como referência de qualidade; decidir por custo × naturalidade × privacidade.
Na chamada BRIDGE, o áudio traduzido substitui (ou é mixado sob) a voz original no fluxo WebRTC.

## Fase 3 — conversa natural

- Tradução incremental por "unidades estáveis" (política *local agreement*: só traduz o prefixo que se repetiu
  em duas hipóteses parciais consecutivas) → legenda que cresce sem reescrever tudo.
- Correção contextual: a tradução de uma fala pode ser revisada quando a seguinte muda o sentido; a UI mostra a
  correção discretamente (nunca muda o significado silenciosamente).
- Memória de contexto da conversa (últimas falas + glossário) só no aparelho; o servidor recebe janela curta.
- Detecção de troca de turno e interrupções via VAD dos dois lados (modo A tem um VAD por pessoa).
- Sincronização legenda ⇄ áudio sintetizado por timestamps dos segmentos.

## Perguntas em aberto (decisões de vocês)

1. Quais celulares cada um usa (Android/iPhone, modelo)? Define viabilidade de STT on-device e se o iOS entra cedo.
2. Algum dos dois tem notebook/PC? (Modo Computador é o caminho mais rápido para usar com o Instagram.)
3. Topam fazer as chamadas pelo próprio BRIDGE no futuro, em vez do Instagram?
4. Aceitam que o **texto** (não o áudio) passe por um provedor de tradução na nuvem para ter melhor qualidade,
   ou preferem 100% local com qualidade menor?
5. Orçamento mensal aceitável.
