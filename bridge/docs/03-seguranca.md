# 03 — Modelo de segurança e privacidade

Referências usadas como checklist: **OWASP MASVS (nível L2)**, **OWASP ASVS** (servidor), **OWASP API Security Top 10**.
Regra: **nenhuma criptografia própria** — só bibliotecas consolidadas (libsodium, BoringSSL/WebRTC, Keystore/Keychain).

## 1. Ativos a proteger

| Ativo | Onde existe | Proteção |
|---|---|---|
| Áudio / vídeo da conversa | RAM do aparelho; em trânsito P2P | Nunca gravado; SRTP ponta a ponta |
| Transcrições e traduções | RAM; histórico opcional no aparelho; proxy de tradução (texto em trânsito) | Histórico cifrado, TTL; proxy sem log |
| Chaves de identidade dos aparelhos | Keystore (Android) / Keychain/Secure Enclave (iOS) | Não exportáveis, `ThisDeviceOnly` |
| Chaves de API dos provedores de IA | **Somente** no servidor (variáveis de ambiente / secret manager) | Nunca no app, nunca no Git |
| Perfil de voz (Fase 2) | Aparelho do dono; provedor de TTS se usado | Consentimento explícito, revogável, apagável |

## 2. Atacantes considerados

1. Terceiro na rede (Wi-Fi público, operadora) — interceptação / MITM.
2. Comprometimento do servidor BRIDGE (VPS invadida, provedor de hospedagem curioso).
3. Roubo/perda de um celular.
4. Alguém tentando usar a API do servidor (abuso de custo, força bruta).
5. Provedor de IA na nuvem (vê o que recebe).
6. Dependência maliciosa ou vulnerável (supply chain).

Fora do escopo: aparelho com root/jailbreak controlado por atacante, malware com acessibilidade no aparelho.

## 3. Identidade e pareamento exclusivo

- Na instalação, cada aparelho gera um par de chaves de identidade **Ed25519** (assinatura) e **X25519** (acordo)
  com libsodium. A chave privada é cifrada por uma chave AES-256-GCM guardada no Keystore/Keychain
  (hardware-backed / StrongBox quando disponível).
- **Pareamento presencial ou por vídeo**: aparelho A mostra um **QR code** (chave pública + nonce + endereço do
  servidor); B escaneia e devolve o seu. Ambos exibem um **número de segurança** (hash das duas chaves, ex.: 60
  dígitos ou 6 palavras) que vocês comparam em voz alta. Sem isso, nada conecta.
- O servidor mantém uma **lista de dispositivos autorizados** (só chaves públicas). Máximo configurado: 2 contas,
  poucos aparelhos cada. Cadastro de novos aparelhos exige aprovação assinada por um aparelho já autorizado.
- **Revogação**: qualquer um dos dois pode revogar um aparelho (perdido/roubado); o servidor recusa a chave
  e o parceiro deixa de aceitá-la.

## 4. Autenticação no servidor

- Desafio-resposta: servidor envia nonce → aparelho assina com Ed25519 → servidor verifica contra a lista
  autorizada → emite **token de acesso curto (5–15 min)**, vinculado à chave do aparelho. Sem senhas.
- Rate limiting por aparelho e por IP (autenticação, sinalização, tradução); bloqueio progressivo.
- Limite de gasto diário no proxy de tradução (protege contra abuso de custo mesmo com token roubado).
- Validação estrita de todas as entradas com Pydantic (tamanhos máximos, tipos, idiomas permitidos = {pt, uk}).
- O texto enviado ao LLM é tratado como **dado, não instrução** (delimitado no prompt; o modelo só traduz).
  Isso mitiga injeção de prompt via fala ("ignore as instruções e…").

## 5. Comunicação em trânsito

- **Cliente ⇄ servidor:** TLS **1.3 somente**, HSTS, certificado automático (Caddy/Let's Encrypt).
  Pinning da chave pública do servidor com pin reserva (avaliar risco de bloqueio na rotação).
- **Aparelho ⇄ aparelho (E2EE real):**
  - WebRTC P2P usa **DTLS-SRTP** para mídia e DTLS para o DataChannel. Isso só é ponta a ponta se as
    impressões digitais DTLS não puderem ser trocadas por um intermediário.
  - Por isso, a oferta/resposta SDP (que contém a impressão digital DTLS) é **assinada com a chave de identidade
    Ed25519 pareada** e cifrada com `crypto_box` (X25519 + XSalsa20-Poly1305) para a chave do parceiro.
    Um servidor comprometido não consegue injetar sua própria impressão digital → MITM detectado e chamada recusada.
  - O TURN (coturn) apenas retransmite pacotes SRTP já cifrados.
  - Legendas viajam pelo DataChannel (DTLS autenticado como acima). Opcionalmente uma segunda camada
    `crypto_secretstream` (XChaCha20-Poly1305) com chave derivada do pareamento.
  - Se no futuro houver servidor de mídia (SFU), será necessário SFrame/Insertable Streams — não previsto.
- **O que o servidor vê:** quem conecta com quem, quando e por quanto tempo (metadados) e, no proxy de tradução,
  o texto a traduzir em memória (não registrado). **Não vê** áudio, vídeo nem legendas trocadas entre vocês.

## 6. Transparência com provedores externos

| Configuração | O provedor externo recebe | Fica protegido |
|---|---|---|
| STT local + tradução local (modo privacidade máxima) | Nada | Tudo |
| STT local + tradução por LLM/DeepL (padrão) | **Texto** de cada fala, sem nomes de conta/identificadores | Áudio, voz, vídeo, histórico |
| STT na nuvem | **Áudio** das falas + texto | Vídeo, histórico |
| TTS/clonagem na nuvem (Fase 2) | Texto traduzido + **amostra/modelo de voz** | Vídeo |

- A UI mostra sempre um indicador "☁ processado por <provedor>" quando há envio externo.
- Usar planos de API cujos termos **não usem os dados para treinamento** e com menor retenção disponível
  (verificar política vigente de cada provedor no momento da contratação; solicitar retenção zero quando possível).
- O proxy remove metadados e envia só o necessário (segmento + contexto curto).

## 7. Dados em repouso (no aparelho)

- **Áudio: nunca gravado.** Buffers em RAM, sobrescritos após uso. Nenhum arquivo temporário.
- **Histórico: desligado por padrão.** Se ligado: banco SQLite cifrado (SQLCipher) ou registros AES-256-GCM
  com chave no Keystore/Keychain; expiração automática (ex.: 24 h / 7 dias, configurável); botão "apagar tudo"
  que apaga dados e destrói a chave (crypto-shredding).
- Excluído de backups em nuvem (`android:allowBackup="false"`, `dataExtractionRules`; iOS
  `NSFileProtectionComplete` + exclusão de backup).
- Bloqueio por biometria opcional para abrir o histórico; `FLAG_SECURE` na tela de histórico (impede print/gravação).
- Logs: **nunca** conteúdo de fala, transcrição, tradução ou tokens. Apenas eventos técnicos e métricas
  (latência, códigos de erro). Lint/testes verificam isso.

## 8. Servidor

- Princípio do menor privilégio: containers sem root, sistema de arquivos read-only, só portas 443 e TURN abertas,
  SSH só por chave, firewall, atualizações automáticas de segurança.
- Segredos em variáveis de ambiente fornecidas pelo host (ou secret manager), arquivo `.env` no `.gitignore`;
  **secret scanning** no repositório. Rotação de chaves de API a cada 90 dias ou imediatamente em suspeita.
- Banco do servidor guarda só: chaves públicas dos aparelhos, status de revogação, contadores de rate limit.
- Cabeçalhos de segurança, CORS fechado, sem documentação OpenAPI pública em produção.

## 9. Processo contínuo

- Dependabot/Renovate; `pip-audit`, `osv-scanner`, `flutter pub outdated`; **Semgrep** (SAST); **MobSF** no APK/IPA;
  `gitleaks` para segredos.
- Checklist MASVS antes de cada versão; revisão de segurança a cada mudança de protocolo.
- Plano de resposta: revogar aparelho, rotacionar chaves do servidor e dos provedores, invalidar tokens.

## 10. Consentimento de voz (Fase 2)

- Cada pessoa grava a própria amostra no próprio aparelho, com termo explícito de uso exclusivo para tradução
  entre vocês dois.
- Modelo/perfil de voz vinculado ao aparelho dono; o parceiro só recebe áudio sintetizado, nunca o modelo.
- Revogação apaga o perfil local e solicita exclusão ao provedor (se houver).
