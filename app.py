import streamlit as st
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import json
from collections import Counter
import folium
from streamlit_folium import st_folium
from shapely.ops import unary_union
from shapely.validation import make_valid
import matplotlib.colors as mcolors

# Configuração da página
st.set_page_config(
    page_title="Mapa Interativo SENAC",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================
# Função para criar o mapa
# =====================================
def create_identical_map(unidade_sel, temas_sel):
    # 1. Carregar os dados
    excel_file = "Temas_Unidades.xlsx"
    unidades_temas = pd.read_excel(excel_file, sheet_name="Unidades x Temas")
    municipios_atuacao = pd.read_excel(excel_file, sheet_name="Municípios - Área de Atuação")

    # 2. Processar os temas
    unidades_temas['Temas'] = unidades_temas['Temas'].str.split(r',\s*')
    temas_expandidos = unidades_temas.explode('Temas').dropna(subset=['Temas'])
    temas_expandidos['Temas'] = temas_expandidos['Temas'].str.strip()

    # 3. Relacionar municípios com unidades e temas
    municipio_para_unidade = municipios_atuacao.set_index('MUNICÍPIOS')['AREA DE ATUAÇÃO OPERACIONAL SENAC SP'].to_dict()

    unidade_para_municipios = {}
    for municipio, unidade in municipio_para_unidade.items():
        if pd.notna(unidade):
            unidade_para_municipios.setdefault(unidade, []).append(municipio)

    temas_por_municipio = {}
    for municipio, unidade in municipio_para_unidade.items():
        if pd.notna(unidade):
            temas = temas_expandidos[temas_expandidos['UNIDADE/GERÊNCIA'] == unidade]['Temas'].tolist()
            if temas:
                temas_por_municipio[municipio] = temas

    tema_predominante = {m: Counter(t).most_common(1)[0][0] for m, t in temas_por_municipio.items()}

    # 5. Carregar o GeoJSON
    with open('geojs-35-mun.json', 'r', encoding='utf-8') as f:
        geojson = json.load(f)

    gdf = gpd.GeoDataFrame.from_features(geojson['features'])
    gdf.crs = "EPSG:4326"

    # 7. Mapear os temas predominantes
    gdf['tema_predominante'] = gdf['name'].map(tema_predominante)

    # 🔹 aplicar filtros
    if unidade_sel != "Todas":
        municipios_filtrados = unidade_para_municipios.get(unidade_sel, [])
        gdf = gdf[gdf['name'].isin(municipios_filtrados)]

    if temas_sel:
        gdf = gdf[gdf['tema_predominante'].isin(temas_sel)]

    # 8. Criar mapa base
    m = folium.Map(location=[-22, -48], zoom_start=7, tiles='CartoDB positron')

    # 9. Colormap dinâmico
    temas_unicos = sorted(temas_expandidos['Temas'].unique())
    cmap = plt.cm.get_cmap("tab20", len(temas_unicos))
    colormap = {t: mcolors.rgb2hex(cmap(i)[:3]) for i, t in enumerate(temas_unicos)}

    # 10. Adicionar municípios ao mapa
    folium.GeoJson(
        gdf,
        style_function=lambda feature: {
            'fillColor': colormap.get(feature['properties'].get('tema_predominante'), 'lightgray'), 
            'color': 'black',
            'weight': 0.5,
            'fillOpacity': 0.7
        },
        tooltip=folium.features.GeoJsonTooltip(
            fields=['name', 'tema_predominante'],
            aliases=['Município:', 'Tema predominante:'],
            localize=True
        )
    ).add_to(m)

    return m, temas_unicos


# =====================================
# Interface principal
# =====================================
def main():
    st.title("🗺️ Mapa Interativo das Unidades SENAC")

    # Sidebar com filtros
    st.sidebar.header("🎛️ Filtros")

    # carregar excel só para pegar lista de filtros
    excel_file = "Temas_Unidades.xlsx"
    unidades_temas = pd.read_excel(excel_file, sheet_name="Unidades x Temas")

    unidades = ["Todas"] + sorted(unidades_temas["UNIDADE/GERÊNCIA"].unique().tolist())
    unidade_sel = st.sidebar.selectbox("Selecione a Unidade", unidades)

    # todos os temas
    temas_all = sorted(set(sum([t.split(", ") for t in unidades_temas["Temas"].dropna()], [])))

    # inicializar estado
    if "temas_sel" not in st.session_state:
        st.session_state.temas_sel = temas_all

    col1, col2 = st.sidebar.columns([1, 1])
    with col1:
        if st.button("Selecionar todos"):
            st.session_state.temas_sel = temas_all
    with col2:
        if st.button("Limpar todos"):
            st.session_state.temas_sel = []

    temas_sel = st.sidebar.multiselect("Selecione os Temas", temas_all, default=st.session_state.temas_sel)
    st.session_state.temas_sel = temas_sel

    # Criar e exibir mapa
    with st.spinner('Carregando mapa interativo...'):
        mapa, temas_unicos = create_identical_map(unidade_sel, temas_sel)
        st_folium(mapa, width=None, height=700, returned_objects=[])


if __name__ == "__main__":
    main()
