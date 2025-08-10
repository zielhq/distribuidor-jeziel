import streamlit as st
import pandas as pd
import io
import random

st.set_page_config(page_title="Distribuidor Jeziel", layout="wide")
st.title("Distribuidor Jeziel 🚗")
st.markdown("Faça upload de um arquivo .xlsx/.csv com colunas CHASSI, RUA e VAGA. O app fará a distribuição por faixas de rua (mantendo ordem original).")

# -----------------------
# Helpers
# -----------------------
def faixa_rua(rua_raw):
    if pd.isna(rua_raw):
        return None
    r = str(rua_raw).strip()
    rl = r.lower()

    if rl.startswith("cil"):
        digits = ''.join(c for c in rl if c.isdigit())
        try:
            return int(digits) * 100
        except:
            return None

    digits = ''.join(c for c in r if c.isdigit())
    if digits == "":
        return None
    try:
        num = int(digits)
        return (num // 100) * 100
    except:
        return None

def distribuir_faixa_contigua(indices, num_tecnicos):
    mapping = {}
    total = len(indices)
    if total == 0:
        return mapping

    base = total // num_tecnicos
    sobra = total % num_tecnicos

    chunk_sizes = [base] * num_tecnicos
    if sobra > 0:
        pos_extra = random.sample(range(num_tecnicos), sobra)
        for p in pos_extra:
            chunk_sizes[p] += 1

    tech_order = random.sample(list(range(num_tecnicos)), k=num_tecnicos)

    ptr = 0
    for i, size in enumerate(chunk_sizes):
        tech = tech_order[i]
        for _ in range(size):
            if ptr >= total:
                break
            idx = indices[ptr]
            mapping[idx] = tech
            ptr += 1

    return mapping

def balancear_globais(assigned, num_tecnicos):
    """Ajusta assigned para que diferença máxima entre técnicos seja 1."""
    # Conta veículos por técnico
    carga = {t: 0 for t in range(num_tecnicos)}
    for t in assigned.values():
        carga[t] += 1

    max_carga = max(carga.values())
    min_carga = min(carga.values())

    # Enquanto diferença > 1, mover 1 veículo do mais carregado para o menos carregado
    while max_carga - min_carga > 1:
        tech_max = max(carga, key=carga.get)
        tech_min = min(carga, key=carga.get)

        # Escolher um índice do tech_max para mover
        idx_para_mover = None
        for idx, t in assigned.items():
            if t == tech_max:
                idx_para_mover = idx
                break

        if idx_para_mover is None:
            break

        assigned[idx_para_mover] = tech_min
        carga[tech_max] -= 1
        carga[tech_min] += 1

        max_carga = max(carga.values())
        min_carga = min(carga.values())

    return assigned

# -----------------------
# UI
# -----------------------
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

    df = df.reset_index(drop=True)
    df["_orig_index"] = list(range(len(df)))

    df["_FAIXA_KEY"] = df["RUA"].apply(faixa_rua)
    df_validos = df[df["_FAIXA_KEY"].notna()].copy()

    faixas_em_ordem = []
    for _, row in df_validos.iterrows():
        fk = row["_FAIXA_KEY"]
        if fk not in faixas_em_ordem:
            faixas_em_ordem.append(fk)

    assigned = {}
    for fk in faixas_em_ordem:
        subset = df_validos[df_validos["_FAIXA_KEY"] == fk]
        subset = subset.sort_values("_orig_index")
        idxs = subset.index.tolist()
        mapping = distribuir_faixa_contigua(idxs, num_tecnicos)
        assigned.update(mapping)

    # 🔹 Balanceamento final para diferença máxima de 1
    assigned = balancear_globais(assigned, num_tecnicos)

    df["TECNICO"] = df.index.map(lambda i: nomes_tecnicos[assigned[i]] if i in assigned else "")

    carga = [0] * num_tecnicos
    for tech in assigned.values():
        carga[tech] += 1

    df_saida = df.sort_values("_orig_index").drop(columns=["_orig_index", "_FAIXA_KEY"])

    st.success("Distribuição concluída.")
    st.write("Carga por técnico (somente veículos atribuídos):")
    carga_df = pd.DataFrame({"Técnico": nomes_tecnicos, "Qtd": carga})
    st.table(carga_df)

    st.write("Amostra da planilha resultante:")
    st.dataframe(df_saida.head(200))

    output_buffer = io.BytesIO()
    with pd.ExcelWriter(output_buffer, engine="openpyxl") as writer:
        df_saida.to_excel(writer, index=False)
    output_buffer.seek(0)

    st.download_button(
        "📥 Baixar planilha (Excel)",
        data=output_buffer,
        file_name="distribuicao_tecnicos.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

