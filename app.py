
import streamlit as st
import pandas as pd
import io
import random

st.set_page_config(page_title="Distribuidor Jeziel", layout="wide")
st.title("Distribuidor Jeziel 🚗")
st.markdown("Faça upload de um arquivo .xlsx/.csv com colunas CHASSI, RUA e VAGA. O app fará a distribuição respeitando faixas, CILs e modelos.")

# --- helpers
def faixa_rua(rua_raw):
    if pd.isna(rua_raw):
        return -1
    r = str(rua_raw).strip()
    r_lower = r.lower()
    if r_lower.startswith("cil"):
        digits = ''.join([c for c in r_lower if c.isdigit()])
        try:
            n = int(digits)
            return n * 100
        except:
            return -1
    digits = ''.join([c for c in r if c.isdigit()])
    if digits == "":
        return -1
    try:
        return int(digits)
    except:
        return -1

def modelo_por_chassi(chassi):
    if pd.isna(chassi):
        return "unknown"
    c = str(chassi).strip()
    prefix = c[:6].upper() if len(c) >= 6 else c
    if prefix == "93YRBB":
        return "kwid"
    if prefix == "93YHJD":
        return "duster"
    if prefix == "8A18SR":
        return "oroch"
    return "outro"

def distribuir_equilibrado(indices, num_tecnicos):
    mapping = {}
    n = len(indices)
    base = n // num_tecnicos
    sobra = n % num_tecnicos
    ptr = 0
    for t in range(num_tecnicos):
        take = base + (1 if t < sobra else 0)
        for i in range(take):
            if ptr < n:
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
    df["_FAIXA_BASE"] = df["RUA"].apply(faixa_rua)
    def faixa_key_from_base(base):
        if base < 0:
            return -1
        return (base // 100) * 100
    df["_FAIXA_KEY"] = df["_FAIXA_BASE"].apply(faixa_key_from_base)
    df["_MODELO"] = df["CHASSI"].apply(modelo_por_chassi)

    num_t = int(num_tecnicos)
    assigned = {i: None for i in df.index}
    carga = [0]*num_t

    non_kwid_models = df[df["_MODELO"] != "kwid"]["_MODELO"].unique().tolist()
    for model in non_kwid_models:
        idxs = df[(df["_MODELO"] == model)].index.tolist()
        if not idxs:
            continue
        if len(idxs) >= num_t:
            mapping = distribuir_equilibrado(idxs, num_t)
            for idx, tech in mapping.items():
                assigned[idx] = tech
                carga[tech] += 1
        else:
            order = sorted(range(num_t), key=lambda x: carga[x])
            for i, idx in enumerate(idxs):
                tech = order[i % num_t]
                assigned[idx] = tech
                carga[tech] += 1

    faixa_keys_in_order = []
    for _, row in df.iterrows():
        fk = row["_FAIXA_KEY"]
        if fk not in faixa_keys_in_order:
            faixa_keys_in_order.append(fk)

    for fk in faixa_keys_in_order:
        group_idxs = df[(df["_FAIXA_KEY"] == fk)].index.tolist()
        unassigned = [i for i in group_idxs if assigned[i] is None]
        if not unassigned:
            continue
        tech_order = sorted(range(num_t), key=lambda x: carga[x])
        tptr = 0
        for idx in unassigned:
            tech = tech_order[tptr % num_t]
            assigned[idx] = tech
            carga[tech] += 1
            tptr += 1

    def current_diff():
        return max(carga) - min(carga)
    attempts = 0
    max_attempts = 1000
    while current_diff() > 1 and attempts < max_attempts:
        attempts += 1
        max_tech = max(range(num_t), key=lambda x: carga[x])
        min_tech = min(range(num_t), key=lambda x: carga[x])
        moved = False
        for fk in faixa_keys_in_order:
            idxs_in_fk = [i for i in df[(df["_FAIXA_KEY"] == fk)].index.tolist() if assigned[i] == max_tech]
            if len(idxs_in_fk) > 0:
                cand = idxs_in_fk[-1]
                assigned[cand] = min_tech
                carga[max_tech] -= 1
                carga[min_tech] += 1
                moved = True
                break
        if not moved:
            cand_list = [i for i,v in assigned.items() if v == max_tech]
            if cand_list:
                cand = cand_list[-1]
                assigned[cand] = min_tech
                carga[max_tech] -= 1
                carga[min_tech] += 1
            else:
                break

    df["TECNICO"] = df.index.map(lambda i: nomes_tecnicos[assigned[i]] if assigned[i] is not None else "")
    df_sorted_for_output = df.sort_values("_orig_index").drop(columns=["_orig_index","_FAIXA_BASE","_FAIXA_KEY","_MODELO"])

    st.success("Distribuição concluída.")
    st.write("Carga por técnico:")
    carga_df = pd.DataFrame({"Técnico": nomes_tecnicos, "Qtd": carga})
    st.table(carga_df)

    st.write("Amostra da planilha resultante:")
    st.dataframe(df_sorted_for_output.head(200))

    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
        df_sorted_for_output.to_excel(writer, index=False)
    output_buffer.seek(0)

    st.download_button("📥 Baixar planilha (Excel)", data=output_buffer, file_name="distribuicao_tecnicos.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
