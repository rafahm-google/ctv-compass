# CTV Compass — Mensuração Executiva de CTV no CM360

Portal web auto-hospedado e pipeline de auditoria em Python para agências e anunciantes mensurarem o impacto real de **Connected TV (`CTV`)** diretamente via **Campaign Manager 360 API (`v5`)**, triangulando automaticamente **3 relatórios oficiais** na mesma janela e `Campaign ID`:

1. **`STANDARD`:** Custo de mídia, plataforma física de entrega (`Platform Type`) e conversões diretas (`Click-Through` + `View-Through`).
2. **`REACH`:** Alcance único deduplicado (`Unique Reach`), *Co-Viewing* na tela grande e sobreposição cross-channel / cross-device.
3. **`PATH_TO_CONVERSION (14 dias)`:** Jornadas completas deduplicadas por pedido (`Conversion ID`), isolando vendas solo, eficiência de toques e ticket médio incremental (`AOV`).

---

## Visão Dupla de CTV (`Naming do Site` + `Validação por Device Type`)

Por padrão (`identification_mode = "both"`), o **CTV Compass** processa e entrega as duas leituras em **um único deck HTML interativo de 8 slides** (pronto para apresentar no navegador ou exportar em PDF):

* **Visão 1 — Naming do Site (`CTV`):** Avalia os veículos nomeados com `CTV` pela agência no CM360.
* **Visão 2 — Validação por Device Type (`Smart TV + Set-top Box`):** Filtra fisicamente `platformType IN ('Connected TV' [30004], 'Set top box' [30006])` em todos os Sites da campanha, aplica a **Lei da Inclusão-Exclusão Exata** (`|A ∩ B| = |A| + |B| - |U|`) para eliminar dupla contagem `TV ∩ TV` entre veículos e **ativa-se automaticamente como visão principal** quando a campanha não utiliza `CTV` na nomenclatura dos Sites.

Todas as tabelas e cards passam por **5 Travas Matemáticas Automáticas** (`assert` em Python) antes da geração do relatório, com fórmulas abertas (`📐 Como calculamos`) em todos os slides.

---

## Como Funciona na Agência (2 Perfis)

* **Para Planejamento / Mídia (Uso no Navegador — Zero Código):**
  Acessa o link interno da agência, clica em **"Entrar com Google"** (ou entra direto via Conta de Serviço), seleciona a **Campanha** em um menu suspenso, revisa as caixas das **Tags Floodlight de Compra** pré-selecionadas e clica em **Gerar Apresentação Executiva** para baixar o deck `.html`.
* **Para TI / BI da Agência (Deploy Único e Conexão com a API do CM360):**
  Hospeda este repositório (Cloud Run, Docker ou servidor interno) e configura a credencial da API do CM360 uma única vez via variáveis de ambiente — sem expor arquivos JSON para os usuários finais nem no GitHub.

---

## Guia de Hospedagem e Conexão CM360 (TI / BI da Agência)

### 1. Habilitar a API no Google Cloud
1. No [Google Cloud Console](https://console.cloud.google.com/), crie ou selecione o projeto da agência e ative a **Campaign Manager 360 API (`dfareporting`)**.
2. Escolha **uma** das duas formas de autenticação abaixo:

#### Opção A — Login Individual por Usuário (`Entrar com Google` na tela)
Ideal quando cada analista já possui acesso ao CM360 no próprio e-mail corporativo:
1. Em **APIs e Serviços > Credenciais > Criar Credenciais > ID do cliente OAuth**, escolha **Aplicativo da Web (Web Application)**.
2. Em **URIs de redirecionamento autorizados**, adicione:
   * `https://SEU-DOMINIO-HOSPEDADO/auth/callback` (produção)
   * `http://localhost:8080/auth/callback` (teste local)
3. Copie o `GOOGLE_CLIENT_ID` e o `GOOGLE_CLIENT_SECRET` (ou salve o JSON baixado como `client_secrets.json` apenas localmente — o `.gitignore` bloqueia seu envio ao GitHub).

#### Opção B — Conexão Centralizada no Servidor (Conta de Serviço — Sem Login na Tela)
Ideal quando o BI da agência possui uma **Service Account** cadastrada como *User Profile* no CM360 e protege o painel via VPN / IAP:
1. Passe o JSON da Service Account na variável `CM360_CREDENTIALS_JSON` (ou caminho em `CM360_CREDENTIALS_FILE`).

---

### 2. Subir o Serviço Web (Cloud Run, Docker ou Local)

#### Deploy em 1 comando no Google Cloud Run
```bash
gcloud run deploy ctv-compass \
  --source . \
  --region southamerica-east1 \
  --timeout 900 \
  --memory 2Gi \
  --set-env-vars "GOOGLE_CLIENT_ID=SEU_ID,GOOGLE_CLIENT_SECRET=SEU_SECRET"
```

#### Ou via Docker em qualquer nuvem / servidor interno
```bash
docker build -t ctv-compass .
docker run -p 8080:8080 \
  -e GOOGLE_CLIENT_ID="SEU_ID" \
  -e GOOGLE_CLIENT_SECRET="SEU_SECRET" \
  ctv-compass
```

#### Ou execução local direta em Python
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python test_self_check.py   # Valida motores matemáticos + rotas HTTP offline em ~3s

export GOOGLE_CLIENT_ID="SEU_ID"
export GOOGLE_CLIENT_SECRET="SEU_SECRET"
python web_app.py           # Abre o portal em http://localhost:8080
```

---

## Uso Opcional via Linha de Comando (CLI)

```bash
python step0_setup_and_discover.py --campaign-id <CAMPAIGN_ID> --mode both
python run_pipeline.py --config configs/camp_<CAMPAIGN_ID>_both.json
```

---

## Estrutura do Repositório

```text
.
├── web_app.py                    # Portal web auto-hospedado (Login OAuth2 / Service Account + SSE)
├── common.py                     # Utilitários OAuth2, higiene Floodlight, parsers CM360/P2C e PT-BR
├── step0_setup_and_discover.py   # CLI opcional de autodescoberta de campanha e tags Floodlight
├── step1_extract_reports.py      # Extração paralela de relatórios CM360 v5 (+ DV360 opcional)
├── step2_compute_methodology.py  # Motor matemático CTV ('site', 'device' e 'both') + 5 Travas assert
├── step3_generate_html.py        # Gerador da apresentação executiva HTML interativa + 3 infográficos PNG
├── run_pipeline.py               # Orquestrador CLI do estudo executivo de CTV
├── test_self_check.py            # Auto-teste offline (modos 'site', 'device', 'both' + Servidor Web)
├── configs/
│   └── campaign.example.json     # Exemplo de configuração para execução via CLI
├── Dockerfile                    # Imagem pronta para Cloud Run / Docker (usuário não-root)
└── requirements.txt              # Dependências enxutas (pandas, numpy, matplotlib, google-api, oauth)
```

---

## Governança Metodológica & Privacidade

* **Higiene de Floodlight:** Selecione sempre **1 tag transacional oficial de compra por plataforma** (`Web`, `Android`, `iOS`), evitando somar pixels agregadores (`Pixel_Unico`, `view_item`) que disparam no mesmo pedido.
* **Rigor Financeiro:** Superar `1,0x` de ROAS significa gerar mais receita atribuída pela metodologia do que o custo de mídia investido no veículo (não equivale a lucro líquido contábil).
* **Segurança:** Credenciais (`client_secrets.json`, `token*.json`, `.env`) e dados brutos/relatórios (`*.csv`, `outputs/`, `configs/*.json`) estão protegidos no `.gitignore` e `.dockerignore` para nunca serem versionados no GitHub.
