import os
import streamlit as st
import pymysql
import pandas as pd
import time
import pydeck as pdk
from datetime import datetime
from fpdf import FPDF 
import matplotlib.pyplot as plt
import io
import tempfile
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

# ==========================================================
# SESSION STATE AND CONFIGURATION
# ==========================================================

if "is_tracking" not in st.session_state:
    st.session_state["is_tracking"] = False
if "current_session_id" not in st.session_state:
    st.session_state["current_session_id"] = None
if "pdf_ready" not in st.session_state:
    st.session_state["pdf_ready"] = None
# One WhatsApp notification per alert (avoids spam on Streamlit reruns)
if "whatsapp_sent_for_session" not in st.session_state:
    st.session_state["whatsapp_sent_for_session"] = {}

st.set_page_config(page_title="Poste de Contrôle - Casque Intelligent", layout="wide")

DB_CONFIG = {
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD', ''),
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', '3306')),
    'database': os.getenv('DB_NAME', 'Projet_casque'),
    'cursorclass': pymysql.cursors.DictCursor
}

# Twilio WhatsApp configuration (optional: notifications are disabled if unset)
TWILIO_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_WHATSAPP_NUMBER = os.getenv('TWILIO_WHATSAPP_FROM', 'whatsapp:+14155238886')  # Twilio sandbox number
ALERT_RECIPIENT = os.getenv('ALERT_WHATSAPP_TO')  # e.g. whatsapp:+33612345678

# ==========================================================
# HELPER FUNCTIONS
# ==========================================================

def enviar_alerta_whatsapp(tipo_alerte, id_session):
    """Send a single emergency WhatsApp notification per alert and session"""
    if not (TWILIO_SID and TWILIO_TOKEN and ALERT_RECIPIENT):
        return

    # Already sent for this session and alert type: skip to avoid duplicates
    clave_alerta = f"{id_session}_{tipo_alerte}"
    if st.session_state["whatsapp_sent_for_session"].get(clave_alerta, False):
        return

    try:
        client = Client(TWILIO_SID, TWILIO_TOKEN)
        mensaje_cuerpo = f"🚨 *URGENCE CASQUE INTELLIGENT* 🚨\n\nUne alerte de type *{tipo_alerte.upper()}* a été détectée sur la session N° {id_session}.\n\nVeuillez vérifier le poste de contrôle immédiatement."
        
        client.messages.create(
            body=mensaje_cuerpo,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=ALERT_RECIPIENT
        )
        # Record successful send
        st.session_state["whatsapp_sent_for_session"][clave_alerta] = True
    except Exception as e:
        # Log to the console only, so the operator UI keeps running
        print(f"Erreur d'envoi WhatsApp: {e}")

def get_lieux():
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("SELECT IdLieu FROM lieux")
            lieux = cursor.fetchall()
        conn.close()
        return [lieu['IdLieu'] for lieu in lieux]
    except Exception as e:
        return ["Campus_Doua"]

def generer_rapport_pdf(id_session, user_data, df_trajet, v_max, alertes):
    """Build the session PDF report with trajectory and speed plots"""
    pdf = FPDF()
    pdf.add_page()
    
    # --- HEADER ---
    pdf.set_font("Helvetica", 'B', 18)
    pdf.set_text_color(41, 128, 185) # INSA blue
    pdf.cell(0, 12, "Rapport Analytique de Session / Casque Intelligent P2I", ln=True, align='C')
    pdf.set_font("Helvetica", 'I', 11)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')} | Identifiant de Session : {id_session}", ln=True, align='C')
    pdf.ln(5)
    
    # --- SECTION 1: USER PROFILE ---
    pdf.set_font("Helvetica", 'B', 14)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 10, "1. Profil de l'utilisateur", ln=True)
    pdf.set_font("Helvetica", '', 11)
    pdf.set_text_color(0, 0, 0)
    if user_data:
        pdf.cell(0, 7, f"Nom / Prénom : {user_data.get('Nom', '')} {user_data.get('Prenom', '')}", ln=True)
        pdf.cell(0, 7, f"Groupe Sanguin : {user_data.get('TypeSanguin', 'Non renseigné')}", ln=True)
        pdf.cell(0, 7, f"Allergies : {user_data.get('Allergies', 'Aucune')}", ln=True)
    pdf.ln(5)
    
    # --- SECTION 2: METRICS ---
    pdf.set_font("Helvetica", 'B', 14)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 10, "2. Analyse Cinématique Synoptique", ln=True)
    pdf.set_font("Helvetica", '', 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 7, f"Vitesse Maximale Enregistrée : {round(v_max, 2) if v_max else 0} km/h", ln=True)
    pdf.cell(0, 7, f"Volume de points GPS collectés : {len(df_trajet)} trames LoRaWAN", ln=True)
    
    if alertes:
        pdf.set_text_color(192, 57, 43)
        pdf.cell(0, 7, f"Statut Incident : ALERTE DÉTECTÉE ({alertes['TypeAlerte']})", ln=True)
    else:
        pdf.set_text_color(39, 174, 96)
        pdf.cell(0, 7, "Statut Incident : Aucun incident enregistré (Session Nominal).", ln=True)
    
    pdf.ln(10)

    # --- SECTION 3: PLOTS (TRAJECTORY AND SPEED) ---
    pdf.set_font("Helvetica", 'B', 14)
    pdf.set_text_color(44, 62, 80)
    pdf.cell(0, 10, "3. Visualisation des Données Terrains", ln=True)
    pdf.ln(2)

    if not df_trajet.empty:
        # Ensure numeric types for the plots
        df_trajet['latitude'] = pd.to_numeric(df_trajet['latitude'], errors='coerce')
        df_trajet['longitude'] = pd.to_numeric(df_trajet['longitude'], errors='coerce')
        df_trajet['MesureVitesse'] = pd.to_numeric(df_trajet['MesureVitesse'], errors='coerce')
        
        if df_trajet['latitude'].max() > 180: df_trajet['latitude'] /= 1000000.0
        if df_trajet['longitude'].max() > 180: df_trajet['longitude'] /= 1000000.0

        # Build the plots with Matplotlib
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 5))
        
        # Plot 1: trajectory (longitude / latitude)
        ax1.plot(df_trajet['longitude'], df_trajet['latitude'], marker='o', color='#0078FF', linewidth=2, markersize=4)
        ax1.set_title("Tracé de la Trajectoire (GPS)", fontsize=12, fontweight='bold')
        ax1.set_xlabel("Longitude")
        ax1.set_ylabel("Latitude")
        ax1.grid(True, linestyle='--')
        
        # Plot 2: speed profile
        ax2.plot(range(len(df_trajet)), df_trajet['MesureVitesse'], color='#FF4B4B', linewidth=2, marker='o', markersize=4)
        ax2.set_title("Évolution de la Vitesse (Cinématique)", fontsize=12, fontweight='bold')
        ax2.set_ylabel("Vitesse (km/h)")
        ax2.set_xlabel("Numéro de la trame LoRa")
        ax2.grid(True, linestyle='--')
        
        plt.tight_layout()
        
        # Save the figure to a temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmpfile:
            plt.savefig(tmpfile.name, format='png', dpi=200)
            plt.close()
            # Insert the image into the PDF
            pdf.image(tmpfile.name, x=10, y=pdf.get_y(), w=190)
            
    else:
        pdf.set_font("Helvetica", 'I', 11)
        pdf.cell(0, 10, "Données insuffisantes pour générer les relevés graphiques.", ln=True)

    return bytes(pdf.output())

# ==========================================================
# SIDEBAR (SESSION CONTROL)
# ==========================================================
with st.sidebar:
    st.header("🛠️ Gestion du Trajet")
    user_id = st.number_input("ID Utilisateur :", min_value=1, value=1)
    casque_id = st.text_input("ID Casque LoRa :", value="arduino-mkr-1310-1")
    liste_lieux = get_lieux()
    id_lieu_choisi = st.selectbox("Lieu de l'activité :", liste_lieux)
    
    st.markdown("---")
    if not st.session_state["is_tracking"]:
        if st.button("🟩 DÉMARRER LE TRAJET", use_container_width=True):
            try:
                conn = pymysql.connect(**DB_CONFIG)
                with conn.cursor() as cursor:
                    sql = "INSERT INTO sessions (DateDebut, IdentifiantUtilisateur, IdentifiantCasque, IdLieu) VALUES (NOW(), %s, %s, %s)"
                    cursor.execute(sql, (user_id, casque_id, id_lieu_choisi))
                    conn.commit()
                    st.session_state["current_session_id"] = cursor.lastrowid
                    st.session_state["is_tracking"] = True
                    st.session_state["pdf_ready"] = None 
                conn.close()
                st.rerun() 
            except Exception as e:
                st.error(f"Erreur BDD : {e}")
                
        if st.session_state["pdf_ready"] is not None:
            st.success("Session clôturée avec succès.")
            st.download_button(
                label="📄 TÉLÉCHARGER LE RAPPORT PDF",
                data=st.session_state["pdf_ready"],
                file_name=f"Rapport_Mission_Session_{st.session_state['current_session_id']}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
    else:
        if st.button("🟥 CLÔTURER LA SESSION", use_container_width=True):
            try:
                conn = pymysql.connect(**DB_CONFIG)
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE sessions SET DateFin = NOW() WHERE IdSession = %s", (st.session_state["current_session_id"],))
                    
                    cursor.execute("SELECT DateHeureMesure, latitude, longitude, MesureVitesse FROM infotrajet WHERE IdSession = %s ORDER BY DateHeureMesure ASC", (st.session_state["current_session_id"],))
                    lignes_trajet = cursor.fetchall()
                    
                    cursor.execute("SELECT MAX(MesureVitesse) as v_max FROM infotrajet WHERE IdSession = %s", (st.session_state["current_session_id"],))
                    max_vitesse = cursor.fetchone()['v_max']
                    
                    cursor.execute("SELECT TypeAlerte FROM alerte WHERE IdSession = %s ORDER BY HeureAlerte DESC LIMIT 1", (st.session_state["current_session_id"],))
                    derniere_alerte = cursor.fetchone()
                    
                    cursor.execute("SELECT * FROM utilisateur WHERE IdentifiantUtilisateur = %s", (user_id,))
                    info_user = cursor.fetchone()
                    
                    conn.commit()
                conn.close()
                
                df_final = pd.DataFrame(lignes_trajet) if lignes_trajet else pd.DataFrame()
                pdf_bytes = generer_rapport_pdf(st.session_state["current_session_id"], info_user, df_final, max_vitesse,  derniere_alerte)
                
                st.session_state["pdf_ready"] = pdf_bytes
                st.session_state["is_tracking"] = False
                st.session_state["current_session_id"] = None
                st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de la clôture : {e}")

# ==========================================================
# MAIN PANEL (REAL-TIME DASHBOARD)
# ==========================================================
st.title("🚴 Poste de Contrôle — Casque Intelligent")

if not st.session_state["is_tracking"]:
    st.info("👋 Configuration prête. Activez le suivi en démarrant un trajet.")
else:
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("SELECT DateHeureMesure, latitude, longitude, MesureVitesse FROM infotrajet WHERE IdSession = %s ORDER BY DateHeureMesure ASC", (st.session_state["current_session_id"],))
            rows = cursor.fetchall()
            
            cursor.execute("SELECT TypeAlerte FROM alerte WHERE IdSession = %s ORDER BY HeureAlerte DESC LIMIT 1", (st.session_state["current_session_id"],))
            alert_res = cursor.fetchone()
            
            sql_user = "SELECT Nom, Prenom, TypeSanguin, Allergies, ContactUrgence FROM utilisateur u JOIN sessions s ON u.IdentifiantUtilisateur = s.IdentifiantUtilisateur WHERE s.IdSession = %s"
            cursor.execute(sql_user, (st.session_state["current_session_id"],))
            user_data = cursor.fetchone()
            
            sql_secours = "SELECT l.TypeSport, l.Region, c.Contact FROM lieux l JOIN sessions s ON l.IdLieu = s.IdLieu JOIN contactsecours c ON l.IdSecours = c.IdSecours WHERE s.IdSession = %s"
            cursor.execute(sql_secours, (st.session_state["current_session_id"],))
            secours_data = cursor.fetchone()
        conn.close()
    except Exception as e:
        rows, alert_res, user_data, secours_data = [], None, None, None

    # --- ALERT NOTIFICATION ---
    if alert_res and alert_res['TypeAlerte']:
        type_txt = str(alert_res['TypeAlerte']).upper()
        st.error(f"⚠️ **INCIDENT DÉTECTÉ : {type_txt}**")
        
        # Trigger the WhatsApp notification (sent once per alert)
        enviar_alerta_whatsapp(type_txt, st.session_state["current_session_id"])

    # --- DASHBOARD COMPONENTS ---
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    v_actuelle = f"{round(df.iloc[-1]['MesureVitesse'], 1)} km/h" if not df.empty else "-- km/h"
    v_max = f"{round(df['MesureVitesse'].max(), 1)} km/h" if not df.empty else "-- km/h"
    nb_points = len(df)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Identifiant Session", f"N° {st.session_state['current_session_id']}")
    m2.metric("Vitesse Actuelle", v_actuelle)
    m3.metric("Vitesse Maximale", v_max)
    m4.metric("Paquets LoRa Reçus", f"{nb_points} trames")

    st.markdown("---")

    col_gauche, col_droite = st.columns([1, 1])

    with col_gauche:
        st.subheader("📍 Position GPS en temps réel")
        if not df.empty:
            df['latitude'] = df['latitude'].astype(float)
            df['longitude'] = df['longitude'].astype(float)
            if df['latitude'].max() > 180: df['latitude'] /= 1000000.0
            if df['longitude'].max() > 180: df['longitude'] /= 1000000.0
            
            df_mapa = df[['latitude', 'longitude']].copy()
            layer = pdk.Layer("ScatterplotLayer", df_mapa, get_position="[longitude, latitude]", get_color="[0, 120, 255, 200]", get_radius=12)
            view_state = pdk.ViewState(latitude=df_mapa.iloc[-1]["latitude"], longitude=df_mapa.iloc[-1]["longitude"], zoom=14)
            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state, map_style="mapbox://styles/mapbox/light-v9"))
        else:
            st.warning("Aucun signal GPS enregistré pour le moment.")

    with col_droite:
        st.subheader("📈 Profil de Vitesse (Cinématique)")
        if not df.empty and 'DateHeureMesure' in df.columns:
            # 1. Force numeric conversion (handles Decimal and NULL)
            df['MesureVitesse'] = pd.to_numeric(df['MesureVitesse'], errors='coerce')
            
            # 2. Drop NaN values that would break the chart
            df_chart = df[['DateHeureMesure', 'MesureVitesse']].dropna().set_index('DateHeureMesure')
            
            # 3. Plot
            st.line_chart(df_chart, y='MesureVitesse', color="#29B6F6")

    # --- ROW 3: MEDICAL RECORD AND EMERGENCY CONTACTS ---
    st.markdown("---")
    col_user, col_secours = st.columns(2)
    with col_user:
        st.subheader("📋 Fiche Médicale de l'Utilisateur")
        if user_data:
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Nom / Prénom :** {user_data['Nom']} {user_data['Prenom']}")
                st.markdown(f"**Groupe Sanguin :** `{user_data['TypeSanguin']}`")
            with c2:
                st.markdown(f"**Allergies signalées :** {user_data['Allergies'] if user_data['Allergies'] else 'Aucune'}")
    with col_secours:
        st.subheader("🚨 Protocoles d'Urgence Associés")
        if secours_data and user_data:
            c3, c4 = st.columns(2)
            with c3:
                st.markdown(f"**Zone d'Activité :** {secours_data['Region']} ({secours_data['TypeSport']})")
                st.markdown(f"**Contact Proche :**☎️ `{user_data['ContactUrgence']}`")
            with c4:
                st.markdown(f"**Centre de secours local :**")
                st.error(f"📞 Téléphone : **{secours_data['Contact']}**")

    time.sleep(20)
    st.rerun()