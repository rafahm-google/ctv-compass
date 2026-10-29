# ctv-compass

Serviço HTTP e pipeline CLI em Python para mensuração de campanhas de Connected TV (CTV) sobre a API do Campaign Manager 360 (`dfareporting` v5).

O pipeline extrai e reconcilia três relatórios do CM360 na mesma janela de datas e `Campaign ID`:
1. `STANDARD`: custo (`DV360 Cost` / `Media Cost`), `Platform Type` e conversões de último toque (`Click-Through` e `View-Through`).
2. `REACH`: `Unique Reach` deduplicado, `Co-Viewed Reach` e sobreposição cross-channel / cross-device (`Duplicate Impression Reach`).
3. `PATH_TO_CONVERSION`: jornadas deduplicadas por `Conversion ID`, vendas solo, toques médios até a conversão e ticket médio (`AOV`).

Por padrão (`identification_mode="both"`), a saída é um arquivo HTML único autocontido (imagens renderizadas em `matplotlib` embutidas em Base64) com duas visões comutáveis:
- `site`: classifica CTV pelo nome do `Site (CM360)`.
- `device`: filtra `platformType IN ('Connected TV' [30004], 'Set top box' [30006])` em todos os Sites da campanha, calcula a interseção `|CTV ∩ Non-CTV| = |CTV| + |Non-CTV| - |Total|` para remover sobreposição `TV ∩ TV` e assume como aba padrão caso nenhum Site possua `CTV` no nome.

---

## Requisitos

- Python `>= 3.10`
- Projeto no Google Cloud com a API `dfareporting.googleapis.com` habilitada (opcionalmente `displayvideo.googleapis.com` e `doubleclickbidmanager.googleapis.com` caso utilize enriquecimento DV360 via CLI)
- Conta Google ou Service Account vinculada a um `User Profile` ativo no CM360 com escopos:
  - `https://www.googleapis.com/auth/dfareporting`
  - `https://www.googleapis.com/auth/dfatrafficking`

---

## Configuração de Autenticação e Variáveis de Ambiente

O servidor HTTP (`web_app.py`) suporta dois modos de autenticação mutuamente exclusivos (priorizando OAuth 2.0 Web Client caso ambos estejam definidos):

1. **OAuth 2.0 Web Application (login individual por usuário):**
   No Google Cloud Console (`APIs & Services > Credentials`), crie um `OAuth client ID` do tipo `Web application` e registre `<BASE_URL>/auth/callback` (ex.: `http://localhost:8080/auth/callback` e `https://<dominio>/auth/callback`) em `Authorized redirect URIs`.
2. **Service Account / Credencial de Servidor (sem tela de login):**
   Cadastre o e-mail da Service Account como `User Profile` no CM360 com acesso aos anunciantes alvo e injete o JSON via variável de ambiente. Recomenda-se restringir o acesso de rede ao serviço via Cloud Run IAM, IAP ou VPN.

| Variável | Obrigatória | Descrição |
| :--- | :--- | :--- |
| `PORT` | Não | Porta de escuta HTTP (padrão: `8080`). |
| `GOOGLE_CLIENT_ID` | Modo OAuth | Client ID do OAuth 2.0 Web Application. |
| `GOOGLE_CLIENT_SECRET` | Modo OAuth | Client Secret do OAuth 2.0 Web Application. |
| `GOOGLE_CLIENT_SECRETS_FILE` | Não | Alternativa local às variáveis acima (padrão procurado: `client_secrets.json`). |
| `PUBLIC_BASE_URL` | Não | URL externa canônica (ex.: `https://ctv.agencia.com.br`) usada para montar `redirect_uri` atrás de proxies reversos. |
| `CM360_CREDENTIALS_JSON` | Modo Server | String JSON completa da Service Account ou `authorized_user`. |
| `CM360_CREDENTIALS_FILE` | Modo Server | Caminho no disco para o JSON da Service Account ou `authorized_user`. |
| `ALLOW_LOCAL_TOKEN` | Não | Se `true`/`1`, permite ler `token.json` local no modo servidor (uso em desenvolvimento). |

---

## Execução e Deploy

### Local
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Executa a suíte de validação offline (invariantes matemáticas + servidor HTTP)
python test_self_check.py

export GOOGLE_CLIENT_ID="..."
export GOOGLE_CLIENT_SECRET="..."
python web_app.py
```

### Docker
```bash
docker build -t ctv-compass .
docker run --rm -p 8080:8080 \
  -e GOOGLE_CLIENT_ID="..." \
  -e GOOGLE_CLIENT_SECRET="..." \
  -e PUBLIC_BASE_URL="https://ctv.exemplo.com" \
  ctv-compass
```

### Google Cloud Run
Sessões OAuth (`_SESSIONS`) e jobs em execução (`_JOBS`) são mantidos na memória do processo, e relatórios `REACH` / `PATH_TO_CONVERSION` no CM360 podem levar de 1 a 4 minutos para finalizar. Configure `--timeout 900` e `--max-instances 1` (ou afinidade de sessão):

```bash
gcloud run deploy ctv-compass \
  --source . \
  --region southamerica-east1 \
  --timeout 900 \
  --memory 2Gi \
  --max-instances 1 \
  --concurrency 20 \
  --set-env-vars "GOOGLE_CLIENT_ID=...,GOOGLE_CLIENT_SECRET=..."
```
Após o deploy, adicione `https://<service-url>/auth/callback` em `Authorized redirect URIs` no Google Cloud Console.

### Linha de Comando (CLI)
```bash
# 1. Descobrir campanha/Floodlights e gerar arquivo de configuração em configs/
python step0_setup_and_discover.py \
  --campaign-id <CAMPAIGN_ID> \
  --mode both \
  --brand-name "Marca" \
  --agency-name "Agencia" \
  --purchase-activity-ids "ID_WEB,ID_ANDROID,ID_IOS"

# 2. Extrair relatórios, computar métricas e renderizar HTML
python run_pipeline.py --config configs/camp_<CAMPAIGN_ID>_both.json

# Recalcular apenas metodologia e HTML reutilizando os CSVs já extraídos em outputs/
python run_pipeline.py --config configs/camp_<CAMPAIGN_ID>_both.json --skip-extract
```

---

## Parâmetros Manuais e Pontos de Customização no Código

### 1. Parâmetros Definidos por Execução (Sem Alteração de Código)
Na interface web (`web_app.py`) ou no JSON de configuração (`configs/campaign.example.json`):
- `profile_id` e `campaign_id`: perfil de usuário e campanha alvo no CM360.
- `start_date` e `end_date`: janela de análise (`YYYY-MM-DD`), preenchida inicialmente com as datas da campanha.
- `brand_name` e `agency_name`: rótulos textuais exibidos no cabeçalho dos slides.
- `identification_mode`: `both` (padrão), `site` ou `device`.
- `purchase_activity_ids`: lista de `Activity IDs` do Floodlight contabilizadas como conversão. Na UI, todas as atividades do anunciante são carregadas da API em checkboxes; selecione apenas **1 atividade transacional de compra por plataforma** (`Web`, `Android`, `iOS`), desmarcando pixels agregadores (que disparam em duplicidade no mesmo pedido), eventos de topo/meio de funil e tags de outras marcas que compartilhem o mesmo `floodlightConfigurationId`.

### 2. Regras Hardcoded no Código (Quando Editar Manualmente)

Caso a taxonomia ou a conta do anunciante divirja das premissas padrão, ajuste os trechos abaixo:

#### a) Critério de Nome de `Site` na Visão 1 (`step2_compute_methodology.py`)
- **Padrão atual:** em `_compute_site_mode` (linhas `315` e `324`) e nos metadados de `_compute_device_mode` (linhas `714`, `751`, `852`, `915`), um `Site (CM360)` é marcado como CTV na Visão 1 se ` "ctv" in site.lower() `.
- **Observação:** veículos sem `"CTV"` no nome que entreguem em `Connected TV` ou `Set top box` já são capturados automaticamente na Visão 2 (`device`). A edição manual só é necessária se você quiser incluí-los também na Visão 1 ou se o parceiro for mensurado apenas por pixel `1x1` sem User-Agent de TV (caindo em `Unknown platform` no CM360).
- **Onde alterar (`step2_compute_methodology.py`, linhas `315` e `324`):**
  ```python
  CTV_SITE_KEYWORDS = ("ctv", "connectedtv", "smarttv", "ott", "netflix", "roku", "globoplay")
  df_sites["is_ctv"] = df_sites["Site (CM360)"].astype(str).str.lower().apply(
      lambda s: any(k in s for k in CTV_SITE_KEYWORDS)
  )
  ```

#### b) Heurística de Pré-Seleção de Tags Floodlight (`common.py`)
- **Padrão atual:** `classify_tag()` (`common.py`, linhas `49–57`) define apenas quais atividades vêm pré-marcadas na UI (e na autodescoberta do `step0_setup_and_discover.py` quando `--purchase-activity-ids` é omitido). Busca `in_app_purchase` + `ios`/`android` ou substrings `("comprafeita", "purchase", "ordercomplete", "venda")`, excluindo `"pixelunico"`.
- **Onde alterar (`common.py`, linha `55`):** adicione os tokens de compra adotados pela agência ou novos termos de exclusão para pixels globais.

#### c) Moeda e Locale Numérico (`common.py` e `step3_generate_html.py`)
- **Padrão atual:** os valores numéricos vêm na moeda da conta do CM360 (`DV360 Cost (Account Currency)` / `Media Cost`), porém `fmt_curr()` (`common.py`, linhas `105–112`) formata com prefixo `"R$"` e separadores `pt-BR` (`1.234,56`). Há também rótulos `"R$"` nos gráficos de `step3_generate_html.py` (linhas `395–397`).
- **Onde alterar:** ajuste `fmt_curr()`, `fmt_dec()` e `fmt_int()` em `common.py` para contas operando em `USD`, `EUR` ou outras moedas.

#### d) Agrupamento de Múltiplos `Campaign IDs` no Mesmo Estudo (`step1` e `step2`)
- **Padrão atual:** o pipeline filtra um único `campaign_id` por execução.
- **Onde alterar para consolidar múltiplos IDs:**
  1. Em `step1_extract_reports.py` (`_build_cm360_specs`, linhas `169–172`), envie múltiplos dicionários `{"dimensionName": "campaign", "id": cid, "matchType": "EXACT"}` em `camp_filters` (filtros de mesma dimensão operam como `OR` na API v5).
  2. Em `step2_compute_methodology.py` (linhas `109`, `291`, `298`, `552` e `566`), substitua `== camp_id` por `.isin(campaign_ids)`.

#### e) Constantes e Limiares Metodológicos (`step2_compute_methodology.py`)
- `CTV_PLATFORM_NAMES` (linha `27`): `{"Connected TV", "Set top box"}` (IDs `30004` e `30006`).
- `PURE_CTV_PLACEMENT_THRESHOLD = 0.95` (linha `28`): fração mínima de impressões em TV/STB exigida para classificar um `Placement ID` como toque determinístico puro de CTV no `Path to Conversion`.
- `MIN_MEANINGFUL_CTV_IMPS = 1000.0` (linha `29`): volume mínimo de impressões em TV/STB para exibir o Site individualmente na Visão Device (abaixo disso, agrupa em `Residual`).
- Limiar mínimo de amostra `>= 5` conversões multi-toque (linhas `188`, `371`, `779`): abaixo de 5 conversões observadas no P2C, o canal utiliza o lift consolidado do bloco CTV da campanha (ou o benchmark de `youtubectv` da mesma campanha para canais contendo `"youtube"`, linhas `781–797`). Canais contendo `"search"` no nome são sempre tratados como não-CTV (`linha 706`).

#### f) Enriquecimento Opcional via API DV360 (`configs/campaign.example.json`)
- No `web_app.py` (linha `198`), `dv360.enabled` permanece `False` e o custo vem integralmente do CM360. Para habilitar a extração complementar por Insertion Order / Line Item na API do DV360, defina `"enabled": true`, `advertiser_id` e `campaign_id` no bloco `dv360` do JSON e execute via `run_pipeline.py`.

---

## Estrutura de Arquivos

```text
.
├── web_app.py                    # Servidor HTTP (ThreadingHTTPServer), OAuth2/Service Account e stream SSE
├── common.py                     # Helpers de autenticação, parsers CSV do CM360/P2C e formatação
├── step0_setup_and_discover.py   # Descoberta via API de metadados da campanha e Floodlight Activities
├── step1_extract_reports.py      # Criação, polling e download de relatórios CM360 v5 (e DV360 opcional)
├── step2_compute_methodology.py  # Cálculo de alcance/atribuição ('site', 'device', 'both') e asserts de reconciliação
├── step3_generate_html.py        # Geração dos gráficos (matplotlib) e renderização do HTML autocontido
├── run_pipeline.py               # Entrypoint CLI (encadeia step1 -> step2 -> step3)
├── test_self_check.py            # Testes offline com fixtures sintéticas para os 3 modos e endpoints HTTP
├── configs/
│   └── campaign.example.json     # Exemplo de payload de configuração para uso via CLI
├── Dockerfile                    # Build Python 3.12-slim (usuário não-root, porta 8080)
└── requirements.txt              # Dependências Python
```
