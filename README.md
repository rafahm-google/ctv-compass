# CTV Compass — Mensuração Executiva de CTV no CM360

Portal web auto-hospedado e pipeline de auditoria em Python para agências e anunciantes mensurarem o impacto real de **Connected TV (`CTV`)** diretamente via **Campaign Manager 360 API (`v5`)**, triangulando automaticamente **3 relatórios oficiais** na mesma janela de datas e `Campaign ID`:

1. **`STANDARD`:** Custo de mídia (`DV360 Cost` / `Media Cost`), plataforma física de entrega (`Platform Type`) e conversões diretas de último toque (`Click-Through` + `View-Through`).
2. **`REACH`:** Alcance único deduplicado (`Unique Reach`), *Co-Viewing* na tela grande e sobreposição de audiência (`Reach Overlap 1+`) entre canais e dispositivos.
3. **`PATH_TO_CONVERSION (14 dias)`:** Jornadas completas deduplicadas por pedido (`Conversion ID`), isolando vendas solo, economia de toques até a conversão e expansão de ticket médio (`AOV`).

---

## Visão Dupla de CTV (`Naming do Site` + `Validação por Device Type`)

Por padrão (`identification_mode = "both"`), o **CTV Compass** processa e entrega as duas leituras em **um único deck HTML interativo de 8 slides** (pronto para apresentar no navegador ou exportar em PDF):

* **Visão 1 — Naming do Site (`CTV`):** Avalia os veículos nomeados com `CTV` pela agência no CM360.
* **Visão 2 — Validação por Device Type (`Smart TV + Set-top Box`):** Filtra fisicamente `platformType IN ('Connected TV' [30004], 'Set top box' [30006])` em todos os Sites da campanha, aplica a **Lei da Inclusão-Exclusão Exata** (`|A ∩ B| = |A| + |B| - |U|`) para eliminar dupla contagem `TV ∩ TV` entre veículos e **ativa-se automaticamente como visão principal** quando a campanha não utiliza `CTV` na nomenclatura dos Sites.

Todas as tabelas e cards passam por **5 Travas Matemáticas Automáticas** (`assert` em Python) antes da geração do relatório, com fórmulas abertas (`📐 Como calculamos`) em todos os slides.

---

## Passo a Passo Completo de Implementação (TI / BI da Agência)

A implementação na agência é feita **uma única vez** pelo time técnico (BI, Engenharia de Dados ou TI). Depois de publicado, os analistas de mídia e planejamento usam tudo pelo navegador sem precisar tocar em código ou arquivos JSON.

### Etapa 1 — Garantir Permissões no CM360
A conta Google (de cada analista no Modelo A, ou a Conta de Serviço no Modelo B) precisa ter um **User Profile ativo no CM360** com acesso ao anunciante e permissão para:
* Visualizar campanhas, anunciantes e atividades Floodlight (`dfatrafficking`).
* Criar, executar e baixar relatórios `Standard`, `Reach` e `Path to Conversion` (`dfareporting`).

### Etapa 2 — Configurar Projeto e Credenciais no Google Cloud
1. Acesse o [Google Cloud Console](https://console.cloud.google.com/) e crie (ou selecione) um projeto da agência.
2. Em **APIs e Serviços > Biblioteca**, pesquise e ative a **Campaign Manager 360 API** (`dfareporting.googleapis.com`).
   *(Opcional: caso utilize também reconciliação direta com DV360 via linha de comando, ative a **Display & Video 360 API** e a **DoubleClick Bid Manager API**).*
3. Escolha **um** dos dois modelos de autenticação abaixo:

#### Modelo A (Recomendado) — Login Individual por Usuário (`Entrar com Google` na tela)
Cada analista faz login com seu próprio e-mail corporativo que já tem acesso ao CM360:
1. Em **APIs e Serviços > Tela de permissão OAuth (OAuth consent screen)**:
   * Selecione **Interno** (se todos os usuários forem do Google Workspace da agência) ou **Externo** (adicionando os e-mails autorizados em *Test users* enquanto estiver em modo de teste).
   * Adicione os escopos `.../auth/dfareporting` e `.../auth/dfatrafficking`.
2. Em **APIs e Serviços > Credenciais > Criar Credenciais > ID do cliente OAuth**:
   * Tipo de aplicativo: **Aplicativo da Web (Web application)**.
   * Em **URIs de redirecionamento autorizados (Authorized redirect URIs)**, cadastre:
     * `http://localhost:8080/auth/callback` (para testes locais)
     * `https://SEU-DOMINIO-OU-CLOUD-RUN/auth/callback` (URL final onde o portal ficará hospedado)
3. Copie os valores gerados de **ID do cliente (`GOOGLE_CLIENT_ID`)** e **Chave secreta do cliente (`GOOGLE_CLIENT_SECRET`)**.

#### Modelo B — Conta de Serviço Centralizada no Servidor (Sem Botão de Login)
Ideal quando o BI da agência opera o portal atrás de VPN / Google IAP com um único perfil técnico no CM360:
1. Em **IAM e Admin > Contas de Serviço**, crie uma Service Account e gere uma chave JSON.
2. Copie o e-mail da Service Account (`...@....iam.gserviceaccount.com`) e cadastre-o como um **User Profile** dentro do CM360 com acesso aos anunciantes desejados.
3. No servidor, forneça o conteúdo do JSON na variável `CM360_CREDENTIALS_JSON` (ou o caminho do arquivo em `CM360_CREDENTIALS_FILE`).

---

### Etapa 3 — Hospedar e Colocar o Portal no Ar

> **Nota de Arquitetura:** O portal mantém sessões OAuth e o progresso dos jobs em memória durante a execução (relatórios `Reach` e `Path to Conversion` do CM360 levam de 1 a 4 minutos para processar). Em ambientes serverless como Cloud Run, configure `--timeout 900` e `--max-instances 1` (com `--concurrency 20`) para garantir que o stream de progresso permaneça na mesma instância.

#### Opção 1 — Deploy em 1 comando no Google Cloud Run (Recomendado)
```bash
git clone https://github.com/rafahm-google/ctv-compass.git
cd ctv-compass

gcloud run deploy ctv-compass \
  --source . \
  --region southamerica-east1 \
  --timeout 900 \
  --memory 2Gi \
  --max-instances 1 \
  --concurrency 20 \
  --set-env-vars "GOOGLE_CLIENT_ID=SEU_CLIENT_ID,GOOGLE_CLIENT_SECRET=SEU_CLIENT_SECRET"
```
Após o comando terminar, copie a URL gerada pelo Cloud Run (ex.: `https://ctv-compass-xyz.southamerica-east1.run.app`) e adicione `https://ctv-compass-xyz.southamerica-east1.run.app/auth/callback` nos **URIs de redirecionamento autorizados** do seu OAuth Client no Google Cloud Console.

#### Opção 2 — Deploy via Docker (VM, AWS ECS, Azure ou Servidor Interno)
```bash
docker build -t ctv-compass .

docker run -d --name ctv-compass -p 8080:8080 \
  -e GOOGLE_CLIENT_ID="SEU_CLIENT_ID" \
  -e GOOGLE_CLIENT_SECRET="SEU_CLIENT_SECRET" \
  -e PUBLIC_BASE_URL="https://ctv.suaagencia.com.br" \
  ctv-compass
```
*(Defina `PUBLIC_BASE_URL` sempre que o container estiver atrás de um proxy reverso HTTPS como Nginx, Cloudflare ou Load Balancer).*

#### Opção 3 — Execução Local em Python
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Valida todos os motores matemáticos e rotas HTTP offline (~3s)
python test_self_check.py

# Inicia o portal em http://localhost:8080
export GOOGLE_CLIENT_ID="SEU_CLIENT_ID"
export GOOGLE_CLIENT_SECRET="SEU_CLIENT_SECRET"
python web_app.py
```

---

## O Que Configurar Manualmente? (Na Tela vs. No Código)

Para evitar erros operacionais, veja abaixo **exatamente o que o usuário ajusta na interface a cada estudo** (sem mexer em código) e **quais premissas estão no código Python** caso a agência queira personalizar regras internas.

### A. Ajustes Feitos Direto na Interface Web (Zero Edição de Código)

1. **Conta / Perfil CM360 e Campanha (Passo 1 na tela):**
   * O usuário seleciona o `User Profile` e filtra a campanha pelo nome ou `Campaign ID` (a busca ignora maiúsculas, espaços e `_` underscores).
2. **Nome da Marca / Título no Slide e Nome da Agência (Passo 1 na tela):**
   * O campo **Nome da Marca** vem preenchido com o nome técnico da campanha no CM360 e **Nome da Agência** vem como `"Agência"`. Edite ambos na tela antes de rodar para que os títulos executivos dos 8 slides fiquem limpos para o cliente final.
3. **Janela de Datas (`Data Início` e `Data Fim`):**
   * Preenchida automaticamente com o período oficial da campanha no CM360 (limitada até a data de hoje), podendo ser recortada manualmente na tela.
4. **Seleção das Tags Floodlight de Compra (Passo 2 na tela — CRÍTICO):**
   * **Não é necessário editar código mesmo que o cliente use nomes diferentes de tags.** O Passo 2 lista todas as atividades Floodlight do anunciante com caixas de seleção (`checkboxes`).
   * **Regra de ouro:** mantenha marcada **apenas 1 tag transacional oficial de compra por plataforma** (ex.: 1 de `Web`, 1 de `Android`, 1 de `iOS`). Desmarque sempre pixels agregadores/globais (que disparam junto com a tag de compra e duplicam a receita), tags de funil superior (`view_item`, `add_to_cart`, `lead`) e tags de **outras marcas** que compartilhem o mesmo anunciante/Floodlight Configuration no CM360.

---

### B. Pontos no Código Python que Exigem Edição Manual (Caso Fujam do Padrão)

Se a operação do seu cliente tiver particularidades fora do padrão acima, estes são **todos os pontos do código** que podem ser editados manualmente:

#### 1. Nome dos Sites na Visão 1 (`step2_compute_methodology.py`)
* **Como funciona por padrão:** Na **Visão 1 (`Naming do Site`)**, o código identifica como CTV os veículos cujo `Site (CM360)` contenha a sigla `"ctv"` (linhas `315` e `324` de `step2_compute_methodology.py`).
* **Quando você NÃO precisa mexer:** Se o veículo não tiver `"CTV"` no nome (ex.: `Netflix`, `Disney`, `Globoplay`, `Roku`), a **Visão 2 (`Device Type`)** já detecta automaticamente toda a entrega em `Connected TV` e `Set top box` e assume a abertura do relatório caso nenhum Site tenha `"CTV"` no nome.
* **Quando editar manualmente:** Se a agência quiser que um parceiro sem `"CTV"` no nome entre também na **Visão 1** (ou se um parceiro de CTV for medido apenas por pixel `1x1` sem User-Agent estruturado, caindo em `Unknown platform` na Visão 2), edite o filtro nas linhas `315` e `324` de `step2_compute_methodology.py` (e o fallback na linha `714`):
  ```python
  # Em step2_compute_methodology.py (linhas 315 e 324):
  CTV_SITE_KEYWORDS = ("ctv", "connectedtv", "smarttv", "ott", "netflix", "roku", "globoplay")
  df_sites["is_ctv"] = df_sites["Site (CM360)"].astype(str).str.lower().apply(
      lambda s: any(k in s for k in CTV_SITE_KEYWORDS)
  )
  ```

#### 2. Sugestão Automática Inicial de Tags Floodlight (`common.py`)
* **Como funciona por padrão:** A função `classify_tag()` em `common.py` (linhas `49–57`) define quais checkboxes já aparecem pré-marcados com o selo `"Recomendada"` na tela web (e quais tags são escolhidas automaticamente no modo CLI quando `--purchase-activity-ids` não é informado). Hoje ela busca `in_app_purchase` + `ios`/`android`, ou `comprafeita`, `purchase`, `ordercomplete`, `venda` (excluindo `pixelunico`).
* **Como customizar:** Para adicionar o padrão de nomenclatura da sua agência (ex.: `"checkoutconfirmado"`, `"transacao"`), basta incluir os termos na tupla da linha `55` de `common.py`:
  ```python
  # Em common.py (linha 55):
  if any(k in nlow for k in ("comprafeita", "purchase", "ordercomplete", "venda", "checkoutconfirmado")) and "pixelunico" not in nlow:
  ```

#### 3. Moeda (`R$`) e Formatação Numérica (`common.py`)
* **Como funciona por padrão:** Os valores extraídos seguem a moeda configurada na conta do CM360 (`DV360 Cost (Account Currency)` / `Media Cost`), mas o símbolo impresso nos slides e gráficos está formatado em Reais (`R$`) na função `fmt_curr()` em `common.py` (linhas `105–112`) — e nos rótulos de eixo das linhas `395–397` de `step3_generate_html.py`.
* **Como customizar:** Para contas em `USD` (`US$`), `EUR` (`€`) ou `MXN` (`MX$`), altere o prefixo `"R$"` em `fmt_curr()` no arquivo `common.py`.

#### 4. Múltiplos `Campaign IDs` para o Mesmo Voo de Mídia (`step1` e `step2`)
* **Como funciona por padrão:** Cada execução avalia **1 `Campaign ID`** do CM360. Se a agência dividiu uma mesma campanha em múltiplos IDs no CM360 (ex.: um `Campaign ID` Nacional + um `Campaign ID` Regional), o fluxo padrão gera 1 deck para cada `Campaign ID`.
* **Como customizar (caso precise consolidar vários IDs em um único deck):**
  1. Em `step1_extract_reports.py` (`_build_cm360_specs`, linhas `169–172`), passe múltiplos objetos `{"dimensionName": "campaign", "id": cid, "matchType": "EXACT"}` na lista `camp_filters` (no CM360 v5, filtros repetidos da mesma dimensão operam como `OR`).
  2. Em `step2_compute_methodology.py` (linhas `109`, `291`, `298`, `552` e `566`), troque a comparação `== camp_id` por `.isin(lista_camp_ids)`.

#### 5. Limiares Metodológicos de Pureza e Amostra (`step2_compute_methodology.py`)
* **`CTV_PLATFORM_NAMES`** (linha `27`): `{"Connected TV", "Set top box"}` (IDs `30004` e `30006` no CM360).
* **`PURE_CTV_PLACEMENT_THRESHOLD = 0.95`** (linha `28`): exige ao menos `95%` de entrega em TV/STB em um Placement para tratá-lo como toque determinístico puro de TV no `Path to Conversion` (evitando contaminar a coorte com placements híbridos Mobile + TV).
* **`MIN_MEANINGFUL_CTV_IMPS = 1000.0`** (linha `29`): na Visão Device, agrupa na linha `Residual` os Sites com menos de `1.000` impressões em Smart TV.
* **Amostra mínima de `5` conversões multi-toque** (linhas `188`, `371`, `779`): veículos com menos de `5` conversões observadas em jornadas multi-canal usam como fallback conservador o lift médio do bloco CTV da própria campanha (e canais multi-tela com `"youtube"` no nome herdam o benchmark do canal `YouTube CTV` puro da mesma campanha nas linhas `781–797`).

#### 6. Reconciliação Opcional Direta com a API do DV360 (Modo CLI)
* Na interface web (`web_app.py`, linha `196`), o pipeline opera em modo **100% CM360** (`"dv360": {"enabled": False}`), lendo o custo diretamente de `DV360 Cost` e `Media Cost` no CM360.
* Caso deseje cruzar também Insertion Orders e Line Items diretamente na API do DV360, utilize o modo de linha de comando abaixo passando `--dv360-advertiser-id` ou editando um JSON baseado em `configs/campaign.example.json`.

---

## Uso Opcional via Linha de Comando (CLI)

Além do Portal Web, todo o motor pode ser executado via terminal ou automações:

```bash
# 1. Descobrir metadados da campanha e gerar o JSON de configuração:
python step0_setup_and_discover.py \
  --campaign-id <CAMPAIGN_ID> \
  --mode both \
  --brand-name "Nome da Marca — Campanha" \
  --agency-name "Nome da Agência" \
  --purchase-activity-ids "ID_WEB,ID_ANDROID,ID_IOS"

# 2. Executar extração CM360 + cálculo das 5 travas + geração do deck HTML:
python run_pipeline.py --config configs/camp_<CAMPAIGN_ID>_both.json

# Dica: para recalcular apenas a metodologia/HTML sobre CSVs já baixados:
python run_pipeline.py --config configs/camp_<CAMPAIGN_ID>_both.json --skip-extract
```

---

## Estrutura do Repositório

```text
.
├── web_app.py                    # Portal web auto-hospedado (Login OAuth2 / Service Account + SSE)
├── common.py                     # Utilitários OAuth2, classificação Floodlight, parsers CM360/P2C e moeda
├── step0_setup_and_discover.py   # CLI opcional de autodescoberta de campanha e tags Floodlight
├── step1_extract_reports.py      # Extração paralela de relatórios CM360 v5 (+ DV360 opcional)
├── step2_compute_methodology.py  # Motor matemático CTV ('site', 'device' e 'both') + 5 Travas assert
├── step3_generate_html.py        # Gerador da apresentação executiva HTML interativa + 3 infográficos PNG
├── run_pipeline.py               # Orquestrador CLI do estudo executivo de CTV
├── test_self_check.py            # Auto-teste offline (modos 'site', 'device', 'both' + Servidor Web)
├── configs/
│   └── campaign.example.json     # Modelo comentado de configuração para execução via CLI
├── Dockerfile                    # Imagem pronta para Cloud Run / Docker (usuário não-root)
└── requirements.txt              # Dependências enxutas (pandas, numpy, matplotlib, google-api, oauth)
```

---

## Governança Metodológica & Privacidade

* **Higiene de Floodlight:** Selecione sempre **1 tag transacional oficial de compra por plataforma** (`Web`, `Android`, `iOS`), evitando somar pixels agregadores que disparam no mesmo pedido.
* **Rigor Financeiro:** Superar `1,0x` de ROAS significa gerar mais receita atribuída pela metodologia do que o custo de mídia investido no veículo (não equivale a lucro líquido contábil, pois não desconta CMV, impostos ou frete).
* **Segurança:** Credenciais (`client_secrets*.json`, `token*.json`, `service_account*.json`, `.env`) e dados brutos/relatórios (`*.csv`, `*.html`, `*.png`, `outputs/`, `configs/*.json`) estão bloqueados no `.gitignore` e no `.dockerignore` para nunca serem enviados ao GitHub.
