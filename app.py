# app.py
import streamlit as st
import pandas as pd
import io
import random
from collections import defaultdict, Counter

st.set_page_config(page_title="Distribuidor Jeziel", layout="wide")
st.title("Distribuidor Jeziel 🚗")
st.markdown("Faça upload de um arquivo .xlsx/.csv com colunas CHASSI, RUA e VAGA. O app fará a distribuição respeitando faixas, CILs e modelos.")

# --- helpers
def faixa_rua(rua_raw):
    """
    Converte '411B' -> 411  (faixa 400-499)
    Converte 'CIL1' -> 100, 'CIL2'->200, etc.
    Retorna inteiro representando a rua base (ex: 411) or faixa_key (100,200,...).
    """
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
    # extract first number (e.g., "411B" -> 411)
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

def distribuir_equilibrado(indices, num_tecnicos, start_order=None):
    """
    Distribui uma lista de índices entre technicians de forma equilibrada,
    retornando mapping idx -> tecnico_index.
    Mantém a ordem dos índices (não embaralha).
    A ordem de atribuição começa em start_order (list de tecnicos preferenciais), 
    ou simplesmente rotaciona começando do técnico de menor carga.
    """
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
    # if user entered fewer names than number, fill defaults
    while len(nomes_tecnicos) < num_tecnicos:
        nomes_tecnicos.append(f"Técnico {len(nomes_tecnicos)+1}")
else:
    nomes_tecnicos = [f"Técnico {i+1}" for i in range(num_tecnicos)]

st.write("Técnicos:", ", ".join(nomes_tecnicos))

process_btn = st.button("Distribuir e baixar planilha")

if uploaded and process_btn:
    try:
        # read file
        if uploaded.name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(uploaded)
        else:
            df = pd.read_csv(uploaded)
    except Exception as e:
        st.error(f"Erro ao ler arquivo: {e}")
        st.stop()

    # normalize columns names
    df.columns = [c.strip().upper() for c in df.columns]

    if not all(col in df.columns for col in ["CHASSI", "RUA", "VAGA"]):
        st.error("Arquivo precisa conter as colunas: CHASSI, RUA, VAGA")
        st.stop()

    # preserve original order by adding index
    df = df.reset_index().rename(columns={"index": "_orig_index"})

    # compute faixa and modelo
    df["_FAIXA_BASE"] = df["RUA"].apply(faixa_rua)
    # compute faixa key for grouping by century (e.g., 411->400)
    def faixa_key_from_base(base):
        if base < 0:
            return -1
        return (base // 100) * 100
    df["_FAIXA_KEY"] = df["_FAIXA_BASE"].apply(faixa_key_from_base)
    df["_MODELO"] = df["CHASSI"].apply(modelo_por_chassi)

    num_t = int(num_tecnicos)
    assigned = {i: None for i in df.index}  # index -> technician_index
    carga = [0]*num_t

    # 1) Prioritize non-kwid models distribution:
    non_kwid_models = df[df["_MODELO"] != "kwid"]["_MODELO"].unique().tolist()
    # We'll treat each model separately
    for model in non_kwid_models:
        idxs = df[(df["_MODELO"] == model)].index.tolist()
        if not idxs:
            continue
        # If there are many (>= num_tecnicos), distribute evenly across technicians
        if len(idxs) >= num_t:
            # distribute round robin but keep original order
            mapping = distribuir_equilibrado(idxs, num_t)
            for idx, tech in mapping.items():
                assigned[idx] = tech
                carga[tech] += 1
        else:
            # less than number of techs: give one per technician until run out
            # choose technicians with currently lowest load
            order = sorted(range(num_t), key=lambda x: carga[x])
            for i, idx in enumerate(idxs):
                tech = order[i % num_t]
                assigned[idx] = tech
                carga[tech] += 1

    # 2) For each faixa key (100,200,300...), distribute remaining (unassigned) in original order
    faixa_keys_in_order = []
    # preserve order of appearance of faixa keys based on first occurrence in original data order
    for _, row in df.iterrows():
        fk = row["_FAIXA_KEY"]
        if fk not in faixa_keys_in_order:
            faixa_keys_in_order.append(fk)

    for fk in faixa_keys_in_order:
        group_idxs = df[(df["_FAIXA_KEY"] == fk)].index.tolist()
        # keep only unassigned
        unassigned = [i for i in group_idxs if assigned[i] is None]
        if not unassigned:
            continue
        # To keep global balance, start assigning to technicians in order of lowest current load
        tech_order = sorted(range(num_t), key=lambda x: carga[x])
        # We'll assign sequentially maintaining order, but rotating tech_order repeatedly
        tptr = 0
        for idx in unassigned:
            tech = tech_order[tptr % num_t]
            assigned[idx] = tech
            carga[tech] += 1
            tptr += 1

    # 3) Final balancing pass: ensure max-min <= 1
    # If difference >1, move some rows (preferably from faixas with >1 assigned to overloaded tech)
    def current_diff():
        return max(carga) - min(carga)
    attempts = 0
    max_attempts = 1000
    while current_diff() > 1 and attempts < max_attempts:
        attempts += 1
        max_tech = max(range(num_t), key=lambda x: carga[x])
        min_tech = min(range(num_t), key=lambda x: carga[x])
        # find a row currently assigned to max_tech that can be moved:
        # Prefer rows from faixa groups where max_tech has >1 assigned in that faixa
        moved = False
        for fk in faixa_keys_in_order:
            idxs_in_fk = [i for i in df[(df["_FAIXA_KEY"] == fk)].index.tolist() if assigned[i] == max_tech]
            if len(idxs_in_fk) > 0:
                # choose the last assigned in original order (to minimize disruption)
                cand = idxs_in_fk[-1]
                assigned[cand] = min_tech
                carga[max_tech] -= 1
                carga[min_tech] += 1
                moved = True
                break
        if not moved:
            # If not moved by faixa preference, move any row from max_tech
            cand_list = [i for i,v in assigned.items() if v == max_tech]
            if cand_list:
                cand = cand_list[-1]
                assigned[cand] = min_tech
                carga[max_tech] -= 1
                carga[min_tech] += 1
            else:
                break  # nothing to move
    # end balancing

    # Apply assigned technician names
    df["TECNICO"] = df.index.map(lambda i: nomes_tecnicos[assigned[i]] if assigned[i] is not None else "")
    # Restore original order by _orig_index
    df_sorted_for_output = df.sort_values("_orig_index").drop(columns=["_orig_index","_FAIXA_BASE","_FAIXA_KEY","_MODELO"])

    # Show summary
    st.success("Distribuição concluída.")
    st.write("Carga por técnico:")
    carga_df = pd.DataFrame({"Técnico": nomes_tecnicos, "Qtd": carga})
    st.table(carga_df)

    st.write("Amostra da planilha resultante:")
    st.dataframe(df_sorted_for_output.head(200))

    # Prepare download
    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
        df_sorted_for_output.to_excel(writer, index=False)
    output_buffer.seek(0)

    st.download_button("📥 Baixar planilha (Excel)", data=output_buffer, file_name="distribuicao_tecnicos.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
