import streamlit as st
import pandas as pd
import io
import random

st.set_page_config(page_title="Distribuidor Jeziel", layout="wide")
st.title("Distribuidor Jeziel 🚗")
st.markdown(
    "Faça upload de um arquivo .xlsx/.csv com colunas CHASSI, RUA e VAGA. "
    "O app fará a distribuição respeitando faixas, CILs e modelos."
)

# --- Helpers ---

def faixa_rua(rua_raw):
    """
    Converte:
    - '411B' -> 400 (faixa 400-499)
    - 'CIL1' -> 100, 'CIL2' -> 200 etc.
    Retorna a faixa base como múltiplo de 100 ou -1 se inválido.
    """
    if pd.isna(rua_raw):
        return -1
    r = str(rua_raw).strip().lower()
    if r.startswith("cil"):
        digits = ''.join([c for c in r if c.isdigit()])
        try:
            return int(digits) * 100
        except:
            return -1
    # Extrai número principal, ignora letras
    digits = ''.join([c for c in r if c.isdigit()])
    if not digits:
        return -1
    try:
        num = int(digits)
        faixa = (num // 100) * 100  # Ex: 411 -> 400
        return faixa
    except:
        return -1

def modelo_por_chassi(chassi):
    if pd.isna(chassi):
        return "unknown"
    c = str(chassi).strip().upper()
    prefix = c[:6] if len(c) >= 6 else c
    if prefix == "93YRBB":
        return "kwid"
    if prefix == "93YHJD":
        return "duster"
    if prefix == "8A18SR":
        return "oroch"
    return "outro"

def distribuir_entre_tecnicos(indices, num_tecnicos):
    """
    Distribui indices igualmente entre técnicos.
    Se sobrarem veículos, distribui de forma aleatória para alguns técnicos (1 a mais no máximo).
    Retorna dicionário idx -> técnico (int)
    """
    assigned = {}
    total = len(indices)
    base = total // num_tecnicos
    sobra = total % num_tecnicos

    # Quantidade por técnico inicialmente
    cargas = [base] * num_tecnicos

    # Distribui a sobra aleatoriamente para técnicos diferentes
    if sobra > 0:
        extras_indices = random.sample(range(num_tecnicos), sobra)
        for i in extras_indices:
            cargas[i] += 1

    ptr = 0
    for tech_idx, qtd in enumerate(cargas):
        for _ in range(qtd):
            assigned[indices[ptr]] = tech_idx
            ptr += 1

    return assigned

# --- UI ---

uploaded = st.file_uploader(
    "Selecione .xlsx ou .csv (com colunas CHASSI, RUA, VAGA)", type=["xlsx", "xls", "csv"]
)
num_tecnicos = st.number_input(
    "Quantidade de técnicos", min_value=1, max_value=20, value=3, step=1
)
nomes_text = st.text_input(
    "Nomes dos técnicos (separados por vírgula) — ou deixe em branco para usar Técnico 1, Técnico 2...", ""
)
if nomes_text.strip():
    nomes_tecnicos = [n.strip() for n in nomes_text.split(",") if n.strip()]
    while len(nomes_tecnicos) < num_tecnicos:
        nomes_tecnicos.append(f"Técnico {len(nomes_tecnicos) + 1}")
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

    # Mantém a ordem original, adiciona coluna para preservar índice original
    df = df.reset_index().rename(columns={"index": "_orig_index"})

    # Aplica faixa para cada rua
    df["_FAIXA"] = df["RUA"].apply(faixa_rua)
    df["_MODELO"] = df["CHASSI"].apply(modelo_por_chassi)

    assigned = {}
    carga = [0] * num_tecnicos

    # 1) Distribuir modelos não-kwid que aparecem mais de 4 vezes (por modelo):
    modelos_especiais = df[df["_MODELO"] != "kwid"]["_MODELO"].unique()
    for modelo in modelos_especiais:
        idxs_modelo = df[df["_MODELO"] == modelo].index.tolist()
        if len(idxs_modelo) > 4:
            # Distribuir 1 por técnico igualitariamente
            dist = distribuir_entre_tecnicos(idxs_modelo, num_tecnicos)
            # Atualiza assigned e carga
            for idx, tech in dist.items():
                assigned[idx] = tech
                carga[tech] += 1

    # 2) Agora distribui o restante dos veículos, agrupando por faixa
    # Veículos já atribuídos não entram
    faixas = df["_FAIXA"].unique()
    # Ordena faixas para preservar ordem
    faixas = [f for f in df["_FAIXA"] if f in faixas]
    faixas = list(dict.fromkeys(faixas))  # remove duplicados mantendo ordem

    for faixa in faixas:
        idxs_faixa = df[(df["_FAIXA"] == faixa)].index.tolist()
        # Filtra os não atribuídos
        idxs_nao_atribuido = [i for i in idxs_faixa if i not in assigned]

        if not idxs_nao_atribuido:
            continue

        dist = distribuir_entre_tecnicos(idxs_nao_atribuido, num_tecnicos)
        for idx, tech in dist.items():
            assigned[idx] = tech
            carga[tech] += 1

    # 3) Para garantir max-min carga <= 1, faz balanceamento simples trocando cargas
    def diff_carga():
        return max(carga) - min(carga)

    tentativas = 0
    max_tentativas = 1000
    while diff_carga() > 1 and tentativas < max_tentativas:
        tentativas += 1
        tech_max = carga.index(max(carga))
        tech_min = carga.index(min(carga))

        # Tenta encontrar um idx para trocar
        idxs_do_max = [i for i, t in assigned.items() if t == tech_max]
        if not idxs_do_max:
            break
        idx_troca = idxs_do_max[-1]

        assigned[idx_troca] = tech_min
        carga[tech_max] -= 1
        carga[tech_min] += 1

    # 4) Aplica nomes dos técnicos
    df["TECNICO"] = df.index.map(lambda i: nomes_tecnicos[assigned[i]] if i in assigned else "")

    # Mantém ordem original para salvar
    df_saida = df.sort_values("_orig_index").drop(columns=["_orig_index", "_FAIXA", "_MODELO"])

    st.success("Distribuição concluída.")
    st.write("Carga por técnico:")
    st.table(pd.DataFrame({"Técnico": nomes_tecnicos, "Qtd": carga}))

    st.write("Amostra da planilha resultante:")
    st.dataframe(df_saida.head(200))

    # Download da planilha
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

