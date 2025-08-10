import streamlit as st
import pandas as pd
import io
import random

st.set_page_config(page_title="Distribuidor Jeziel", layout="wide")
st.title("Distribuidor Jeziel 🚗")
st.markdown("Faça upload de um arquivo .xlsx/.csv com colunas CHASSI, RUA e VAGA. O app fará a distribuição respeitando faixas de rua.")

# --- Funções auxiliares
def faixa_rua(rua_raw):
    if pd.isna(rua_raw):
        return None
    r = str(rua_raw).strip()
    r_lower = r.lower()

    # Trata CIL
    if r_lower.startswith("cil"):
        digits = ''.join([c for c in r_lower if c.isdigit()])
        try:
            return int(digits) * 100
        except:
            return None

    # Extrai número de rua
    digits = ''.join([c for c in r if c.isdigit()])
    if digits == "":
        return None
    try:
        base = int(digits)
        return (base // 100) * 100
    except:
        return None

def distribuir_faixa(indices, num_tecnicos):
    random.shuffle(indices)  # embaralha ordem
    base = len(indices) // num_tecnicos
    sobra = len(indices) % num_tecnicos
    mapping = {}
    ordem_tecnicos = list(range(num_tecnicos))
    random.shuffle(ordem_tecnicos)  # ordem aleatória dos técnicos

    ptr = 0
    for t in ordem_tecnicos:
        qtd = base + (1 if sobra > 0 else 0)
        if sobra > 0:
            sobra -= 1
        for _ in range(qtd):
            if ptr < len(indices):
                mapping[indices[ptr]] = t
                ptr += 1
    return mapping

# --- UI
uploaded = st.file_uploader("Selecione .xlsx ou .csv (com colunas CHASSI, RUA, VAGA)", type=["xlsx", "xls", "csv"])
num_tecnicos = st.number_input("Quantidade de técnicos", min_value=1, max_value=20, value=3, step=1)
nomes_text = st.text_input("Nomes dos técnicos (separados por vírgula) — ou deixe em branco para usar Técnico 1, Técnico 2...", "")

if nomes_text.strip():
    nomes_tecnicos = [n.strip() for n in nomes_text.split(",") if n.strip()]
    while len(nomes_tecnicos) < num_tecnicos:
        nomes_tecnicos.append(f"Técnico {len(nomes_tecnicos)+1}")
else:
    nomes_tecnicos = [f"Técnico {i+1}" for i in range(num_tecnicos)]

st.write("Técnicos:", ", ".join(nomes_tecnicos))

process_btn = st.button("Distribuir e baixar planilha")

if uploaded and process_btn:
    try:
        if uploaded.name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded)
        else:
            df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        st.stop()

    df.columns = [c.strip().upper() for c in df.columns]

    if not all(col in df.columns for col in ["CHASSI", "RUA", "VAGA"]):
        st.error("Arquivo precisa conter as colunas: CHASSI, RUA, VAGA")
        st.stop()

    df = df.reset_index().rename(columns={"index": "_orig_index"})

    # Calcula faixa
    df["_FAIXA_KEY"] = df["RUA"].apply(faixa_rua)

    # Remove ruas inválidas (None)
    df_validos = df[df["_FAIXA_KEY"].notna()].copy()

    # Agrupa por faixa e distribui
    assigned = {}
    for fk in sorted(df_validos["_FAIXA_KEY"].unique()):
        idxs = df_validos[df_validos["_FAIXA_KEY"] == fk].index.tolist()
        mapping = distribuir_faixa(idxs, num_tecnicos)
        assigned.update(mapping)

    # Aplica técnicos no df final
    df["TECNICO"] = df.index.map(lambda i: nomes_tecnicos[assigned[i]] if i in assigned else "")

    # Mantém ordem original
    df_sorted_for_output = df.sort_values("_orig_index").drop(columns=["_orig_index","_FAIXA_KEY"])

    st.success("Distribuição concluída.")
    st.write("Carga por técnico (somente veículos atribuídos):")
    carga_df = df_sorted_for_output["TECNICO"].value_counts().reindex(nomes_tecnicos, fill_value=0).reset_index()
    carga_df.columns = ["Técnico", "Qtd"]
    st.table(carga_df)

    st.write("Amostra da planilha resultante:")
    st.dataframe(df_sorted_for_output.head(200))

    # Exporta
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
        df_sorted_for_output.to_excel(writer, index=False)
    output_buffer.seek(0)

    st.download_button(
        "📥 Baixar planilha (Excel)",
        data=output_buffer,
        file_name="distribuicao_tecnicos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

