# BRIDGE — protótipo no computador (Modo Computador / Ambiente)

Legendas traduzidas **português ⇄ ucraniano** em tempo real, rodando **100% no seu computador**:
nenhum áudio ou texto vai para a internet, e não há conta nem assinatura para pagar.

| Peça | Tecnologia | Onde roda |
|---|---|---|
| Detecção de voz | Silero VAD | CPU |
| Reconhecimento de fala | Whisper large-v3-turbo (faster-whisper) | GPU NVIDIA |
| Tradução | NLLB-200 1.3B (Meta) via CTranslate2 | GPU NVIDIA |
| Legenda | Janela Tkinter sempre por cima, semitransparente | — |

## O que está pronto e o que não está

**Pronto e testado aqui (Linux, sem GPU, sem microfone):**
- Reconhecimento com gravações reais de falantes nativos (conjunto FLEURS, 20 frases por idioma):

  | Idioma | Erro por palavra (WER) | Idioma identificado certo |
  |---|---|---|
  | Ucraniano | **7,1%** | 20/20 |
  | Português | **2,1%** | 20/20 |

  Parte do "erro" é só formato (ex.: "10" em vez de "dez"). São frases lidas em ambiente limpo;
  conversa real, com gírias e ruído, terá mais erros — meça com as vozes de vocês (ver abaixo).
- Teste de ponta a ponta com uma conversa misturando ucraniano e português: falante identificado
  pelo idioma, tradução nos dois sentidos, e um trecho com nomes estrangeiros marcado como
  "baixa confiança" em vez de ser apresentado como certo. Uma frase partida por uma pausa
  ("Então, Lakkha Singh… | tomou a frente…") é juntada e traduzida inteira.
- Tradução local pt⇄uk, segmentação por pausas, legendas parciais, marcação de incerteza,
  filtro de eco, histórico só em memória, pausa/retomada — 43 testes automáticos passando.
- Janela de legendas (testada em tela virtual).

**Ainda não testado — depende do seu Windows:**
- Captura do microfone e do som do sistema (WASAPI loopback) na sua máquina.
- Aceleração na RTX 3060 Ti (CUDA). Se falhar, o programa usa a CPU automaticamente (mais lento).
- Uso real numa chamada do Instagram no navegador.

## Instalação no Windows 11 (uma vez)

1. **Python 3.12**: baixe em <https://www.python.org/downloads/> e, na instalação, marque
   **"Add python.exe to PATH"**.
2. **Driver da NVIDIA** atualizado (GeForce Experience ou nvidia.com).
3. Baixe este projeto (botão *Code → Download ZIP* no GitHub, branch
   `claude/bridge-bilingual-translation-app-xxydsq`) e extraia.
4. Abra a pasta `bridge\poc` e dê dois cliques em **`instalar.bat`**.
   Ele cria um ambiente Python isolado, instala as dependências, baixa os modelos (~3 GB, uma vez só)
   e verifica a GPU. No final deve aparecer `GPU CUDA encontrada (1)`.

Os modelos ficam em `%LOCALAPPDATA%\bridge\modelos`.

## Uso com chamada do Instagram

1. Abra o Instagram **no navegador** do computador (Chrome/Edge) e inicie a chamada de vídeo.
   (Funciona com qualquer app que toque a voz dela no PC: Instagram Web, WhatsApp Desktop, etc.)
2. **Use fone de ouvido** — assim o microfone não capta a voz dela pela caixa de som.
   (Sem fone, o filtro de eco descarta no seu microfone as falas detectadas em ucraniano.)
3. Dê dois cliques em **`iniciar.bat`**. Em ~30 s aparece a janela de legendas no topo da tela.
4. Feche outros sons do PC (música, vídeos, notificações): o programa ouve **todo** o som do computador.

Controles da janela: arraste pela barra superior · **Espaço** pausa/retoma · **T** alterna
"original + tradução" / "só tradução" · **H** histórico · **Esc** fecha.

### Ela também pode ver legendas
Do jeito atual, só quem roda o programa vê as legendas. Se a Katya tiver um PC com Windows, ela pode
instalar o mesmo programa e rodar:

```
iniciar.bat --eu-nome Katya --eu-idioma uk --parceiro-nome Cauã
```

### Modo ambiente
Um único microfone ouve os dois (ex.: celular em viva-voz ao lado do PC). Quem está falando é
deduzido pelo idioma. Qualidade menor que o modo computador: `iniciar_ambiente.bat`.

## Comandos úteis

Abra o *Prompt de Comando* na pasta `bridge\poc` e ative o ambiente: `.venv\Scripts\activate`

```bat
python -m bridge_poc --diagnostico                 :: GPU encontrada?
python -m bridge_poc --listar-dispositivos         :: nomes de microfones e saídas de som
python -m bridge_poc computador --microfone "Headset" --saida "Fones"
python -m bridge_poc computador --metricas         :: mostra tempos no terminal (sem conteúdo)
python -m bridge_poc arquivo --wav gravacao.wav --sem-interface
python -m bridge_poc --help                        :: todas as opções
pytest                                             :: testes automáticos
```

### Glossário pessoal (nomes, apelidos, correções)
Copie `glossario.exemplo.txt` para `%LOCALAPPDATA%\bridge\glossario.txt` e edite:

- uma palavra por linha → o reconhecimento passa a "esperar" esse nome
  (nomes em cirílico ajudam só o ucraniano; em alfabeto latino, só o português);
- `errado => certo` → correção automática no texto reconhecido e na tradução.

### Frases cortadas
Quando alguém faz uma pausa no meio da frase, o trecho curto (ou terminado em vírgula/reticências)
espera até 1,5 s pela continuação e é traduzido junto com ela. Ajuste com `--juntar-ms 2500`
ou desligue com `--juntar-ms 0`.

### Medir a qualidade com as vozes de vocês
Grave frases (WAV) e coloque, ao lado de cada `frase1.wav`, um `frase1.txt` com o texto exato falado:

```bat
python -m bridge_poc.bench --pasta C:\caminho\gravacoes_katya --lang uk
python -m bridge_poc.bench --pasta C:\caminho\gravacoes_caua --lang pt
```

As gravações são de vocês: não as coloque no GitHub.

## Privacidade

- Áudio fica só na memória RAM, em pedaços, e é descartado após o reconhecimento. Nada é gravado em disco.
- Histórico **desligado por padrão**; quando ligado, fica só na memória, expira em 6 h e some ao fechar.
- Os registros (`--metricas`) mostram apenas tempos e contagens, nunca o que foi dito (há teste para isso).
- A internet só é usada para baixar os modelos na instalação, com versões fixas (commit) do Hugging Face.

## Limitações conhecidas (honestas)

- **Tradução literal**: o NLLB traduz frase a frase, sem contexto da conversa, e às vezes erra o gênero
  ("querida" × "querido") e usa português de Portugal ("a norte de"). Uma opção com IA contextual
  (custo de ~US$ 2/mês) pode ser adicionada depois, se vocês quiserem.
- **Atraso**: a legenda final aparece depois que a pessoa faz uma pausa (~0,5 s de silêncio) mais o
  tempo de processamento. O texto original aparece antes, enquanto ela fala.
- **Gírias, nomes e fala muito rápida** reduzem a precisão; palavras incertas ficam sublinhadas em
  laranja e frases duvidosas aparecem com "≈" e o aviso "baixa confiança".
- NLLB tem licença **CC-BY-NC 4.0**: uso pessoal, não comercial.

## Estrutura

```
bridge_poc/
  audio.py      microfone, loopback (WASAPI) e arquivos WAV → 16 kHz mono
  vad.py        detecção de voz em streaming e segmentação por pausas
  stt.py        Whisper + regras de confiança, idioma restrito a pt/uk, filtro de alucinações
  translate.py  NLLB local
  pipeline.py   liga tudo; filtro de eco; prioridade para falas finais
  history.py    histórico temporário em memória
  ui.py         janela de legendas
  modelos.py    download dos modelos com versão fixa
  bench.py      medição de precisão e tempo
  gpu.py        localiza as bibliotecas CUDA no Windows
tests/          testes automáticos (sem modelos)
```
