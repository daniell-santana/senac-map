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

# Configuração da página
st.set_page_config(
    page_title="Mapa Interativo SENAC",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Título do aplicativo
st.title("🗺️ Mapa Interativo das Unidades SENAC")
st.markdown("Visualização das áreas de atuação e temas predominantes por município")

# Função principal
def main():
    try:
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

        # Criar dicionário de municípios por unidade
        unidade_para_municipios = {}
        for municipio, unidade in municipio_para_unidade.items():
            if pd.notna(unidade):
                if unidade not in unidade_para_municipios:
                    unidade_para_municipios[unidade] = []
                unidade_para_municipios[unidade].append(municipio)

        temas_por_municipio = {}
        for municipio, unidade in municipio_para_unidade.items():
            if pd.notna(unidade):
                temas = temas_expandidos[temas_expandidos['UNIDADE/GERÊNCIA'] == unidade]['Temas'].tolist()
                if temas:
                    temas_por_municipio[municipio] = temas

        # 4. Determinar o tema predominante
        tema_predominante = {m: Counter(t).most_common(1)[0][0] for m, t in temas_por_municipio.items()}

        # 5. Carregar o GeoJSON
        with open('geojs-35-mun.json', 'r', encoding='utf-8') as f:
            geojson_data = json.load(f)

        # 6. Converter para GeoDataFrame e definir CRS
        gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
        gdf.crs = "EPSG:4326"

        # 7. Mapear os temas predominantes
        gdf['tema_predominante'] = gdf['name'].map(tema_predominante)

        # Criar colormap
        temas_unicos = sorted(temas_expandidos['Temas'].unique())
        colors = plt.cm.tab20(range(len(temas_unicos)))
        colormap = {t: '#%02x%02x%02x' % tuple(int(x*255) for x in colors[i][:3]) for i, t in enumerate(temas_unicos)}

        # 8. Criar mapa interativo
        m = folium.Map(location=[-22, -48], zoom_start=7, tiles='CartoDB positron')

        # 9. Adicionar municípios ao mapa
        folium.GeoJson(
            gdf,
            style_function=lambda feature: {
                'fillColor': colormap.get(feature['properties'].get('tema_predominante', 'lightgray')), 
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

        # 10. Criar camada Município 2 (bordas)
        gdf_projected = gdf.to_crs(epsg=3857)

        areas_atuacao_geometrias = {}
        for unidade, municipios in unidade_para_municipios.items():
            municipios_unidade = gdf_projected[gdf_projected['name'].isin(municipios)]
            
            if not municipios_unidade.empty:
                try:
                    geometrias_validas = [make_valid(geom) for geom in municipios_unidade.geometry]
                    geometria_unida = unary_union(geometrias_validas)
                    
                    if geometria_unida.is_empty:
                        geometria_unida = geometrias_validas[0].convex_hull
                        for geom in geometrias_validas[1:]:
                            geometria_unida = geometria_unida.union(geom.convex_hull)
                    
                    areas_atuacao_geometrias[unidade] = geometria_unida
                    
                except Exception as e:
                    st.warning(f"Erro ao processar unidade {unidade}: {e}")
                    bbox = municipios_unidade.total_bounds
                    from shapely.geometry import box
                    areas_atuacao_geometrias[unidade] = box(bbox[0], bbox[1], bbox[2], bbox[3])

        # Criar buffer e borda
        bordas_atuacao = []
        for unidade, geometria in areas_atuacao_geometrias.items():
            try:
                buffer_distance = 1000
                geometria_buffer = geometria.buffer(buffer_distance)
                borda = geometria_buffer.difference(geometria)
                
                if borda.is_empty:
                    borda = geometria_buffer
                    
                bordas_atuacao.append({
                    'unidade': unidade,
                    'geometry': borda
                })
                
            except Exception as e:
                st.warning(f"Erro ao criar borda para {unidade}: {e}")
                continue

        if bordas_atuacao:
            gdf_bordas = gpd.GeoDataFrame(bordas_atuacao, crs=gdf_projected.crs)
            gdf_bordas = gdf_bordas.to_crs(epsg=4326)

            folium.GeoJson(
                gdf_bordas,
                style_function=lambda feature: {
                    'fillColor': '#808080',
                    'color': '#606060',
                    'weight': 1,
                    'fillOpacity': 0.2
                }
            ).add_to(m)

        # 11. Adicionar marcadores
        for idx, row in unidades_temas.iterrows():
            if not pd.isna(row['LATITUDE']) and not pd.isna(row['LONGITUDE']):
                temas_unidade = set([t.strip() for t in row['Temas'] if pd.notna(t)])
                
                folium.Marker(
                    location=[row['LATITUDE'], row['LONGITUDE']],
                    popup=f"<b>{row['UNIDADE/GERÊNCIA']}</b><br>Temas: {', '.join(temas_unidade)}",
                    tooltip=row['SIGLA'],
                    icon=folium.Icon(color='red', icon='info-sign')
                ).add_to(m)

        # Exibir mapa
        st_folium(m, width=1200, height=700)

        # Sidebar com informações
        st.sidebar.header("📊 Estatísticas")
        st.sidebar.write(f"**Unidades:** {len(unidades_temas)}")
        st.sidebar.write(f"**Municípios com atuação:** {len(temas_por_municipio)}")
        st.sidebar.write(f"**Temas diferentes:** {len(temas_unicos)}")

        st.sidebar.header("🎨 Legenda")
        for tema, cor in colormap.items():
            st.sidebar.markdown(
                f"<span style='display: inline-block; width: 20px; height: 20px; background: {cor}; margin-right: 10px; border: 1px solid #000;'></span> **{tema}**",
                unsafe_allow_html=True
            )

    except Exception as e:
        st.error(f"❌ Erro ao carregar o mapa: {str(e)}")
        st.info("ℹ️ Verifique se os arquivos estão na pasta correta")

if __name__ == "__main__":
    main()