# 01 — Análise de viabilidade

## A pergunta

> É tecnicamente possível criar um aplicativo que acompanhe uma chamada de vídeo externa (Instagram),
> reconheça o áudio dos dois participantes e apresente legendas traduzidas em tempo real?

**Resposta:** a parte de IA (reconhecer, traduzir e legendar pt-BR ⇄ uk-UA com ~1–2 s de atraso) é viável hoje.
O gargalo é **obter o áudio**. No mesmo celular em que roda a chamada do Instagram, isso **não é confiável
no Android e é impossível no iOS**. Por isso a arquitetura muda o ponto de captura (ver "Alternativas viáveis").

Afirmações marcadas com ⚠️ dependem de versão do sistema/app e precisam ser confirmadas por teste prático
(Spike S0, em [05-custos-roadmap.md](05-custos-roadmap.md)).

---

## Android

### 1. AudioPlaybackCapture API (Android 10+, API 29)

- Captura o áudio que **outros apps reproduzem**, mediante consentimento do usuário via `MediaProjection`
  (a mesma caixa de diálogo de "gravar a tela"). No Android 14+ o consentimento vale por sessão.
- **Limitações decisivas:**
  - Só captura áudio com uso `USAGE_MEDIA`, `USAGE_GAME` ou `USAGE_UNKNOWN`.
    **Áudio de chamada (`USAGE_VOICE_COMMUNICATION`) nunca é capturável por apps de terceiros.**
    Apps de chamada VoIP (Instagram, WhatsApp, Messenger) reproduzem a voz remota com esse uso. ⚠️
  - O app de origem pode recusar captura (`allowAudioPlaybackCapture="false"` ou `setAllowedCapturePolicy`).
  - Requer foreground service do tipo `mediaProjection`, com notificação permanente.
- **Conclusão:** não serve para capturar a voz dela numa chamada do Instagram. Vale um teste de 1 dia para
  documentar o comportamento real, mas o projeto **não depende** disso.

### 2. Microfone (AudioRecord) durante a chamada

- Desde o Android 10 existe uma política de captura simultânea: quando um app de chamada usa o microfone com
  a fonte `VOICE_COMMUNICATION` (considerada sensível à privacidade), **outros apps recebem silêncio**
  enquanto ele estiver ativo. ⚠️ (detalhes variam entre versões 10–15 e fabricantes)
- Mesmo quando há captura, o microfone ouviria só a sua voz (com cancelamento de eco do Instagram,
  a voz dela que sai do alto-falante é removida).
- **Conclusão:** no mesmo aparelho, nem a sua voz é garantida durante a chamada.

### 3. Foreground Service

- Obrigatório para captura contínua em segundo plano: tipo `microphone` (Android 14+ exige declarar o tipo
  e a permissão `FOREGROUND_SERVICE_MICROPHONE`; só pode iniciar com o app visível).
- Funciona bem para os modos BRIDGE (Chamada/Ambiente). Não contorna as restrições acima.

### 4. Overlay (janela flutuante)

- `SYSTEM_ALERT_WINDOW` ("Exibir sobre outros apps") permite legenda flutuante sobre o Instagram.
  Tecnicamente viável — **mas inútil sem áudio**. Será usado no Modo Ambiente (celular com legenda flutuante
  enquanto outro app está aberto) e talvez no futuro.

### 5. Reconhecimento de fala em streaming

- `SpeechRecognizer` do Android (inclusive on-device, `createOnDeviceSpeechRecognizer`, Android 12+)
  suporta pt-BR; suporte on-device a uk-UA depende do pacote de idioma instalado. ⚠️
- whisper.cpp roda on-device via NDK. Ambos serão comparados no benchmark.

### 6. Recursos do próprio sistema

- O "Legenda Instantânea" (Live Caption) do Android/Pixel legenda chamadas porque é **privilegiado** (parte do
  sistema). Apps comuns não têm esse acesso. Suporte de tradução pt⇄uk no Live Caption/Live Translate é
  limitado/inexistente. ⚠️ Pode ser testado como paliativo imediato, sem depender do BRIDGE.

## iOS

- **Sandbox estrito:** nenhum app pode ler o áudio de outro app. Não existe equivalente ao AudioPlaybackCapture.
- **Microfone em segundo plano:** quando o Instagram está em chamada, ele controla a `AVAudioSession`;
  um app em segundo plano não consegue iniciar gravação, e uma gravação já em curso é interrompida.
- **ReplayKit Broadcast Upload Extension:** recebe áudio do app e do microfone durante uma "transmissão de tela".
  Problemas: limite de memória da extensão (~50 MB) impede STT on-device; apps podem excluir seu áudio; o
  comportamento com áudio de chamadas VoIP não é garantido; exige o usuário iniciar a transmissão sempre. ⚠️
  **Não recomendado** como base do produto.
- **Recursos nativos da Apple:** o iOS 26 trouxe "Tradução ao Vivo" em FaceTime/Telefone/Mensagens, mas
  apenas para um conjunto restrito de idiomas; até onde se sabe, **ucraniano não está incluído**. ⚠️
  Não funciona dentro do Instagram.
- **Conclusão:** no iPhone, o BRIDGE só funciona com áudio que ele mesmo capta (Modo Chamada BRIDGE ou Modo
  Ambiente com o app em primeiro plano).

## Desktop (Windows/macOS) — a brecha legítima para o Instagram

- O Instagram permite chamadas de vídeo pelo navegador no computador. ⚠️ (verificar disponibilidade atual)
- **Windows:** WASAPI loopback captura todo o áudio reproduzido no dispositivo de saída — inclusive a voz dela.
- **macOS 13+:** ScreenCaptureKit captura áudio de apps (com permissão de Gravação de Tela);
  macOS 14.2+ oferece Core Audio Taps.
- Microfone em paralelo capta a sua voz. **Dois canais separados = falante identificado sem adivinhar.**
- **Conclusão:** é a única forma confiável de legendar uma chamada do Instagram sem trocar de app.

---

## Alternativas viáveis (escolhidas)

| Modo | Como funciona | Qualidade | Funciona com Instagram? | Complexidade |
|---|---|---|---|---|
| **A. Chamada BRIDGE** | Videochamada dentro do BRIDGE (WebRTC P2P). Cada aparelho transcreve só o seu dono e envia legenda E2EE | ★★★★★ (áudio limpo, sem eco, falante conhecido) | Não — substitui o Instagram | Alta |
| **B. Computador** | Instagram Web no notebook; BRIDGE desktop capta loopback (ela) + microfone (você) | ★★★★ | **Sim** | Média |
| **C. Ambiente / 2º dispositivo** | Celular/tablet extra ao lado do celular em viva-voz; microfone ouve os dois | ★★★ (eco, ruído, compressão do viva-voz) | **Sim** | Baixa |

Observação importante para o Modo C: como cada pessoa fala um idioma diferente, **o idioma detectado já
identifica o falante** (pt ⇒ Cauã, uk ⇒ Katya). Isso simplifica muito a diarização. Um perfil de voz
(embedding) local serve de confirmação.

## Recomendação de plataforma inicial

1. **Spike de validação (Python, notebook/PC)** — prova o pipeline de IA com vozes reais, mede latência e
   qualidade, e já entrega o **Modo Computador** utilizável com o Instagram Web.
2. **App móvel em Flutter (Android primeiro, iOS depois)** — Modo Ambiente (simples) e depois Modo Chamada
   BRIDGE (o produto definitivo).

O que **não** será construído: legenda flutuante "sobre o Instagram" no mesmo celular fingindo ouvir a chamada.
