# Metodologia — PLI Reporta

Documento conceitual que define **como** os reportes cidadãos são qualificados,
hierarquizados e integrados ao cálculo de rotas. Este texto é a referência única
para qualquer decisão de implementação. Toda regra do código aponta para uma
seção daqui.

## 1. Premissas

1. A unidade de análise é o **incidente geoespacial verificável**, não o questionário.
2. Cada incidente possui ciclo de vida: `submetido → triado → validado → publicado → expirado/resolvido`.
3. O sistema deve ser auditável: toda decisão automática registra os sinais que a produziram.
4. O cálculo de rotas é cliente do feed; não conhece a origem do dado.
5. O usuário tem direito de saber por que seu reporte foi aceito, modificado ou descartado.

## 2. Cadeia de qualificação

Cada reporte passa por dois scores **independentes e ortogonais**:

```
   captura ──► VERACIDADE (V)  ──► é real?
                                       │
                                       ▼
                            RELEVÂNCIA (R) ──► importa para a rota?
                                       │
                                       ▼
                            PRIORIDADE (P) ──► quão antes deve refletir no grafo?
```

Separar V e R é deliberado: um buraco minúsculo numa rua sem volume é **verdadeiro**
mas **irrelevante**; uma denúncia de bloqueio em corredor estratégico é **muito relevante**
mesmo se a confiança individual for moderada (até a reconfirmação chegar).

## 3. Veracidade (V)

Score `V ∈ [0,1]` com sinais ponderados. Cada sinal `s_i ∈ [0,1]` com peso `w_i`:

```
V = Σ (w_i · s_i) / Σ w_i
```

### 3.1 Sinais

| Sinal | Como medir | Peso |
|---|---|---|
| `s_geo_browser` | GPS do navegador no envio com `accuracy < 50 m` → 1.0; `< 200 m` → 0.5; sem GPS → 0.0 | 0.20 |
| `s_exif_match` | EXIF GPS coerente com GPS do navegador (Δ < 100 m) e timestamp Δ < 5 min → 1.0; só EXIF presente sem coerência → 0.3; sem EXIF → 0.5 (não pune ausência, pune incoerência) | 0.15 |
| `s_capture_inapp` | Foto capturada via `getUserMedia` com nonce server-side válido → 1.0; upload de galeria → 0.4 | 0.20 |
| `s_road_snap` | Distância da posição à aresta navegável OSM mais próxima `< 30 m` → 1.0; `< 100 m` → 0.6; `> 200 m` → 0.0 | 0.10 |
| `s_image_integrity` | ELA + checagem de software EXIF (Photoshop, GIMP) → 1.0 se limpo, 0.0 se evidência de edição | 0.15 |
| `s_user_reputation` | Reputação do contribuinte normalizada (ver §6) | 0.10 |
| `s_temporal_plausibility` | Reporte enviado dentro de 30 min da captura → 1.0; até 2 h → 0.6; > 24 h → 0.2 | 0.10 |

Pesos somam 1.00. Soma é normalizada por segurança.

### 3.2 Gates

```
V < AUTO_DISCARD_THRESHOLD          → status = "descartado"
AUTO_DISCARD_THRESHOLD ≤ V < AUTO_PUBLISH_THRESHOLD → status = "em_moderacao"
V ≥ AUTO_PUBLISH_THRESHOLD          → status = "validado"
```

Defaults: `0.30` e `0.70`. Configuráveis por `.env`.

### 3.3 Por que esses sinais

- **GPS do navegador é mais confiável que EXIF** porque é coletado pelo nosso código no momento do envio; EXIF é trivialmente forjável.
- **Exigir foto in-app** elimina a maior fonte de fraude (subir foto antiga ou de outra cidade). EBU e literatura de jornalismo forense convergem nesse ponto.
- **Snap à malha viária** valida que o reporte é fisicamente plausível como problema de transporte. Reporte no meio de uma fazenda recebe sinal baixo.
- **Reputação** transforma contribuintes recorrentes em validadores implícitos sem virar barreira para novatos.

## 4. Relevância (R)

Score `R ∈ [0,1]` com quatro fatores multiplicativos suaves:

```
R = R_severidade · R_confirmacao · R_persistencia · R_afetacao
```

### 4.1 Severidade por categoria

Tabela base. `R_severidade` é o valor da categoria, ajustado por magnitude declarada.

| Categoria | R_sev base | TTL default | Bloqueia aresta? |
|---|---|---|---|
| `bloqueio_total` | 1.00 | 6 h | sim, se V·R > 0.8 |
| `acidente` | 0.85 | 2 h | não, mas penaliza forte |
| `alagamento` | 0.85 | 12 h | sim, se V·R > 0.85 |
| `obra_grande` | 0.70 | 30 dias | não, penaliza |
| `lentidao_corredor` | 0.65 | 1 h | não, penaliza |
| `sinalizacao_quebrada` | 0.50 | 14 dias | não |
| `buraco` | 0.40 | 90 dias | não |
| `outro` | 0.30 | 7 dias | não |

`R_severidade` final = `R_sev_base × magnitude_declarada` (1.0 default, 1.2 se "grave", 0.7 se "leve"), trava em `[0,1]`.

### 4.2 Confirmação independente

Função sigmoide do número de reportes distintos (contribuintes diferentes) no mesmo
cluster espaço-temporal (raio `r=80 m`, janela `Δt` por categoria):

```
R_confirmacao = 0.5 + 0.5 · (1 - exp(-k · n))      com k = 0.6
```

| n confirmações | R_confirmacao |
|---|---|
| 1 | 0.50 |
| 2 | 0.65 |
| 3 | 0.75 |
| 5 | 0.88 |
| 10 | 0.99 |

Reportes confirmadores também elevam a **prioridade** de processamento.

### 4.3 Persistência temporal

Penaliza reportes muito velhos sem reconfirmação:

```
R_persistencia = exp( - idade_horas / TTL_horas )
```

Quando `R_persistencia < 0.1`, o incidente é movido para `expirado`. Nova confirmação reseta o relógio.

### 4.4 Afetação viária

Pondera pelo papel da via no grafo (hierarquia OSM `highway=*`). Função monótona:

| Hierarquia OSM | R_afetacao |
|---|---|
| `motorway`, `trunk` | 1.00 |
| `primary` | 0.85 |
| `secondary` | 0.70 |
| `tertiary` | 0.55 |
| `residential`, `unclassified` | 0.35 |
| `service`, `track` | 0.15 |

Quando o roteador integra dados de volume (contagens, V/C ratio), `R_afetacao` é
substituído por uma função do volume normalizado.

## 5. Prioridade (P) e impacto no roteamento

`P = V · R` — combinação simples e interpretável.

### 5.1 Aplicação no peso da aresta

Para cada aresta `e` afetada por incidentes ativos `I_e = {i₁, i₂, ...}`:

```
penalty_e = max( P_i ) para i ∈ I_e        # toma o pior caso, não soma
w'_e = w_e · (1 + α · penalty_e)            # α default = 3.0 → até 4× o custo
```

Bloqueio total é tratado à parte:

```
se existe i ∈ I_e com categoria ∈ BLOQUEANTES e P_i > 0.80:
    e é removida do grafo durante o cálculo
```

### 5.2 Por que `max` e não soma

- `max` evita que vários reportes irrelevantes empilhem peso indevido.
- Reflete realidade física: a aresta tem o pior problema reportado, não a média.
- Robusto contra ataques de inflação por bots no mesmo ponto.

### 5.3 Por que multiplicativo e não aditivo

- Mantém escala original do peso (tempo, distância). Um corredor lento penalizado fica proporcionalmente mais lento, não absurdamente lento.
- Facilita explicação ao usuário do roteador: "rota desviada porque trecho X está 3× mais custoso".

## 6. Reputação do contribuinte

Reputação `ρ ∈ [0,1]` por usuário (anônimos compartilham `ρ=0` e nunca crescem).

```
ρ = clip( base + Σ (resultado_i · w_resultado) , 0, 1 )

resultados:
  reporte publicado ........ +0.02
  reporte confirmado por outros .. +0.05
  reporte resolvido pela autoridade .. +0.08
  reporte descartado ......... -0.10
  reporte marcado como abuso ... -0.30
```

Estabiliza por suavização exponencial em janelas de 30 dias para evitar volatilidade.

## 7. Deduplicação e clusterização

DBSCAN espacial restrito por categoria e janela temporal. Para cada novo reporte:

1. Buscar reportes ativos da mesma categoria a `≤ 80 m` e dentro da janela `Δt(categoria)`.
2. Se existir cluster compatível: anexa como `confirmation` em vez de criar novo incidente. Atualiza `R_confirmacao`.
3. Se não existir: cria novo incidente.

Edge case: dois eventos reais no mesmo ponto em horas diferentes (ex.: dois acidentes no mesmo cruzamento). Janela temporal por categoria resolve.

## 8. Hierarquização para o roteador — regra final

Dado um conjunto de incidentes ativos, o feed exposto ao roteador segue:

1. **Filtra** `status ∈ {validado, publicado}` e `valid_to > now`.
2. **Calcula** `P = V · R` para cada incidente.
3. **Anexa** `affected_edges` por snap (raio adaptativo: 30 m default, 60 m se `R_afetacao ≥ 0.85`).
4. **Ordena** por `P` decrescente quando há conflito de aresta (uma aresta com vários incidentes mantém o de maior `P`).
5. **Marca** como bloqueante se categoria ∈ `{bloqueio_total, alagamento}` e `P > 0.80`.
6. **Publica** GeoJSON com TTL nos headers HTTP (Cache-Control conforme `min(valid_to - now, 60s)`).

## 9. Equidade e mitigação de viés

Evidência mostra que plataformas de reporte cidadão amplificam vozes de áreas mais ricas e digitalmente conectadas. Contramedidas:

- **Painel de cobertura** por município/microrregião com semáforo: verde (densidade adequada), amarelo (subnotificada), vermelho (silenciosa).
- **Modo agente de campo** para parceiros institucionais (DER, prefeituras, motoristas profissionais), com reputação elevada por padrão e cota de reportes em áreas vermelhas.
- **Onboarding presencial** nos workshops regionais do PLI, com QR para instalar a PWA.
- **Não usar** densidade de reportes como proxy direto de problema; sempre normalizar por população, frota, ou km de via.

## 10. Privacidade e segurança

- Foto pode conter pessoas e placas. **Borrar faces e placas server-side** antes de publicar (pipeline de visão computacional, fora do MVP, mas previsto).
- EXIF do contribuinte é despojado na publicação; mantemos só o necessário no banco.
- Dados pessoais (e-mail, telefone) são opcionais e nunca expostos no feed público.
- O nonce de captura usa `itsdangerous` com TTL curto (5 min) para evitar replay.

## 11. Indicadores de qualidade do sistema

A operação acompanha:

- Taxa de publicação automática (alvo: 50–70%).
- Taxa de descarte automático (alvo: 10–20%).
- Tempo mediano até validação (alvo: < 10 min para alta prioridade).
- Cobertura geográfica (Gini espacial dos reportes vs. população).
- Taxa de confirmação (% de incidentes com n ≥ 2).
- Concordância com fontes autoritativas (DER, CET) por amostragem.

## 12. O que está fora do MVP (v1)

- Borramento automático de faces/placas (entra na v2).
- Detecção de imagem gerada por IA (entra na v2).
- Login social e reputação avançada (entra na v1.1).
- Snap à malha viária estadual completa de SP (MVP usa um GeoJSON local opcional; v1.1 integra OSRM/PBF).

## 13. Referências de fundamentação

A escolha das estratégias acima é apoiada por evidência sobre PPGIS/VGI, mobile crowdsensing, validação de imagem por EXIF/ELA e plataformas operacionais de incidentes (Waze, FixMyStreet, SeeClickFix). Lista completa em `docs/REFERENCIAS.md`.
