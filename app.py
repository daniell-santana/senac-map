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

# Configuração da página do Streamlit
st.set_page_config(
    page_title="Mapa Interativo SENAC",
    page_icon="🗺️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Função para criar o mapa idêntico ao seu script
def create_identical_map():
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
        geojson = json.load(f)

    # 6. Converter para GeoDataFrame e definir CRS
    gdf = gpd.GeoDataFrame.from_features(geojson['features'])
    gdf.crs = "EPSG:4326"

    # 7. Mapear os temas predominantes
    gdf['tema_predominante'] = gdf['name'].map(tema_predominante)

    # 8. Criar mapa interativo com Folium usando o tema Positron do OpenStreetMap
    m = folium.Map(location=[-22, -48], zoom_start=7, tiles='CartoDB positron')

    # Criar colormap
    temas_unicos = sorted(temas_expandidos['Temas'].unique())
    colors = plt.cm.tab20(range(len(temas_unicos)))
    colormap = {t: '#%02x%02x%02x' % tuple(int(x*255) for x in colors[i][:3]) for i, t in enumerate(temas_unicos)}

    # 9. Adicionar municípios ao mapa
    if gdf.crs != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")

    # Criar um FeatureGroup para os municípios com nome amigável (inicialmente escondido)
    municipios_layer = folium.FeatureGroup(name='Camada Municípios', show=False)
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
    ).add_to(municipios_layer)
    municipios_layer.add_to(m)

    # 10. Criar a nova camada "Camada Município 2" com os contornos das áreas de atuação
    gdf_projected = gdf.to_crs(epsg=3857)

    # Criar polígonos unidos para cada área de atuação
    areas_atuacao_geometrias = {}

    for unidade, municipios in unidade_para_municipios.items():
        # Filtrar municípios desta unidade
        municipios_unidade = gdf_projected[gdf_projected['name'].isin(municipios)]
        
        if not municipios_unidade.empty:
            try:
                # Corrigir geometrias inválidas primeiro
                geometrias_validas = [make_valid(geom) for geom in municipios_unidade.geometry]
                
                # Unir todos os polígonos dos municípios desta unidade
                geometria_unida = unary_union(geometrias_validas)
                
                # Se a união falhar, usar convex hull como fallback
                if geometria_unida.is_empty:
                    geometria_unida = geometrias_validas[0].convex_hull
                    for geom in geometrias_validas[1:]:
                        geometria_unida = geometria_unida.union(geom.convex_hull)
                
                areas_atuacao_geometrias[unidade] = geometria_unida
                
            except Exception as e:
                print(f"Erro ao processar unidade {unidade}: {e}")
                # Fallback: usar o bounding box dos municípios
                bbox = municipios_unidade.total_bounds
                from shapely.geometry import box
                areas_atuacao_geometrias[unidade] = box(bbox[0], bbox[1], bbox[2], bbox[3])

    # Criar buffer e borda para cada área de atuação
    bordas_atuacao = []

    for unidade, geometria in areas_atuacao_geometrias.items():
        try:
            # Criar buffer ao redor da área unida
            buffer_distance = 1000
            geometria_buffer = geometria.buffer(buffer_distance)
            
            # Subtrair a área original para obter apenas a borda
            borda = geometria_buffer.difference(geometria)
            
            # Se a diferença falhar, usar apenas o buffer
            if borda.is_empty:
                borda = geometria_buffer
                
            bordas_atuacao.append({
                'unidade': unidade,
                'geometry': borda
            })
            
        except Exception as e:
            print(f"Erro ao criar borda para {unidade}: {e}")
            continue

    # Criar GeoDataFrame com as bordas
    if bordas_atuacao:
        gdf_bordas = gpd.GeoDataFrame(bordas_atuacao, crs=gdf_projected.crs)
        gdf_bordas = gdf_bordas.to_crs(epsg=4326)

        # Adicionar a camada de borda ao mapa (INICIALMENTE VISÍVEL) - SEM TOOLTIP
        municipios_border_layer = folium.FeatureGroup(name='Camada Município 2', show=True)
        folium.GeoJson(
            gdf_bordas,
            style_function=lambda feature: {
                'fillColor': '#808080',
                'color': '#606060',
                'weight': 1,
                'fillOpacity': 0.2
            }
        ).add_to(municipios_border_layer)
        municipios_border_layer.add_to(m)

    # 11. Criar FeatureGroups para cada tema (TODOS INICIALMENTE VISÍVEIS)
    feature_groups = {}
    for tema in temas_unicos:
        feature_groups[tema] = folium.FeatureGroup(name=tema, show=True)

    # Adicionar marcadores das unidades SENAC aos respectivos FeatureGroups
    for idx, row in unidades_temas.iterrows():
        if not pd.isna(row['LATITUDE']) and not pd.isna(row['LONGITUDE']):
            temas_unidade = set([t.strip() for t in row['Temas'] if pd.notna(t)])
            
            for tema in temas_unidade:
                if tema in feature_groups:
                    folium.Marker(
                        location=[row['LATITUDE'], row['LONGITUDE']],
                        popup=f"<b>{row['UNIDADE/GERÊNCIA']}</b><br>Temas: {', '.join(temas_unidade)}",
                        tooltip=row['SIGLA'],
                        icon=folium.Icon(color='red', icon='info-sign')
                    ).add_to(feature_groups[tema])

    # Adicionar todos os FeatureGroups ao mapa
    for group in feature_groups.values():
        group.add_to(m)

    # 12. Adicionar controle de camadas personalizado
    layer_control = folium.LayerControl(
        position='topright',
        collapsed=True,
        autoZIndex=True
    )
    layer_control.add_to(m)

    # 13. Adicionar legenda interativa com botão "Selecionar Todas"
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 300px; height: auto;
                border: 2px solid #cccccc; z-index: 9999; font-size: 12px;
                background-color: white; overflow-y: auto; max-height: 300px;
                padding: 10px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
        <p style="margin:0; padding-bottom:8px; color: #333333; font-weight: bold; border-bottom: 1px solid #eeeeee;">
            Legenda de Temas</p>
        <button onclick="window.toggleAllLayers(true)" style="margin-bottom:8px; width:100%; padding:6px; 
                background-color: #f8f9fa; color: #333333; border: 1px solid #dddddd; border-radius:4px; 
                cursor: pointer; font-size:11px;">Selecionar Todas</button>
        <button onclick="window.toggleAllLayers(false)" style="margin-bottom:12px; width:100%; padding:6px;
                background-color: #f8f9fa; color: #333333; border: 1px solid #dddddd; border-radius:4px;
                cursor: pointer; font-size:11px;">Desselecionar Todas</button>
        {items}
    </div>
    '''.format(items=''.join(
        [f'<p style="margin:4px 0; cursor:pointer; color: #333333; font-size:11px; padding:2px;" onclick="window.toggleLayer(\'{tema}\')">'
         f'<i class="fa fa-square" style="color:{colormap[tema]}; margin-right:8px;"></i> {tema}</p>' 
         for tema in temas_unicos]))
    
    m.get_root().html.add_child(folium.Element(legend_html))
    
    # Adicionar JavaScript para controle interativo - VERSÃO STREAMLIT COMPATÍVEL
    m.get_root().html.add_child(folium.Element('''
    <script>
    // Tornar funções globais para acesso pelo Streamlit
    window.toggleLayer = function(temaNome) {
        console.log('Tentando alternar tema:', temaNome);
        
        // Aguardar o Folium carregar completamente
        setTimeout(function() {
            const layerControls = document.querySelectorAll('.leaflet-control-layers input');
            console.log('Inputs encontrados:', layerControls.length);
            
            layerControls.forEach(input => {
                const label = input.nextElementSibling;
                if (label && label.textContent && label.textContent.trim() === temaNome) {
                    console.log('Encontrado tema:', temaNome);
                    input.click();
                    // Forçar atualização visual
                    const event = new Event('change', { bubbles: true });
                    input.dispatchEvent(event);
                }
            });
        }, 1000);
    };
    
    window.toggleAllLayers = function(select) {
        console.log('Toggle all layers:', select);
        
        setTimeout(function() {
            const inputs = document.querySelectorAll('.leaflet-control-layers input');
            console.log('Total inputs:', inputs.length);
            
            inputs.forEach(input => {
                if (input.type === 'checkbox') {
                    const labelText = input.nextElementSibling ? input.nextElementSibling.textContent : '';
                    if (labelText && 
                        !labelText.includes('OpenStreetMap') && 
                        !labelText.includes('Camada Municípios') &&
                        !labelText.includes('Camada Município 2')) {
                        if (input.checked !== select) {
                            input.click();
                            // Forçar atualização
                            const event = new Event('change', { bubbles: true });
                            input.dispatchEvent(event);
                        }
                    }
                }
            });
        }, 1000);
    };
    
    // Função auxiliar para encontrar elementos por texto
    window.findLayerByText = function(text) {
        const labels = document.querySelectorAll('.leaflet-control-layers label');
        for (let label of labels) {
            if (label.textContent.trim() === text) {
                const input = label.querySelector('input');
                if (input) return input;
            }
        }
        return null;
    };
    
    // Inicialização quando o mapa estiver pronto
    document.addEventListener('DOMContentLoaded', function() {
        console.log('Mapa carregado, inicializando legenda...');
        
        // Aguardar o Folium carregar os controles
        setTimeout(function() {
            const baseLayers = document.querySelectorAll('.leaflet-control-layers-base label');
            baseLayers.forEach(layer => {
                if (layer.textContent.includes('OpenStreetMap')) {
                    layer.textContent = 'Controle de Camadas';
                }
            });
            
            console.log('Controles de camadas inicializados');
        }, 2000);
    });
    
    // Alternative approach - usar mutation observer para detectar quando os controles são carregados
    if (typeof MutationObserver !== 'undefined') {
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.addedNodes && mutation.addedNodes.length > 0) {
                    const layerControls = document.querySelector('.leaflet-control-layers');
                    if (layerControls) {
                        console.log('Controles de camadas detectados via MutationObserver');
                        observer.disconnect();
                    }
                }
            });
        });
        
        observer.observe(document.body, {
            childList: true,
            subtree: true
        });
    }
    </script>
    '''))

    return m

# Interface principal do Streamlit
def main():
    st.title("🗺️ Mapa Interativo das Unidades SENAC")

    # Criar e exibir o mapa
    with st.spinner('Carregando mapa interativo...'):
        mapa = create_identical_map()
        
        # Usar st_folium para exibir o mapa centralizado e responsivo
        st_folium(mapa, width=None, height=700, returned_objects=[])

    # CSS para centralizar e tornar o mapa totalmente responsivo
    st.markdown("""
    <style>
    /* Container principal do mapa - CENTRALIZADO */
    .stFolium {
        width: 95% !important;
        margin: 0 auto !important;
        height: 75vh !important;
        display: flex !important;
        justify-content: center !important;
    }
    
    /* Folium iframe dentro do container */
    .stFolium iframe {
        width: 100% !important;
        height: 100% !important;
        border-radius: 10px !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.15) !important;
    }
    
    /* Ajustar para dispositivos móveis */
    @media (max-width: 768px) {
        .stFolium {
            width: 100% !important;
            height: 65vh !important;
            margin: 0 !important;
            padding: 0 5px !important;
        }
    }
    
    /* Ajustar para telas muito grandes */
    @media (min-width: 1600px) {
        .stFolium {
            width: 85% !important;
            height: 80vh !important;
        }
    }
    
    /* Garantir que o streamlit não adicione margens extras */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        padding-left: 3rem;
        padding-right: 3rem;
    }
    </style>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
