# 02 — Arquitetura, tecnologias e fluxo de áudio

## Princípios

1. **Áudio nunca sai do aparelho por padrão.** Só texto transcrito vai para tradução na nuvem (e só se habilitado).
2. **Cada aparelho processa a voz do próprio dono** (Modo Chamada) — elimina eco, diarização e adivinhação de idioma.
3. **Provedores plugáveis** — STT, tradução e TTS atrás de interfaces; local e nuvem intercambiáveis por configuração.
4. **Servidor mínimo e não confiável** — apenas sinalização, TURN e proxy de tradução. Não vê áudio nem vídeo.
5. **Incerteza é exibida, nunca escondida.**

## Visão geral

```
            ┌──────────────── Celular do Cauã ────────────────┐          ┌──────────────── Celular da Katya ───────────────┐
 microfone ─► VAD ─► STT (pt) ─► tradução pt→uk ─► [E2EE] ───┼── P2P ──►┼─► legenda uk  (original pt + tradução uk)        │
            │                                                 │ WebRTC  │                                                  │
            │ legenda pt ◄──────────────────────── [E2EE] ◄───┼─────────┼◄─ tradução uk→pt ◄─ STT (uk) ◄─ VAD ◄─ microfone │
            └─────────────────────────────────────────────────┘          └──────────────────────────────────────────────────┘
                         │ sinalização assinada (sem conteúdo)        │
                         ▼                                            ▼
                 ┌─────────────────────── Servidor BRIDGE (VPS) ───────────────────────┐
                 │ FastAPI: autenticação por chave de dispositivo · sinalização WebRTC │
                 │ coturn (TURN: só retransmite pacotes cifrados)                       │
                 │ proxy de tradução (guarda as chaves de API; não registra conteúdo)   │
                 └──────────────────────────────────────────────────────────────────────┘
```

Modos B (Computador) e C (Ambiente) reutilizam o mesmo núcleo (VAD → STT → tradução → legenda), mudando só a
**fonte de áudio** e o **identificador de falante**:

| Modo | Fonte(s) de áudio | Quem está falando |
|---|---|---|
| A. Chamada BRIDGE | microfone local (só o dono) | sempre o dono do aparelho |
| B. Computador | microfone + loopback do sistema | pelo canal (mic = Cauã, loopback = Katya) |
| C. Ambiente | um microfone para os dois | idioma detectado (pt/uk) + embedding de voz local |

## Fluxo de áudio detalhado (núcleo)

1. **Captura**: PCM 16 kHz mono, 16 bits, buffers de 20–30 ms, mantidos **somente em RAM** (ring buffer).
2. **Pré-processamento**: high-pass, normalização de ganho; supressão de ruído leve (RNNoise) opcional.
   No modo A o WebRTC já aplica AEC/NS/AGC.
3. **VAD** (Silero VAD, ONNX, ~2 MB): detecta início/fim de fala; fim de segmento após ~400–600 ms de silêncio
   ou segmento máximo de ~8–10 s. Sem VAD o Whisper "alucina" frases em silêncio — VAD é obrigatório.
4. **Identificação de idioma**: restrita a **{pt, uk}** (nunca deixar o modelo escolher entre 99 idiomas —
   ucraniano é frequentemente confundido com russo). No modo A o idioma é conhecido; LID só confirma.
5. **STT**:
   - *Parcial* a cada ~0,5–1 s (texto cinza, instável) para dar sensação de tempo real.
   - *Final* ao fim do segmento (texto definitivo), com métricas de confiança (`avg_logprob`, `no_speech_prob`,
     probabilidade por palavra).
6. **Tradução**: só do segmento final (parciais não são traduzidas no MVP, para economizar e evitar flicker).
   Contexto: últimas ~10 falas + glossário do casal (nomes, apelidos, lugares).
7. **Sinalização de incerteza**: palavras com baixa confiança aparecem marcadas (ex.: sublinhado pontilhado / `[?]`);
   se a confiança do segmento for baixa, a tradução aparece como "provável" em vez de definitiva.
8. **Entrega**: legenda local + envio ao parceiro (modo A) por canal de dados cifrado.
9. **Descarte**: buffers de áudio zerados após o STT final. Texto só persiste se o histórico estiver ligado.

### Orçamento de latência (alvo após o fim da frase)

| Etapa | Alvo |
|---|---|
| Detecção de fim de fala (VAD) | 400–600 ms |
| STT final (segmento ~3 s) | 300–900 ms |
| Tradução | 300–800 ms |
| Rede P2P | 50–150 ms |
| **Total** | **p50 ≤ 1,5 s · p95 ≤ 3 s** |

O texto original parcial aparece enquanto a pessoa ainda fala (~0,5–1 s de atraso).

---

## Seleção de tecnologias

### Reconhecimento de fala (STT)

| Opção | Local? | Qualidade pt-BR | Qualidade uk | Streaming | Custo | Observação |
|---|---|---|---|---|---|---|
| **Whisper large-v3-turbo via faster-whisper** (CTranslate2) | Sim (PC/servidor) | Excelente | Boa | Pseudo (VAD + segmentos) | Grátis | Melhor opção local em PC; GPU ajuda, CPU int8 funciona |
| **whisper.cpp** (mesmo modelo, GGUF quantizado) | Sim (celular/PC) | Excelente (medium/turbo) · ok (small) | Boa (turbo) · fraca (small) | Pseudo | Grátis | Em celular top de linha, turbo q5 é próximo de tempo real, mas gasta bateria |
| Android SpeechRecognizer on-device | Sim | Boa | ⚠️ depende do pacote | Real | Grátis | Pouco controle, sem métricas de confiança detalhadas |
| Apple SpeechAnalyzer / SFSpeechRecognizer | Sim/nuvem | Boa | ⚠️ suporte on-device a uk incerto | Real | Grátis | Testar no aparelho dela |
| Google Cloud STT (Chirp) / Azure Speech | Não | Excelente | Muito boa | Real | ~US$ 0,4–1,0/h | Envia **áudio** ao provedor |
| Deepgram / Soniox / OpenAI transcribe | Não | Excelente | Boa–muito boa ⚠️ | Real | ~US$ 0,3–1,0/h | Verificar suporte uk e política de retenção |

**Decisão:** padrão **local** (faster-whisper no PC, whisper.cpp no celular). Nuvem fica como opção explícita,
com aviso visível, para aparelhos fracos. A escolha final do modelo no celular sai do benchmark (Etapa 3).

### Tradução

| Opção | Local? | Qualidade pt⇄uk | Contexto | Latência | Licença / custo |
|---|---|---|---|---|---|
| **LLM via API (Claude Haiku 5.5 / Sonnet 5.5)** | Não | Muito boa / excelente, natural | **Sim** (histórico + glossário + instrução de fidelidade) | ~0,3–1 s | Haiku 5.5: US$ 0,10/0,50 por M tokens; Sonnet 5.5: US$ 2/10 |
| DeepL API | Não | Muito boa (suporta PT-BR e UK) | Parcial (parâmetro `context`) | ~0,3 s | Free 500 mil caracteres/mês; Pro ~€5,49/mês + €20/M caracteres |
| Google Translate API | Não | Boa | Não | ~0,2 s | US$ 20/M caracteres |
| NLLB-200 distilled 600M/1.3B (CTranslate2) | **Sim** | Razoável | Não | 0,2–1 s (CPU) | **CC-BY-NC** (ok para uso privado, não comercial) |
| MarianMT / OPUS-MT | Sim | Limitada para o par pt-uk direto ⚠️ | Não | Rápida | Apache/MIT |
| LLM local pequeno (Gemma/Qwen 3–8B) | Sim | Variável em ucraniano | Sim | Lenta no celular | Varia |

**Decisão:** tradução principal por **LLM via proxy no servidor**, com contexto e prompt de fidelidade
("traduza sem acrescentar nem remover informação; mantenha `[?]` onde a transcrição é incerta; não interprete").
Modelo padrão: **Claude Haiku 5.5** (barato e rápido; esforço `low` para latência); **Sonnet 5.5** como modo
"qualidade". **NLLB local** como fallback offline e como modo "máxima privacidade". DeepL como alternativa
avaliada no benchmark. As chaves ficam **somente no servidor**.

> Privacidade: neste modo o provedor recebe **o texto** das falas (não o áudio). Isso é informado na UI
> (ícone de nuvem + nome do provedor) e pode ser desligado.

### Síntese de voz (Fase 2 — apenas pesquisa por enquanto)

Ver [05-custos-roadmap.md](05-custos-roadmap.md#fase-2--pesquisa-de-voz).

### Desenvolvimento

| Camada | Escolha | Por quê | Alternativas descartadas |
|---|---|---|---|
| App móvel | **Flutter** (Dart) + módulos nativos Kotlin/Swift | Um código para Android e iOS (não sabemos o celular dela); `flutter_webrtc` maduro; FFI para whisper.cpp; UI premium com facilidade | Kotlin puro (só Android); React Native (bom, mas FFI de C++ e áudio em tempo real são mais trabalhosos) |
| Áudio nativo | Kotlin (`AudioRecord`, foreground service) / Swift (`AVAudioEngine`) | Controle de buffers e permissões que o Flutter não oferece | — |
| Spike / desktop | **Python 3.12** (`sounddevice`, `faster-whisper`, `silero-vad`, `soundcard`/WASAPI) | Ecossistema de IA, prototipagem rápida, mede qualidade antes de investir em app | — |
| Servidor | **FastAPI** + WebSocket, **coturn**, **Caddy** (TLS automático) | Pequeno, tipado (Pydantic valida entradas), async | Firebase (dados em terceiros), servidor de mídia SFU (desnecessário para 2 pessoas) |
| Tempo real entre aparelhos | **WebRTC** (mídia + DataChannel) | P2P, DTLS-SRTP, NAT traversal, AEC embutido | WebSocket para áudio (pior latência e criptografia não é E2E) |
| Sinalização | WebSocket sobre TLS 1.3 | Simples; conteúdo da sinalização é assinado/cifrado ponta a ponta | — |

---

## Estrutura de pastas planejada

```
bridge/
├── README.md
├── docs/                      # decisões técnicas (este conjunto) + ADRs futuros
├── poc/                       # Etapa S0/S1: pipeline Python + Modo Computador
│   ├── bridge_poc/
│   │   ├── audio/             # fontes: microfone, loopback (WASAPI/ScreenCaptureKit), arquivo
│   │   ├── vad/               # Silero VAD + segmentador
│   │   ├── stt/               # interface SpeechRecognizer + faster-whisper, nuvem
│   │   ├── translate/         # interface Translator + LLM (via servidor), NLLB, DeepL
│   │   ├── speaker/           # identificação de falante (canal / idioma / embedding)
│   │   ├── ui/                # janela de legenda semitransparente sempre-no-topo
│   │   └── pipeline.py
│   ├── bench/                 # scripts de WER, chrF/COMET, latência
│   └── tests/
├── app/                       # Flutter
│   ├── lib/
│   │   ├── core/              # modelos de domínio (Utterance, Speaker, Confidence), config, DI
│   │   ├── services/
│   │   │   ├── audio/         # ponte para captura nativa
│   │   │   ├── stt/           # whisper.cpp FFI, reconhecedor nativo, nuvem
│   │   │   ├── translation/   # cliente do proxy, NLLB local
│   │   │   ├── transport/     # WebRTC, sinalização
│   │   │   ├── crypto/        # libsodium (sodium_libs), identidade, pareamento
│   │   │   └── storage/       # histórico cifrado, secure storage
│   │   └── features/
│   │       ├── home/  pairing/  call/  ambient/  subtitles/  history/  settings/  privacy/
│   ├── android/               # foreground service, AudioRecord, overlay
│   ├── ios/
│   └── test/  integration_test/
├── server/
│   ├── app/
│   │   ├── auth/              # desafio-resposta com chave do dispositivo, tokens curtos
│   │   ├── devices/           # lista de dispositivos autorizados, revogação
│   │   ├── signaling/         # WebSocket WebRTC
│   │   ├── translate/         # proxy para provedores (sem log de conteúdo)
│   │   └── security/          # rate limit, cabeçalhos, validação
│   └── tests/
├── infra/                     # docker-compose (api, coturn, caddy), configuração TLS
└── .github/workflows/         # testes, lint, pip-audit, osv-scanner, semgrep, dependabot
```

## Decisões registradas (ADR resumido)

| # | Decisão | Motivo |
|---|---|---|
| ADR-001 | Não capturar áudio do Instagram no mesmo celular | Bloqueado por Android/iOS (ver 01) |
| ADR-002 | Três modos (Chamada BRIDGE, Computador, Ambiente) sobre um núcleo comum | Cobrir uso real sem fingir funcionalidade |
| ADR-003 | STT local por padrão | Privacidade; áudio íntimo não sai do aparelho |
| ADR-004 | Tradução por LLM via proxy, NLLB local como fallback | Melhor qualidade contextual; chaves fora do app |
| ADR-005 | Flutter + módulos nativos | Android e iOS com um código |
| ADR-006 | WebRTC P2P com DTLS autenticado por chaves de identidade pareadas | E2EE real em chamada de 2 pessoas |
| ADR-007 | Restringir idiomas a {pt, uk} | Evita confusão uk/ru e aumenta precisão |
