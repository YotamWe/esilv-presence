from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
import os
import datetime
import time
import logging
from zoneinfo import ZoneInfo
from workalendar.europe import France
from logging.handlers import TimedRotatingFileHandler

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

from utilisateur import Utilisateur

load_dotenv()

PARIS_TZ = ZoneInfo("Europe/Paris")

users = [
    {
        "email": os.getenv("EMAIL_1"),
        "password": os.getenv("PASSWORD_1")
    }
]


def now_in_paris():
    return datetime.datetime.now(PARIS_TZ)

def est_jour_ferie():
    """Retourne True si aujourd'hui est un jour férié en France."""
    cal = France()
    now = now_in_paris()
    return cal.is_holiday(now.date())

def dormir_jusqua_minuit():
    now = now_in_paris()
    minuit = datetime.datetime.combine(
        now.date() + datetime.timedelta(days=1),
        datetime.time.min,
        tzinfo=PARIS_TZ,
    )
    attente = max(1, (minuit - now).total_seconds())
    logging.info(f"Aucun cours à vérifier, on attend jusqu'à minuit ({attente:.0f} secondes).")
    return attente


def dormir_jusqua_lundi():
    now = now_in_paris()
    minuit_lundi = datetime.datetime.combine(
        now.date() + datetime.timedelta(days=(7 - now.weekday())),
        datetime.time.min,
        tzinfo=PARIS_TZ,
    )
    attente = (minuit_lundi - now).total_seconds()
    logging.info(f"Week-end détecté, on dort jusqu'à lundi ({attente:.0f} secondes).")
    return attente


def calculer_attente(delais, prochains_debuts):
    if delais:
        return min(delais)
    elif prochains_debuts:
        prochain = min(prochains_debuts)
        now = now_in_paris()
        attente = max(1, (prochain - now).total_seconds())
        prochain_check = now + datetime.timedelta(seconds=attente)
        logging.info(
            f"Prochain check à {prochain_check.strftime('%Y-%m-%d %H:%M:%S')}. "
            f"Il est actuellement {now.strftime('%Y-%m-%d %H:%M:%S')}."
        )
        return attente
    else:
        return dormir_jusqua_minuit()


def traiter_cours(utilisateur, cours, delais, prochains_debuts):
    if cours.deja_notifie:
        logging.info(f"Le cours {cours.identifiant} déjà notifié, on passe.")
        return

    now = now_in_paris()

    # Fenêtre 1 : 15 min avant jusqu'à 15 min après le début
    if cours.heure_debut - datetime.timedelta(minutes=15) <= now <= cours.heure_debut + datetime.timedelta(minutes=15):
        logging.info(f"Cours {cours.identifiant} dans la fenêtre 1.")
        etat = cours.type_appel()
        if etat == "open":
            utilisateur.notifier(f"Le cours {cours.identifiant} - {cours.denomination} est ouvert !")
            cours.deja_notifie = True
        elif etat == "deja_present":
            cours.deja_notifie = True
        elif etat == "closed":
            delais.append(60)

    # Fenêtre 2 : 15 min après le début jusqu'à la fin
    elif cours.heure_debut + datetime.timedelta(minutes=15) < now <= cours.heure_fin:
        logging.info(f"Cours {cours.identifiant} dans la fenêtre 2.")
        etat = cours.type_appel()
        if etat == "open":
            utilisateur.notifier(f"Le cours {cours.identifiant} - {cours.denomination} est ouvert !")
            cours.deja_notifie = True
        elif etat == "deja_present":
            cours.deja_notifie = True
        elif etat == "closed":
            delais.append(120)

    # Hors fenêtre
    else:
        fenetre_debut = cours.heure_debut - datetime.timedelta(minutes=15)
        if fenetre_debut > now:
            prochains_debuts.append(fenetre_debut)


def main():
    last_date = now_in_paris().date()

    with sync_playwright() as p:
        utilisateurs = []
        logging.info("Initialisation des utilisateurs...")
        for user_info in users:
            utilisateur = Utilisateur(user_info["email"])
            utilisateur.se_connecter(p, user_info["password"])
            utilisateur.maj_cours_du_jour()
            utilisateurs.append(utilisateur)
        logging.info(f"{len(utilisateurs)} utilisateur(s) initialisé(s).")

        while True:
            # Week-end : dormir jusqu'à lundi
            now = now_in_paris()
            if now.weekday() >= 5:
                time.sleep(dormir_jusqua_lundi())
                continue
                
            # Jours fériés
            if est_jour_ferie():
                now = now_in_paris()
                minuit = datetime.datetime.combine(
                    now.date() + datetime.timedelta(days=1),
                    datetime.time.min,
                    tzinfo=PARIS_TZ,
                )
                attente = (minuit - now).total_seconds()
                logging.info(f"Jour férié détecté, on dort jusqu'à demain ({attente:.0f} secondes).")
                time.sleep(attente)
                continue

            # Nouvelle journée
            today_date = now_in_paris().date()
            if last_date != today_date:
                logging.info("Nouvelle journée détectée, mise à jour des cours...")
                for utilisateur in utilisateurs:
                    utilisateur.maj_cours_du_jour()
                last_date = today_date

            # Traitement des cours
            delais = []
            prochains_debuts = []
            utilisateur = utilisateurs[0]

            logging.info(f"Vérification des cours pour {utilisateur.email}...")
            for cours in utilisateur.planning:
                traiter_cours(utilisateur, cours, delais, prochains_debuts)

            time.sleep(calculer_attente(delais, prochains_debuts))
                    
if __name__ == "__main__":
    main()