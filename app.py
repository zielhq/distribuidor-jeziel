import streamlit as st
import pandas as pd
import random
import re

st.title("Distribuição de Veículos por Técnicos")

# Função para identificar a faixa da rua
def get_faixa_key(rua):
    if pd.isna(rua):
        return None
    rua_str = str(rua).strip().upper()

    # Tratar Cil1, Cil2, ...
    m = re.match(r"CIL(\d+)", rua_str)
    if m:
        base = int(m.group(1)) * 100
        return f"{base}-{base+99}"

    # Extrair número inicial
    m = re.match(r"(\d+)", rua_str)
    if m:
        numero = int(m.group(1))
        base = (numero // 100) * 100
        return f"{base}-{base+99}"

    return None

# Entrada de técnicos
tecnicos_input = st.text_input("Digite os nomes dos técnicos separados por vírgula:")
tecnicos = [t.strip() for t in tecnicos_input.split(",") if t.strip()]

arquivo = st.file_uploader("Envie o arquivo Excel", type=["xlsx"])

if arquivo and tecnicos:
    df = pd.read_excel(arquivo)

    # Detectar coluna da RUA
    col_rua = None
    for col in df.columns:
        if "RUA" in str(col).upper():
            col_rua = col
            break
    if col_rua is None:
        st.error("Não encontrei coluna 'RUA' no arquivo.")
        st.stop()

    # Adicionar coluna de faixa
    df["_FAIXA_KEY"] = df[col_rua].apply(get_faixa_key)

    # Filtrar apenas faixas válidas (ex.: '300-399', '400-499', etc.)
    df_valid = df[df["_FAIXA_KEY"].notna()].copy()

    # Criar estrutura para manter ordem original
    veiculos = list(df_valid.index)

    # Agrupar por faixa mantendo ordem original
    faixas_ordenadas = []
    vistos = set()
    for idx in veiculos:
        fk = df_valid.at[idx, "_FAIXA_KEY"]
        if fk not in vistos:
            vistos.add(fk)
            faixas_ordenadas.append(fk)

    # Inicializar distribuição
    assigned = {idx: None for idx in df_valid.index}
    carga = {tec: 0 for tec in tecnicos}

    # Embaralhar ordem inicial dos técnicos para não começar sempre pelo mesmo
    ordem_tecnicos = tecnicos[:]
    random.shuffle(ordem_tecnicos)

    # Distribuir por faixa mantendo equilíbrio global
    for fk in faixas_ordenadas:
        idxs_faixa = [i for i in veiculos if df_valid.at[i, "_FAIXA_KEY"] == fk]
        for idx in idxs_faixa:
            # Escolher técnico com menor carga atual
            min_carga = min(carga.values())
            candidatos = [tec for tec, c in carga.items() if c == min_carga]
            escolhido = random.choice(candidatos)
            assigned[idx] = escolhido
            carga[escolhido] += 1

    # Atribuir de volta ao df original
    df["Técnico"] = None
    for idx, tec in assigned.items():
        df.at[idx, "Técnico"] = tec

    # Salvar resultado
    output_path = "/mnt/data/distribuicao_final.xlsx"
    df.to_excel(output_path, index=False)
    st.success("Distribuição concluída!")
    st.download_button("Baixar arquivo distribuído", data=open(output_path, "rb"), file_name="distribuicao_final.xlsx")


