# 04 — Plano de testes

Princípio: **toda métrica é medida com áudio real**, não com texto digitado. Os testes automatizados usam
conjuntos públicos; os testes com as vozes de vocês ficam **fora do Git** (pasta local cifrada, com consentimento).

## Dados de teste

| Conjunto | Uso | Observação |
|---|---|---|
| **FLEURS** (Google) pt_br, uk_ua | WER de STT; mesmas frases nos dois idiomas → tradução | Licença CC-BY |
| **Common Voice** pt, uk | Variedade de vozes e sotaques | CC0 |
| **FLORES-200** por_Latn ⇄ ukr_Cyrl | Qualidade de tradução (chrF++, COMET) | CC-BY-SA |
| **MUSAN** / ruído gravado (TV, rua, cozinha) | Ruído de fundo a 20/10/5 dB SNR | |
| Gravações próprias (~30 frases cada, com gírias, apelidos, nomes) | Teste realista do casal | Nunca no repositório |
| Conversas roteirizadas (pausas, interrupções, falas sobrepostas, fala rápida) | Pipeline completo | Gravadas pelos dois |

## Matriz de testes

| Área | Teste | Métrica / critério inicial |
|---|---|---|
| STT português | FLEURS pt_br + gravações próprias | WER ≤ 10% (limpo) |
| STT ucraniano | FLEURS uk_ua + gravações próprias | WER ≤ 15% (limpo) |
| Identificação de idioma | Segmentos mistos pt/uk, curtos (1–2 s) | ≥ 97% correto em segmentos ≥ 2 s; nunca "russo" |
| Identificação de falante | Modo C com duas vozes no mesmo microfone | ≥ 95% de segmentos atribuídos corretamente |
| Tradução pt→uk e uk→pt | FLORES + frases do casal; revisão humana por falante nativo (ela avalia uk, você avalia pt) | chrF++/COMET comparando LLM × DeepL × NLLB; nota humana ≥ 4/5 |
| Fidelidade | Frases com números, datas, negações, nomes | 0 erros de negação/número em 100 frases |
| Incerteza | Áudio com palavras mascaradas por ruído | Texto marcado `[?]`; nunca palavra inventada sem marcação |
| Pausas | Frases com pausas longas no meio | Segmento não corta no meio da ideia em > 90% |
| Fala rápida | Áudio acelerado 1,25× e 1,5× | Degradação de WER registrada |
| Interrupções | Um fala por cima do outro (modo A e C) | Sem travamento; ambos legendados |
| Ruído | SNR 20/10/5 dB | WER registrado por nível; alvo utilizável a 10 dB |
| Silêncio | 10 min sem fala | 0 legendas fantasmas (alucinação) |
| Falha de conexão | Derrubar Wi-Fi, alternar 4G/Wi-Fi, perder servidor | Reconecta ≤ 10 s; STT local continua; aviso visível |
| Latência | Instrumentação fim-de-fala → legenda na tela do outro | p50 ≤ 1,5 s; p95 ≤ 3 s |
| Bateria | Chamada de 60 min (Android Battery Historian / Xcode Energy) | ≤ 15–20%/h no modo A (meta a validar) |
| Estabilidade | Chamada de 2 h | Sem vazamento de memória, sem crescimento de latência |
| Segurança — armazenamento | Inspecionar sandbox do app após uso | Nenhum áudio; histórico só cifrado; nada em logs |
| Segurança — rede | mitmproxy com CA própria; servidor modificado trocando fingerprint DTLS | Conexão recusada em ambos |
| Segurança — API | Token expirado/revogado, chave não autorizada, payload gigante, flood | 401/403/413/429 corretos |
| Segurança — dependências | pip-audit, osv-scanner, Semgrep, gitleaks, MobSF | Sem vulnerabilidade alta aberta |

## Tipos de teste

- **Unitários**: segmentador VAD, montagem de contexto, marcação de incerteza, cifra/decifra do histórico,
  verificação de assinatura, validação de entrada.
- **Contrato**: interfaces `SpeechRecognizer`, `Translator`, `Transport` com implementações falsas (fakes),
  permitindo testar o pipeline sem rede nem modelos.
- **Integração**: pipeline completo com arquivos de áudio (determinístico, roda no CI com modelo pequeno).
- **Benchmark** (`poc/bench`): WER, chrF/COMET, latência por etapa — gera relatório comparativo de provedores.
- **Manual roteirizado**: chamadas reais entre vocês com checklist.

## Como executar (planejado — comandos passam a valer quando o código existir)

```bash
# Spike Python
cd bridge/poc && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"
pytest                               # unitários + integração
python -m bench.stt --dataset fleurs --langs pt,uk --model large-v3-turbo
python -m bench.translate --dataset flores --pairs pt-uk,uk-pt --providers llm,deepl,nllb

# Servidor
cd bridge/server && pytest

# App
cd bridge/app && flutter test && flutter test integration_test
```
