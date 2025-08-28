import streamlit as st

st.set_page_config(page_title="Mapa SENAC", layout="wide")
st.title("🗺️ Mapa Interativo SENAC")

# URL do GitHub Pages
mapa_url = "https://daniell-santana.github.io/senac-map/mapa_interativo_senac_v5.html"

# Iframe responsivo
st.components.v1.iframe(
    mapa_url,
    height=800,
    scrolling=True
)

# Link direto como fallback
st.markdown(f"""
**💡 Alternativa:** [Abrir mapa em nova janela]({mapa_url})
""")
