import streamlit as st
import pandas as pd
import geopandas as gpd
import matplotlib.pyplot as plt
import json
from collections import Counter
import folium
from streamlit_folium import st_folium

# --- Configuração da página ---
st.set_page_config(page_title="Mapa Interativo SENAC",
                   page_icon="🗺️",
                   layout="wide")

def load_data():
    excel_file = "Temas_Unidades.xlsx"
    unidades_temas = pd.read_excel(excel_file, sheet_name="Unidades x Temas")
    municipios_atuacao = pd.read_excel(excel_file, sheet_name="Municípios - Área de Atuação")
    geojson = json.load(open('geojs-35-mun.json', encoding='utf-8'))
    return unidades_temas, municipios_atuacao, geojson

def create_map(unidades_temas, municipios_atuacao, geojson, unidades_sel, temas_sel):
    # Processamento dos Temas
    unidades_temas['Temas'] = unidades_temas['Temas'].str.split(r',\s*')
    temas_exp = unidades_temas.explode('Temas').dropna(subset=['Temas'])
    temas_exp['Temas'] = temas_exp['Temas'].str.strip()

    # Dicionários auxiliares
    mun_para_uni = municipios_atuacao.set_index('MUNICÍPIOS')['AREA DE ATUAÇÃO OPERACIONAL SENAC SP'].to_dict()
    temas_por_mun = {m: temas_exp[temas_exp['UNIDADE/GERÊNCIA'] == uni]['Temas'].tolist()
                     for m, uni in mun_para_uni.items() if pd.notna(uni)}

    # Tema predominante por município
    tema_pred = {m: Counter(lst).most_common(1)[0][0] for m, lst in temas_por_mun.items()}

    # GeoDataFrame
    gdf = gpd.GeoDataFrame.from_features(geojson['features'])
    gdf.crs = "EPSG:4326"
    gdf['tema_predominante'] = gdf['name'].map(tema_pred)

    # Preparar cores
    temas_unicos = sorted(temas_exp['Temas'].unique())
    colors = plt.cm.tab20(range(len(temas_unicos)))
    colormap = {t: '#%02x%02x%02x' % tuple(int(c*255) for c in colors[i][:3])
                for i, t in enumerate(temas_unicos)}

    # Mapa base
    m = folium.Map(location=[-22, -48], zoom_start=7, tiles='CartoDB positron')

    # Adicionar municípios com cor do tema predominante
    folium.GeoJson(
        gdf,
        style_function=lambda feat: {
            'fillColor': colormap.get(feat['properties'].get('tema_predominante', ''), 'lightgray'),
            'color': 'black', 'weight': 0.3, 'fillOpacity': 0.6
        },
        tooltip=folium.features.GeoJsonTooltip(
            fields=['name', 'tema_predominante'],
            aliases=['Município:', 'Tema predominante:']
        )
    ).add_to(m)

    # Adicionar FeatureGroups por tema, apenas os selecionados
    for tema in temas_unicos:
        if tema in temas_sel:
            fg = folium.FeatureGroup(name=tema, show=True)
            df_u = unidades_temas[unidades_temas['UNIDADE/GERÊNCIA'].isin(unidades_sel)]
            for idx, row in df_u.iterrows():
                temas_row = [t.strip() for t in row['Temas'] if pd.notna(t)]
                if tema in temas_row and pd.notna(row['LATITUDE']) and pd.notna(row['LONGITUDE']):
                    folium.Marker(
                        location=[row['LATITUDE'], row['LONGITUDE']],
                        popup=f"{row['UNIDADE/GERÊNCIA']}<br>Temas: {', '.join(temas_row)}",
                        tooltip=row['SIGLA'],
                        icon=folium.Icon(color='red', icon='info-sign')
                    ).add_to(fg)
            fg.add_to(m)

    # Layer control
    folium.LayerControl(collapsed=False).add_to(m)
    return m, temas_unicos

def main():
    st.title("🗺️ Mapa Interativo das Unidades SENAC")

    unidades_temas, municipios_atuacao, geojson = load_data()

    # Sidebar: filtro de Unidade e Temas
    st.sidebar.header("Filtros")
    unidades_disponiveis = sorted(unidades_temas['UNIDADE/GERÊNCIA'].dropna().unique())
    unidades_sel = st.sidebar.multiselect("Unidade / Gerência", options=unidades_disponiveis, default=unidades_disponiveis)

    _, temas_unicos = create_map(unidades_temas, municipios_atuacao, geojson, unidades_sel, [])
    st.sidebar.subheader("Temas (cores)")
    temas_sel = st.sidebar.multiselect("Selecione os temas", options=temas_unicos, default=temas_unicos)

    mapa, _ = create_map(unidades_temas, municipios_atuacao, geojson, unidades_sel, temas_sel)

    with st.spinner("Carregando o mapa..."):
        st_folium(mapa, width="100%", height=700, returned_objects=[])

if __name__ == "__main__":
    main()
