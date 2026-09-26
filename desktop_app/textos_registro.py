# ruff: noqa: E501 — tabla de traducciones: una frase por línea, se lee mejor así.
"""El registro de la aplicación de escritorio, en el idioma que se elija.

Lo que escribe el lector sale en español desde muchos sitios —el propio
lector, la comprobación de arranque (`app/core/preflight.py`), el horario, el
ciclo de correo— y el Monitor de la web lo guarda tal cual. Aquí sólo se
TRADUCE AL PINTAR: el historial conserva el texto original, así que cambiar de
idioma repinta el registro entero sin perder nada, y el Monitor sigue
recibiendo lo mismo de siempre.

Dos formas, como el traductor de la calculadora (`frontend/js/isc-idioma.js`):
frases exactas y plantillas con expresiones regulares para lo que lleva
cifras, nombres o fechas. Lo que no está aquí se enseña como vino: un
mensaje nuevo en español es mejor que uno perdido.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# español → (inglés, francés)
FRASES: Dict[str, Tuple[str, str]] = {
    # --- el lector ---
    "Revisando el esquema de la base…": ("Checking the database schema…", "Vérification du schéma de la base…"),
    "El esquema ya estaba al día.": ("The schema was already up to date.", "Le schéma était déjà à jour."),
    "Comprobando la configuración…": ("Checking the configuration…", "Vérification de la configuration…"),
    "Todo en su sitio. Puedes iniciar el lector.": ("All set. You can start the reader.", "Tout est prêt. Vous pouvez démarrer le lecteur."),
    "Ciclo a mano: se salta el horario.": ("Manual cycle: business hours are skipped.", "Cycle manuel : les horaires sont ignorés."),
    "Ciclo omitido: fuera de horario.": ("Cycle skipped: outside business hours.", "Cycle ignoré : hors horaires."),
    "Deteniendo…": ("Stopping…", "Arrêt…"),
    "Lector detenido.": ("Reader stopped.", "Lecteur arrêté."),
    "AUTO_MIGRAR está apagado: el esquema no se toca desde aquí.": (
        "AUTO_MIGRAR is off: the schema is not touched from here.",
        "AUTO_MIGRAR est désactivé : le schéma n'est pas modifié d'ici."),
    "Outlook confía en Pohua: los correos salen sin preguntar.": (
        "Outlook trusts Pohua: emails go out without asking.",
        "Outlook fait confiance à Pohua : les courriels partent sans demander."),
    "Outlook va a pedir permiso para CADA correo que mande Pohua (el cuadro «A program is trying to send an email…»).": (
        "Outlook will ask permission for EVERY email Pohua sends (the “A program is trying to send an email…” box).",
        "Outlook demandera l'autorisation pour CHAQUE courriel envoyé par Pohua (la fenêtre « A program is trying to send an email… »)."),
    "Se quita en Outlook: Archivo → Opciones → Centro de confianza → Configuración → Acceso mediante programación. «Estado del antivirus» tiene que decir Válido; si no, hay que activar o actualizar el antivirus (o que TI lo configure).": (
        "To remove it in Outlook: File → Options → Trust Center → Settings → Programmatic Access. “Antivirus status” must say Valid; if not, turn on or update the antivirus (or have IT configure it).",
        "Pour le retirer dans Outlook : Fichier → Options → Centre de gestion de la confidentialité → Paramètres → Accès par programmation. « État de l'antivirus » doit indiquer Valide ; sinon, activez ou mettez à jour l'antivirus (ou demandez au service informatique)."),
    "Mientras tanto: si pulsas «Deny», Pohua deja de preguntar 15 min y las ofertas esperan en la bandeja de salida.": (
        "Meanwhile: if you press “Deny”, Pohua stops asking for 15 min and the offers wait in the outbox.",
        "En attendant : si vous cliquez sur « Deny », Pohua cesse de demander pendant 15 min et les offres attendent dans la boîte d'envoi."),
    "Latido rechazado: el secreto no coincide con el del servidor.": (
        "Heartbeat rejected: the secret does not match the server's.",
        "Battement refusé : le secret ne correspond pas à celui du serveur."),
    "Outlook no dejó mandar (se pulsó «Deny»). Las ofertas siguen en la bandeja de salida; no se vuelve a preguntar en 15 min.": (
        "Outlook did not allow sending (“Deny” was pressed). The offers stay in the outbox; it won't ask again for 15 min.",
        "Outlook n'a pas autorisé l'envoi (« Deny »). Les offres restent dans la boîte d'envoi ; pas de nouvelle demande pendant 15 min."),
    # --- comprobación de arranque (app/core/preflight.py) ---
    "No hay DATABASE_URL": ("No DATABASE_URL", "Pas de DATABASE_URL"),
    "Falta JWT_SECRET": ("JWT_SECRET is missing", "JWT_SECRET manquant"),
    "Falta ANTHROPIC_API_KEY": ("ANTHROPIC_API_KEY is missing", "ANTHROPIC_API_KEY manquant"),
    "No se pudo consultar el esquema": ("Could not query the schema", "Impossible d'interroger le schéma"),
    "No se pudo conectar a la base": ("Could not connect to the database", "Impossible de se connecter à la base"),
    "WORKER_SECRET_KEY sin poner: el latido no saldrá": ("WORKER_SECRET_KEY not set: no heartbeat will be sent", "WORKER_SECRET_KEY non défini : aucun battement ne sera envoyé"),
    "Desde la consola no se sabe si la aplicación de escritorio está leyendo": ("From the console it is unknown whether the desktop app is reading", "Depuis la console, on ignore si l'application de bureau lit"),
    "Nadie lee el buzón solo": ("Nobody reads the mailbox automatically", "Personne ne lit la boîte automatiquement"),
    "WORKER_SECRET_KEY sin poner: el latido está apagado": ("WORKER_SECRET_KEY not set: the heartbeat is off", "WORKER_SECRET_KEY non défini : le battement est désactivé"),
    "Se leerá la BANDEJA DE ENTRADA, no una carpeta de pruebas": ("The INBOX will be read, not a test folder", "La BOÎTE DE RÉCEPTION sera lue, pas un dossier de test"),
    "El servidor no tiene credenciales del buzón": ("The server has no mailbox credentials", "Le serveur n'a pas d'identifiants de boîte"),
    "No se pudo abrir el buzón": ("Could not open the mailbox", "Impossible d'ouvrir la boîte"),
    "No se pudo leer el horario": ("Could not read the business hours", "Impossible de lire les horaires"),
    "Horario apagado: se lee a cualquier hora": ("Business hours off: reading at any time", "Horaires désactivés : lecture à toute heure"),
    "Cerrado ahora: el ciclo automático no abrirá el buzón": ("Closed now: the automatic cycle won't open the mailbox", "Fermé maintenant : le cycle automatique n'ouvrira pas la boîte"),
    "No se pudo leer el estado del envío": ("Could not read the sending status", "Impossible de lire l'état de l'envoi"),
    "ENVIO_AUTOMATICO encendido: el sistema escribe solo": ("ENVIO_AUTOMATICO on: the system writes on its own", "ENVIO_AUTOMATICO activé : le système écrit seul"),
    "ENVIO_MANUAL apagado: ni la oferta ni la declinación saldrán": ("ENVIO_MANUAL off: neither the offer nor the decline will go out", "ENVIO_MANUAL désactivé : ni l'offre ni le refus ne partiront"),
    "No se pudo cargar el módulo de avisos": ("Could not load the notifications module", "Impossible de charger le module d'alertes"),
    "Faltan las claves VAPID": ("The VAPID keys are missing", "Les clés VAPID manquent"),
    "No se pudo contar los dispositivos suscritos": ("Could not count the subscribed devices", "Impossible de compter les appareils abonnés"),
    "Ningún dispositivo suscrito": ("No subscribed devices", "Aucun appareil abonné"),
    "Apagado (RECORDATORIO_HORAS=0)": ("Off (RECORDATORIO_HORAS=0)", "Désactivé (RECORDATORIO_HORAS=0)"),
    "Falta APP_URL": ("APP_URL is missing", "APP_URL manquant"),
    "No se pudo leer quién dictamina": ("Could not read who decides", "Impossible de lire qui décide"),
    "Nadie con permiso 'rfq:dictaminar' y correo": ("Nobody with the 'rfq:dictaminar' permission and an email", "Personne avec la permission 'rfq:dictaminar' et un courriel"),
    "No está vendor/lector": ("vendor/lector is missing", "vendor/lector est absent"),
    "No están las calculadoras vendorizadas": ("The vendored calculators are missing", "Les calculatrices vendorisées sont absentes"),
    "No se pudo leer el catálogo de costeo": ("Could not read the costing catalog", "Impossible de lire le catalogue de coûts"),
    "El catálogo validado del taller NO está cargado en la base": ("The shop's validated catalog is NOT loaded in the database", "Le catalogue validé de l'atelier n'est PAS chargé dans la base"),
    "Los parámetros vigentes en la base no son los del motor": ("The current parameters in the database are not the engine's", "Les paramètres en vigueur dans la base ne sont pas ceux du moteur"),
    "No está frontend/legal/responsable.js": ("frontend/legal/responsable.js is missing", "frontend/legal/responsable.js est absent"),
    "Faltan datos del responsable en el aviso de privacidad": ("The privacy notice is missing the data controller's details", "Les coordonnées du responsable manquent dans l'avis de confidentialité"),
    "La versión de los documentos legales no coincide": ("The legal documents version does not match", "La version des documents juridiques ne correspond pas"),
    "Una comprobación falló": ("A check failed", "Une vérification a échoué"),
    # --- el detalle bajo lo que falta ---
    "Sin base no hay RFQ que registrar.": ("Without a database there is nowhere to record RFQs.", "Sans base, aucun RFQ ne peut être enregistré."),
    "Sin ella no se puede entrar a Pohua.": ("Without it nobody can sign in to Pohua.", "Sans elle, impossible de se connecter à Pohua."),
    "El correo se registraría, pero sin extracción: el RFQ acabaría en Incomplete.": ("The email would be recorded, but without extraction: the RFQ would end up Incomplete.", "Le courriel serait enregistré, mais sans extraction : le RFQ finirait Incomplete."),
    "python scripts/generar_vapid.py, y las dos líneas a Render. Sin ellas la campana funciona dentro de Pohua, pero no llega nada al teléfono.": ("python scripts/generar_vapid.py, and the two lines to Render. Without them the bell works inside Pohua, but nothing reaches the phone.", "python scripts/generar_vapid.py, et les deux lignes dans Render. Sans elles, la cloche fonctionne dans Pohua, mais rien n'arrive au téléphone."),
    "Sin ella el enlace iría a localhost y el correo no se manda. APP_URL=https://tu-servicio.onrender.com": ("Without it the link would point to localhost and the email is not sent. APP_URL=https://your-service.onrender.com", "Sans elle, le lien pointerait vers localhost et le courriel ne part pas. APP_URL=https://votre-service.onrender.com"),
    "El precio del flujo no va a coincidir con la calculadora. Se carga una vez, desde la carpeta del proyecto: python scripts/cargar_catalogo.py --carpeta _extracto_catalogo": ("The flow's price won't match the calculator. Load it once, from the project folder: python scripts/cargar_catalogo.py --carpeta _extracto_catalogo", "Le prix du flux ne correspondra pas à la calculatrice. Chargez-le une fois depuis le dossier du projet : python scripts/cargar_catalogo.py --carpeta _extracto_catalogo"),
    "O las pones en el servidor (con Microsoft 365, Graph: AZURE_* y GRAPH_USER), o dejas leyendo la aplicación de escritorio, que las tiene en tu computadora.": ("Either set them on the server (with Microsoft 365, Graph: AZURE_* and GRAPH_USER), or leave the desktop app reading, which has them on your computer.", "Soit vous les mettez sur le serveur (avec Microsoft 365, Graph : AZURE_* et GRAPH_USER), soit vous laissez lire l'application de bureau, qui les a sur votre ordinateur."),
    "Revisa las credenciales y que el servidor tenga salida.": ("Check the credentials and that the server has outbound access.", "Vérifiez les identifiants et que le serveur a un accès sortant."),
    # --- el pie de la ventana (latido) ---
    "Sin latido: falta APP_URL o WORKER_SECRET_KEY. El servidor podría leer el mismo buzón.": ("No heartbeat: APP_URL or WORKER_SECRET_KEY is missing. The server could read the same mailbox.", "Pas de battement : APP_URL ou WORKER_SECRET_KEY manquant. Le serveur pourrait lire la même boîte."),
    "El servidor rechazó el latido: WORKER_SECRET_KEY no coincide.": ("The server rejected the heartbeat: WORKER_SECRET_KEY does not match.", "Le serveur a refusé le battement : WORKER_SECRET_KEY ne correspond pas."),
}

# (regex en español, plantilla en inglés, plantilla en francés). Se prueban en
# orden y gana la primera; los grupos se reusan con \1, \2…
PLANTILLAS: List[Tuple[str, str, str]] = [
    (r"^Lector en marcha\. Un ciclo cada (\d+) min\.$",
     r"Reader running. One cycle every \1 min.", r"Lecteur en marche. Un cycle toutes les \1 min."),
    (r"^Ciclo: (\d+) sin leer · (\d+) procesados · (\d+) RFQ · (\d+) con error\.$",
     r"Cycle: \1 unread · \2 processed · \3 RFQ · \4 with errors.",
     r"Cycle : \1 non lus · \2 traités · \3 RFQ · \4 en erreur."),
    (r"^Fuera del horario de atención \((.+?) (.+?), lunes a viernes\)\. Los correos esperan a (.+)\.$",
     r"Outside business hours (\1 \2, Monday to Friday). Emails wait until \3.",
     r"Hors horaires (\1 \2, du lundi au vendredi). Les courriels attendent jusqu'au \3."),
    (r"^Recordatorio de dictamen enviado por (\d+) caso\(s\) \((\d+) correo/s\)\.$",
     r"Decision reminder sent for \1 case(s) (\2 email(s)).",
     r"Rappel de décision envoyé pour \1 cas (\2 courriel(s))."),
    (r"^Faltan (\d+) cosa\(s\); el lector puede arrancar igual, pero fallará ahí\.$",
     r"\1 thing(s) missing; the reader can start anyway, but it will fail there.",
     r"\1 élément(s) manquant(s) ; le lecteur peut démarrer, mais il échouera là."),
    (r"^Falta: (.+)$", r"Missing: \1", r"Manquant : \1"),
    (r"^Migraciones: (.+)$", r"Migrations: \1", r"Migrations : \1"),
    (r"^Esquema actualizado: (.+)$", r"Schema updated: \1", r"Schéma mis à jour : \1"),
    (r"^No se pudo comprobar: (.+)$", r"Could not check: \1", r"Vérification impossible : \1"),
    (r"^No se pudo revisar el esquema: (.+)$", r"Could not check the schema: \1", r"Impossible de vérifier le schéma : \1"),
    (r"^El ciclo falló: (.+)$", r"The cycle failed: \1", r"Le cycle a échoué : \1"),
    (r"^La bandeja de salida falló: (.+)$", r"The outbox failed: \1", r"La boîte d'envoi a échoué : \1"),
    (r"^No se pudo mirar la bandeja de salida: (.+)$", r"Could not check the outbox: \1", r"Impossible de vérifier la boîte d'envoi : \1"),
    (r"^Bandeja de salida: (\d+) correo/s enviado/s por Outlook\.$",
     r"Outbox: \1 email(s) sent through Outlook.", r"Boîte d'envoi : \1 courriel(s) envoyé(s) par Outlook."),
    (r"^Bandeja de salida: (\d+) no salieron; se reintentan el próximo ciclo\.$",
     r"Outbox: \1 did not go out; retried next cycle.", r"Boîte d'envoi : \1 non envoyé(s) ; nouvel essai au prochain cycle."),
    (r"^Quedan (\d+) esperando\.$", r"\1 still waiting.", r"\1 en attente."),
    (r"^Hay (\d+) oferta/s esperando, pero esta computadora no está configurada para mandar\. Falta MAIL_MODE=outlook y OUTLOOK_BUZON en el \.env\.$",
     r"\1 offer(s) waiting, but this computer is not set up to send. MAIL_MODE=outlook and OUTLOOK_BUZON are missing in .env.",
     r"\1 offre(s) en attente, mais cet ordinateur n'est pas configuré pour envoyer. MAIL_MODE=outlook et OUTLOOK_BUZON manquent dans .env."),
    # --- lo que cuenta el ciclo (app/main.py) ---
    (r"^Latido enviado a (.+) · (.+)$", r"Heartbeat sent to \1 · \2", r"Battement envoyé à \1 · \2"),
    (r"^El servidor contestó (\d+) al latido\.$", r"The server answered \1 to the heartbeat.", r"Le serveur a répondu \1 au battement."),
    (r"^No se pudo mandar el latido: (.+)$", r"Could not send the heartbeat: \1", r"Impossible d'envoyer le battement : \1"),
    (r"^Duplicado omitido: (.+)$", r"Duplicate skipped: \1", r"Doublon ignoré : \1"),
    (r"^Reintento: (.+)$", r"Retry: \1", r"Nouvel essai : \1"),
    (r"^Del propio buzón, omitido: (.+)$", r"From our own mailbox, skipped: \1", r"De notre propre boîte, ignoré : \1"),
    (r"^Cuarentena \((.+?)\): (.+)$", r"Quarantine (\1): \2", r"Quarantaine (\1) : \2"),
    (r"^Error: (.+)$", r"Error: \1", r"Erreur : \1"),
    (r"^Modo prueba: se permiten correos repetidos\.$",
     r"Test mode: repeated emails are allowed.", r"Mode test : courriels répétés autorisés."),
    (r"^(\d+) migración\(es\) sin aplicar$", r"\1 migration(s) not applied", r"\1 migration(s) non appliquée(s)"),
    (r"^No hay correos sin leer en '(.+)'$", r"No unread emails in '\1'", r"Aucun courriel non lu dans « \1 »"),
    (r"^Faltan credenciales del buzón: (.+)$", r"Mailbox credentials missing: \1", r"Identifiants de boîte manquants : \1"),
    (r"^El servidor no puede mandar correo: falta (.+)$", r"The server cannot send email: missing \1", r"Le serveur ne peut pas envoyer : \1 manquant"),
]

_COMPILADAS = [(re.compile(p), en, fr) for p, en, fr in PLANTILLAS]
_IDX = {"en": 0, "fr": 1}


def traducir(texto: str, idioma: str) -> str:
    """El texto del registro en ``idioma`` ('es', 'en', 'fr'). Nunca lanza."""
    if not texto or idioma not in _IDX:
        return texto
    idx = _IDX[idioma]
    sangria = texto[:len(texto) - len(texto.lstrip())]
    cuerpo = texto.strip()
    if cuerpo in FRASES:
        return sangria + FRASES[cuerpo][idx]
    for patron, en, fr in _COMPILADAS:
        m = patron.match(cuerpo)
        if m:
            fuera = m.expand(en if idx == 0 else fr)
            # Lo que la plantilla deja dentro puede ser a su vez un mensaje
            # conocido («Falta: <título del preflight>», que también puede
            # llevar cifras): se traduce igual, un nivel más abajo.
            for grupo in m.groups():
                if grupo:
                    dentro = traducir(grupo.strip(), idioma)
                    if dentro != grupo.strip():
                        fuera = fuera.replace(grupo, dentro)
            return sangria + fuera
    return texto
