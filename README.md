
Distribuidor Jeziel
===================

App em Streamlit para distribuir veículos entre técnicos a partir de uma planilha .xlsx/.csv.

Regras implementadas:
- Mantém a ordem original do arquivo.
- Tratamento de ruas com letra (Ex: 411B -> faixa 400-499).
- Tratamento de CIL1/CIL2/CIL3 como faixas 100/200/300.
- Identificação de modelo pelos 6 primeiros dígitos do CHASSI (Kwid, Duster, Oroch, outro).
- Distribuição balanceada, diferença máxima entre técnicos = 1.

Arquivos:
- app.py (Streamlit app)
- requirements.txt (dependências)

Como rodar localmente:
1. Instale Python 3.8+
2. pip install -r requirements.txt
3. streamlit run app.py
4. Abra http://localhost:8501

Deploy rápido (Streamlit Cloud):
1. Crie repositório no GitHub e envie esses arquivos.
2. Vá para https://streamlit.io/cloud, conecte ao GitHub e faça deploy.
