# Movimentação 3R — controle de estoque

Painel interativo da **3R Indústria**.

## Como funciona (sem chave Omie no Streamlit)

1. **GitHub Actions** consulta a Omie (somente leitura) com secrets do repositório  
2. Gera `public/dashboard.html` + `public/last_publish.json` e faz commit  
3. **Streamlit Cloud** só exibe esse HTML (busca o arquivo fresco no GitHub)  
4. Botão **Atualizar** dispara uma publicação **forçada** e reinicia a janela de 4 h  

## Secrets no GitHub (Actions)

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Uso |
|--------|-----|
| `OMIE_3R_APP_KEY` | App Key Omie 3R |
| `OMIE_3R_APP_SECRET` | App Secret Omie 3R |
| `STREAMLIT_APP_URL` | URL do app (anti-sono) |

## Publicar dados

- Automático: o cron roda **a cada hora**, mas só coleta Omie se já passaram **4 h** da última publicação  
- Forçado: botão **Atualizar** no painel (ou Actions → Run workflow com `force`) — reinicia a contagem de 4 h  

## Streamlit Cloud

- Main file: `streamlit_app.py`  
- **Não** cadastre chaves Omie no Streamlit  
- Para o botão Atualizar forçar a coleta, cadastre só:

| Secret Streamlit | Uso |
|------------------|-----|
| `GH_DISPATCH_TOKEN` | PAT GitHub com `actions:write` (e leitura de runs) neste repo |

## Manter ativo

Workflow `Manter painel ativo` visita o app a cada 2 h (usa `STREAMLIT_APP_URL`).

## Regras de negócio

- Entrada CFOP **1901** · Saída CFOP **5902** (NF origem na remessa)  
- CFOP **5124** só financeiro  
- Canceladas: filtro no painel; não entram no saldo  
