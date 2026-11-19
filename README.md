# Movimentação 3R — controle de estoque

Painel interativo da **3R Indústria** (Omie, **somente leitura**).

## Regras

- Entrada CFOP **1901** → alimenta saldo  
- Saída CFOP **5902** → consome NF de origem na observação da remessa  
- CFOP **5124** → só valor financeiro (não move estoque)  
- NFs canceladas: filtro no cabeçalho; não entram no saldo  

## Streamlit Cloud

1. Deploy deste repositório no [Streamlit Cloud](https://share.streamlit.io/)  
2. Main file: `streamlit_app.py`  
3. Em **Settings → Secrets** (nunca no git):

```toml
OMIE_3R_APP_KEY = "sua_app_key"
OMIE_3R_APP_SECRET = "sua_app_secret"
```

## Manter ativo (não dormir)

O workflow `.github/workflows/manter-ativo.yml` visita o app a cada 2 horas.

No GitHub do repo → **Settings → Secrets and variables → Actions**:

- `STREAMLIT_APP_URL` = `https://seu-app.streamlit.app`

## Local

```bash
pip install -r requirements.txt
# defina OMIE_3R_APP_KEY e OMIE_3R_APP_SECRET no ambiente
streamlit run streamlit_app.py
```

Ou HTML:

```bash
python estoque3r.py --de 01/01/2026 --abrir
```

## Segurança

- Sem chaves no repositório  
- API Omie só com métodos de leitura (`ListarNF`, `ConsultarNF`, `ConsultarRemessa`)  
