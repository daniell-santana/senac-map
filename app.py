import streamlit as st
import folium
from streamlit_folium import st_folium
import geopandas as gpd
import pandas as pd
from collections import Counter
import matplotlib.cm as cm
import matplotlib.colors as mcolors


# ==============================
# Função para criar o mapa
# ==============================
def create_map(unidades_temas, municipios_atuacao, geojson, unidades_sel, temas_sel, color_map):
    # filtra dados por unidade
    if unidades_sel != "Todas":
        unidades_temas = unidades_temas[unidades_temas["Unidade"] == unidades_sel]

    # filtra dados por temas
    if temas_sel:
        unidades_temas = unidades_temas[unidades_temas["Tema"].isin(temas_sel)]

    # mapeia temas por município
    temas_por_mun = unidades_temas.groupby("Municipio")["Tema"].apply(list).to_dict()

    # pega tema mais comum em cada município
    tema_pred = {m: Counter(lst).most_common(1)[0][0] for m, lst in temas_por_mun.items()}

    # cria mapa base
    m = folium.Map(location=[-23.55, -46.63], zoom_start=7)

    # adiciona polígonos
    folium.GeoJson(
        geojson,
        style_function=lambda feature: {
            "fillColor": color_map.get(tema_pred.get(feature["properties"]["name"]), "lightgray"),
            "color": "black",
            "weight": 0.5,
            "fillOpacity": 0.6,
        },
        tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["Município:"]),
    ).add_to(m)

    return m


# ==============================
# Função principal
# ==============================
def main():
    st.set_page_config(layout="wide")
    st.title("📍 Mapa Interativo - Unidades e Temas")

    # ------------------------------
    # Carregar dados de exemplo
    # ------------------------------
    municipios_atuacao = pd.DataFrame({
        "Municipio": ["São Paulo", "Campinas", "Santos", "Ribeirão Preto", "Sorocaba"],
        "Unidade": ["PIN", "PIR", "PIR", "PIN", "PIN"],
        "Tema": ["Educação", "Saúde", "Tecnologia", "Educação", "Artes"],
    })

    geojson = gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    geojson = geojson[geojson["name"].isin(["Brazil"])]  # simplificação

    # ------------------------------
    # Sidebar com filtros
    # ------------------------------
    st.sidebar.header("Filtros")

    # filtro de Unidade
    unidades = ["Todas"] + sorted(municipios_atuacao["Unidade"].unique().tolist())
    unidade_sel = st.sidebar.selectbox("Unidade", unidades)

    # filtro de Temas
    temas = sorted(municipios_atuacao["Tema"].unique().tolist())

    # botões selecionar todos/nenhum
    col1, col2 = st.sidebar.columns([1, 1])
    with col1:
        if st.button("Selecionar todos"):
            st.session_state.temas_sel = temas
    with col2:
        if st.button("Limpar todos"):
            st.session_state.temas_sel = []

    # múltipla escolha
    if "temas_sel" not in st.session_state:
        st.session_state.temas_sel = temas

    temas_sel = st.sidebar.multiselect(
        "Temas", temas, default=st.session_state.temas_sel
    )

    # ------------------------------
    # Geração de cores automáticas
    # ------------------------------
    cmap = cm.get_cmap("tab20", len(temas))
    color_map = {tema: mcolors.rgb2hex(cmap(i)) for i, tema in enumerate(temas)}

    # legenda manual no sidebar
    st.sidebar.markdown("### Legenda")
    for tema in temas:
        cor = color_map[tema]
        st.sidebar.markdown(f"<span style='color:{cor}'>⬤</span> {tema}", unsafe_allow_html=True)

    # ------------------------------
    # Renderizar mapa
    # ------------------------------
    mapa = create_map(municipios_atuacao, municipios_atuacao, geojson, unidade_sel, temas_sel, color_map)
    st_folium(mapa, width=900, height=600)


if __name__ == "__main__":
    main()
