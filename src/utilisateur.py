import os

from dotenv import load_dotenv
import time
import random
from datetime import datetime
import logging
from zoneinfo import ZoneInfo
from logging.handlers import TimedRotatingFileHandler

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        TimedRotatingFileHandler(
            "logs/presence.log",
            when="midnight",
            interval=1,
            backupCount=7,
            encoding="utf-8"
        ),
        logging.StreamHandler()
    ]
)

import requests
from cours import Cours

PARIS_TZ = ZoneInfo("Europe/Paris")

def human_delay(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))

class Utilisateur:
    def __init__(self, email):
        self.email = email
        self.planning = [] #on commence avec un planning vide
        self.browser_context = None
        self.page = None
        self.derniere_maj = None
        self.mot_de_passe = None
        self.playwright_instance = None 

    def maj_cours_du_jour(self): #Récupère les cours du jour et les ajoute au planning
        if not self.page:
            logging.error("Erreur : L'utilisateur doit être connecté pour récupérer les cours.")
            return
        
        logging.info(f"Suppression des cours de {self.email}...")

        self.planning.clear() #on vide le planning

        logging.info(f"Récupération des cours pour {self.email}...")

        self.verifier_session()

        # Vérification de la présence de cours ajd
        self.page.wait_for_selector("body")
        contenu = self.page.inner_text("body").lower()
        if "Pas de cours de prévu" in contenu:
            logging.info(f"Aucun cours prévu aujourd'hui pour {self.email}.")
            self.derniere_maj = datetime.now(PARIS_TZ)
            return

        #sinon
        try:
            self.page.wait_for_selector("#body_presences", timeout=15000)
        except:
            logging.info(f"Pas de cours aujourd'hui pour {self.email}, on attend demain.")
            self.planning = []
            return
        rows = self.page.query_selector_all("#body_presences tr")
        for row in rows:
            cols = row.query_selector_all("td")

            if len(cols) == 0: #si la ligne ne contient pas de cours, on ignore
                continue

            # On suppose que les colonnes sont : [0] Horaires du cours, [1] Nom du cours, [2] Intervenant, [3] Présence
            horaires = cols[0].inner_text().strip()
            horaires2 = " ".join(horaires.split()) #pour enlever les espaces en trop
            heure_debut, heure_fin = horaires2.split("-")
            heure_debut = heure_debut.strip()
            heure_fin = heure_fin.strip()
            today = datetime.now(PARIS_TZ).date()
            heure_debut_dt = datetime.combine(today, datetime.strptime(heure_debut, "%H:%M").time(), tzinfo=PARIS_TZ)
            heure_fin_dt = datetime.combine(today, datetime.strptime(heure_fin, "%H:%M").time(), tzinfo=PARIS_TZ)

            nom_cours = cols[1].inner_text().strip()

            intervenant = cols[2].inner_text().strip()

            presence_link = None
            presence = cols[3].query_selector("a")
            if presence:
                presence_link = presence.get_attribute("href")
            logging.info(f"{nom_cours} ({horaires}) par {intervenant}) lu pour {self.email}")

            self.planning.append(Cours(
                identifiant=presence_link.split("/")[-1] if presence_link else None,
                utilisateur=self,
                denomination=nom_cours,
                heure_debut=heure_debut_dt,
                heure_fin=heure_fin_dt
            ))
        
        self.derniere_maj = datetime.now(PARIS_TZ)

    
    def se_connecter(self, playwright_instance, mot_de_passe):
        self.mot_de_passe = mot_de_passe
        self.playwright_instance = playwright_instance
        logging.info(f"Connexion de {self.email}...")
        browser = playwright_instance.chromium.launch(headless=False)
        self.browser_context = browser.new_context()
        self.page = self.browser_context.new_page()

        self.page.goto("https://my.devinci.fr/")

        self.page.type("##email", self.email, delay=random.randint(50, 150))
        human_delay()
        self.page.click('button.btn-primary')

        self.page.wait_for_url("**adfs.devinci.fr**")

        self.page.type("#passwordInput", mot_de_passe, delay=random.randint(70, 180))
        human_delay()
        self.page.click("#submitButton")

        self.page.wait_for_url("https://my.devinci.fr/**")

        logging.info(f"{self.email} connecté avec succès !")
    
    def _reconnecter(self):
        """Tente de se reconnecter, retourne True si succès, False sinon."""
        try:
            self.se_connecter(self.playwright_instance, self.mot_de_passe)
            logging.info(f"Reconnexion réussie pour {self.email}.")
            return True
        except Exception as e:
            logging.error(f"Échec de la reconnexion pour {self.email} : {e}")
            return False
    
    def verifier_session(self):
        """Vérifie si la session est toujours active, sinon se reconnecte."""
        try:
            self.page.goto("https://my.devinci.fr/student/presences/", timeout=10000)
            # Si on est redirigé vers la page de login, on est déconnecté
            if "adfs.devinci.fr" in self.page.url or "login" in self.page.url:
                logging.warning(f"Session expirée pour {self.email}, reconnexion...")
                return self._reconnecter()
            return True
        except Exception as e:
            logging.error(f"Erreur lors de la vérification de session pour {self.email} : {e}")
            logging.info(f"Tentative de reconnexion pour {self.email}...")
            return self._reconnecter()

    def notifier(self, message):
        ntfy_sujet = os.getenv("SUJET")
        url = f"https://ntfy.sh/{ntfy_sujet}"
        requests.post(url, data=message)
        logging.info(f"Notification pour {self.email}: {message}")