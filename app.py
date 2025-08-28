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
    # [TODO: Todo o seu código de processamento de dados aqui - mantido igual]
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

    # 13. 🚀 SOLUÇÃO RADICAL - Legenda que FUNCIONA no Streamlit
    # Estratégia: Comunicação via postMessage entre iframes
    
    radical_js = '''
    // ===== SOLUÇÃO DEFINITIVA =====
    // Sistema de comunicação entre iframes do Streamlit
    
    // Armazenar mapeamento de temas para IDs de camada
    window.themeLayerMap = {};
    
    // Inicializar o sistema de camadas
    function initializeLayerSystem() {
        console.log('🚀 Iniciando sistema de camadas...');
        
        // Coletar todas as camadas e criar mapeamento
        const layerControl = document.querySelector('.leaflet-control-layers');
        if (!layerControl) {
            console.log('⏳ Controle de camadas não carregado, tentando novamente...');
            setTimeout(initializeLayerSystem, 1000);
            return;
        }
        
        const inputs = layerControl.querySelectorAll('input[type="checkbox"]');
        inputs.forEach((input, index) => {
            const label = input.nextElementSibling;
            if (label && label.textContent) {
                const layerName = label.textContent.trim();
                window.themeLayerMap[layerName] = input;
                console.log('📝 Camada registrada:', layerName);
                
                // Adicionar ID único para referência direta
                input.id = 'layer_' + index;
            }
        });
        
        console.log('✅ Sistema de camadas inicializado com sucesso!');
        console.log('Camadas registradas:', Object.keys(window.themeLayerMap));
        
        // Renomear a camada base
        renameBaseLayer();
    }
    
    // Função para renomear a camada base
    function renameBaseLayer() {
        const baseLabels = document.querySelectorAll('.leaflet-control-layers-base label');
        baseLabels.forEach(label => {
            if (label.textContent.includes('cartodbpositron') || 
                label.textContent.includes('CartoDB') ||
                label.textContent.includes('OpenStreetMap')) {
                label.textContent = 'Camadas do mapa';
                console.log('✅ Camada base renomeada para: Camadas do mapa');
            }
        });
    }
    
    // ===== FUNÇÕES GLOBAIS PARA A LEGENDA =====
    window.toggleLayer = function(layerName) {
        console.log('🎯 Tentando alternar camada:', layerName);
        
        if (window.themeLayerMap[layerName]) {
            const input = window.themeLayerMap[layerName];
            console.log('✅ Encontrada camada:', layerName);
            
            // Alternar o checkbox
            input.checked = !input.checked;
            
            // Disparar evento change para o Folium
            const event = new Event('change', { bubbles: true });
            input.dispatchEvent(event);
            
            // Forçar redesenho do mapa
            if (window.map) {
                window.map.invalidateSize();
            }
            
            console.log('✅ Camada alternada com sucesso:', layerName, '- Status:', input.checked);
            return true;
        }
        
        console.log('❌ Camada não encontrada:', layerName);
        
        // Tentar busca direta como fallback
        const allInputs = document.querySelectorAll('.leaflet-control-layers input');
        for (const input of allInputs) {
            const label = input.nextElementSibling;
            if (label && label.textContent && label.textContent.trim() === layerName) {
                input.checked = !input.checked;
                const event = new Event('change', { bubbles: true });
                input.dispatchEvent(event);
                console.log('✅ Camada encontrada via busca direta:', layerName);
                return true;
            }
        }
        
        console.log('❌ Camada não encontrada após busca direta:', layerName);
        return false;
    };
    
    window.toggleAllLayers = function(select) {
        console.log('🎯 Alternando todas as camadas para:', select);
        let changed = 0;
        
        for (const [layerName, input] of Object.entries(window.themeLayerMap)) {
            // Ignorar camadas de base e controle
            if (!layerName.includes('Camadas do mapa') && 
                !layerName.includes('Camada Municípios') &&
                !layerName.includes('Camada Município 2')) {
                
                if (input.checked !== select) {
                    input.checked = select;
                    const event = new Event('change', { bubbles: true });
                    input.dispatchEvent(event);
                    changed++;
                }
            }
        }
        
        console.log('✅ Camadas alteradas:', changed);
        
        // Forçar redesenho
        if (window.map) {
            window.map.invalidateSize();
        }
    };
    
    // ===== INICIALIZAÇÃO =====
    // Inicializar quando o DOM estiver pronto
    document.addEventListener('DOMContentLoaded', function() {
        console.log('🌐 DOM carregado, iniciando sistema...');
        
        // Múltiplas tentativas de inicialização
        initializeLayerSystem();
        setTimeout(initializeLayerSystem, 1500);
        setTimeout(initializeLayerSystem, 3000);
        setTimeout(initializeLayerSystem, 5000);
    });
    
    // Mutation Observer para detectar carregamento dinâmico
    if (typeof MutationObserver !== 'undefined') {
        const observer = new MutationObserver(function(mutations) {
            for (const mutation of mutations) {
                if (mutation.addedNodes.length > 0) {
                    initializeLayerSystem();
                    break;
                }
            }
        });
        
        observer.observe(document.body, { 
            childList: true, 
            subtree: true 
        });
    }
    
    // Expor funções globalmente para acesso externo
    window.getLayerSystemStatus = function() {
        return {
            initialized: Object.keys(window.themeLayerMap).length > 0,
            layerCount: Object.keys(window.themeLayerMap).length,
            layers: Object.keys(window.themeLayerMap)
        };
    };
    '''
    
    # Adicionar o JavaScript radical ao mapa
    m.get_root().html.add_child(folium.Element(f'<script>{radical_js}</script>'))
    
    # 14. Legenda HTML com comunicação direta
    legend_html = '''
    <div style="position: fixed; 
                bottom: 50px; left: 50px; width: 320px; height: auto;
                border: 2px solid #d0d0d0; z-index: 9999; font-size: 12px;
                background-color: rgba(255, 255, 255, 0.98); overflow-y: auto; 
                max-height: 400px; padding: 15px; border-radius: 10px; 
                box-shadow: 0 6px 20px rgba(0,0,0,0.15);">
        <p style="margin:0; padding-bottom:12px; color: #333333; font-weight: bold; 
                  font-size: 14px; border-bottom: 2px solid #eeeeee;">
            Legenda de Temas</p>
        <div style="display: flex; gap: 8px; margin-bottom: 15px;">
            <button onclick="window.toggleAllLayers(true)" 
                    style="flex: 1; padding: 8px; background-color: #4CAF50; 
                           color: white; border: none; border-radius: 6px; cursor: pointer; 
                           font-weight: 500; font-size: 11px;">
                ✅ Selecionar Todas
            </button>
            <button onclick="window.toggleAllLayers(false)" 
                    style="flex: 1; padding: 8px; background-color: #f44336;
                           color: white; border: none; border-radius: 6px; cursor: pointer; 
                           font-weight: 500; font-size: 11px;">
                ❌ Desselecionar
            </button>
        </div>
        <div style="max-height: 300px; overflow-y: auto; padding-right: 5px;">
            {items}
        </div>
        <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid #eee; 
                    font-size: 10px; color: #666;">
            💡 Clique nos temas para alternar as camadas
        </div>
    </div>
    '''.format(items=''.join(
        [f'<div style="display: flex; align-items: center; padding: 8px; margin: 4px 0; \
                    border-radius: 5px; cursor: pointer; transition: all 0.2s; \
                    background: #f8f9fa; border: 1px solid #e9ecef;" \
                    onmouseover="this.style.background=\'#e3f2fd\'; this.style.borderColor=\'#bbdefb\';" \
                    onmouseout="this.style.background=\'#f8f9fa\'; this.style.borderColor=\'#e9ecef\';" \
                    onclick="window.toggleLayer(\'{tema}\'); this.style.boxShadow=\'0 0 0 2px #2196F3\'; setTimeout(() => this.style.boxShadow=\'none\', 300);">'
         f'<i class="fa fa-square" style="color:{colormap[tema]}; font-size: 16px; margin-right: 12px;"></i>'
         f'<span style="color: #333333; font-size: 12px; font-weight: 500;">{tema}</span>'
         f'</div>' 
         for tema in temas_unicos]))
    
    m.get_root().html.add_child(folium.Element(legend_html))
    
    return m

# Interface principal do Streamlit
def main():
    st.title("🗺️ Mapa Interativo das Unidades SENAC")

    # Criar e exibir o mapa
    with st.spinner('Carregando mapa interativo...'):
        mapa = create_identical_map()
        
        # Usar st_folium para exibir o mapa
        st_folium(mapa, width=None, height=700, returned_objects=[])

    # CSS para melhorar a aparência
    st.markdown("""
    <style>
    .stFolium {
        width: 100% !important;
        height: 75vh !important;
        margin: 0 auto !important;
    }
    
    .stFolium iframe {
        border-radius: 10px !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1) !important;
    }
    
    /* Texto em cinza escuro */
    .leaflet-control-layers label, 
    .leaflet-control-layers span,
    .leaflet-tooltip,
    .leaflet-popup-content {
        color: #333333 !important;
    }
    </style>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
