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
    """
    Retorna a faixa base (múltiplo de 100) ou None se inválida.
    Exemplos:
      411B -> 400
      411  -> 400
      CIL1 -> 100
      'At Fabrica' -> None
    """
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
    """
    indices: lista de índices (já na ordem original) pertencentes à mesma faixa.
    Divide esses indices em 'num_tecnicos' blocos contíguos com tamanhos o mais igual possível.
    Se houver sobra, escolhe aleatoriamente quais blocos recebem +1.
    Em seguida embaralha a ordem dos técnicos e atribui cada bloco a um técnico.
    Retorna mapping {idx -> tecnico_index}.
    """
    mapping = {}
    total = len(indices)
    if total == 0:
        return mapping

    base = total // num_tecnicos
    sobra = total % num_tecnicos

    # cria lista de tamanhos por bloco (um por técnico-position)
    chunk_sizes = [base] * num_tecnicos
    if sobra > 0:
        # escolhe aleatoriamente quais posições ganham +1
        pos_extra = random.sample(range(num_tecnicos), sobra)
        for p in pos_extra:
            chunk_sizes[p] += 1

    # ordem aleatória dos técnicos (garante que não comece sempre pelo Técnico 1)
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

# -----------------------
# UI
# -----------------------
uploaded = st.file_uploader("Selecione .xlsx ou .csv (com colunas CHASSI, RUA, VAGA)", type=["xlsx", "xls", "csv"])
num_tecnicos = st.number_input("Quantidade de técnicos", min_value=1, max_value=20, value=3, step=1)
nomes_text = st.text_input("Nomes dos técnicos (separados por vírgula) — ou deixe em branco para usar Técnico 1, Técnico 2...", "")

if nomes_text.strip():
    nomes_tecnicos = [n.strip() for n in nomes_text.split(",") if n.strip()]
    # preenche nomes faltantes caso o usuário coloque menos nomes que num_tecnicos
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

    # normalize column names
    df.columns = [c.strip().upper() for c in df.columns]

    if not all(col in df.columns for col in ["CHASSI", "RUA", "VAGA"]):
        st.error("Arquivo precisa conter as colunas: CHASSI, RUA, VAGA")
        st.stop()

    # preserva ordem original explicitamente
    df = df.reset_index(drop=True)
    df["_orig_index"] = list(range(len(df)))

    # calcula faixa (None quando inválida)
    df["_FAIXA_KEY"] = df["RUA"].apply(faixa_rua)

    # considera apenas linhas válidas (as outras serão IGNORADAS)
    df_validos = df[df["_FAIXA_KEY"].notna()].copy()

    # preserva ordem de aparição das faixas conforme arquivo original
    faixas_em_ordem = []
    for _, row in df_validos.iterrows():
        fk = row["_FAIXA_KEY"]
        if fk not in faixas_em_ordem:
            faixas_em_ordem.append(fk)

    assigned = {}  # map idx -> tecnico_index

    # percorre cada faixa na ordem de aparição
    for fk in faixas_em_ordem:
        subset = df_validos[df_validos["_FAIXA_KEY"] == fk]
        # garante ordem original dentro da faixa
        subset = subset.sort_values("_orig_index")
        idxs = subset.index.tolist()
        mapping = distribuir_faixa_contigua(idxs, num_tecnicos)
        assigned.update(mapping)

    # monta coluna TECNICO (linhas inválidas recebem "")
    df["TECNICO"] = df.index.map(lambda i: nomes_tecnicos[assigned[i]] if i in assigned else "")

    # calcula carga final por técnico (somente atribuídos)
    carga = [0] * num_tecnicos
    for tech in assigned.values():
        carga[tech] += 1

    # prepara saída mantendo ordem original do arquivo
    df_saida = df.sort_values("_orig_index").drop(columns=["_orig_index", "_FAIXA_KEY"])

    st.success("Distribuição concluída.")
    st.write("Carga por técnico (somente veículos atribuídos):")
    carga_df = pd.DataFrame({"Técnico": nomes_tecnicos, "Qtd": carga})
    st.table(carga_df)

    st.write("Amostra da planilha resultante:")
    st.dataframe(df_saida.head(200))

    # exporta excel mantendo ordem original
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

