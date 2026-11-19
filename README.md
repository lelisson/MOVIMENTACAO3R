# Movimentação 3R — controle de estoque

Painel interativo da **3R Indústria**.

## Como funciona (sem chave no Streamlit)

1. **GitHub Actions** consulta a Omie (somente leitura) com secrets do repositório  
2. Gera `public/dashboard.html` e faz commit  
3. **Streamlit Cloud** só exibe esse HTML — **não precisa** de `OMIE_*` nos Secrets do Streamlit  

## Secrets no GitHub (Actions)

Repo → **Settings → Secrets and variables → Actions**:

| Secret | Uso |
|--------|-----|
| `OMIE_3R_APP_KEY` | App Key Omie 3R |
| `OMIE_3R_APP_SECRET` | App Secret Omie 3R |
| `STREAMLIT_APP_URL` | URL do app (anti-sono) |

## Publicar dados

- Automático: a cada 4 horas (`Publicar painel Omie`)  
- Manual: **Actions → Publicar painel Omie → Run workflow**

## Streamlit Cloud

- Main file: `streamlit_app.py`  
- **Não** cadastre chaves Omie no Streamlit  

## Manter ativo

Workflow `Manter painel ativo` visita o app a cada 2 h (usa `STREAMLIT_APP_URL`).

## Regras de negócio

- Entrada CFOP **1901** · Saída CFOP **5902** (NF origem na remessa)  
- CFOP **5124** só financeiro  
- Canceladas: filtro no painel; não entram no saldo  
