/**
 * Idiomas: inglés, español y francés.
 *
 * Cómo funciona, en dos piezas:
 *
 *   1. El HTML estático marca sus textos con data-i18n="clave". `aplicar()`
 *      recorre esas marcas y les pone el texto del idioma actual.
 *   2. Lo que se genera desde JavaScript llama a `I18N.t('clave')`.
 *
 * Las plantillas se vuelven a pintar al cambiar de idioma (`alCambiar`), así
 * que no hace falta recargar la página.
 *
 * Decisiones que conviene no deshacer sin pensarlo:
 *
 *   - Una clave que falta devuelve la clave misma, no una cadena vacía. Un
 *     hueco en blanco pasa desapercibido en pruebas; un "perfil.foto" en medio
 *     de la pantalla, no.
 *   - El inglés es la red de seguridad: si una clave existe en inglés pero
 *     todavía no en francés, sale en inglés en vez de desaparecer.
 *   - Los datos NO se traducen: nombres de clientes, materiales y mensajes
 *     del registro se enseñan tal cual. Los ESTADOS del RFQ sí (2026-09-26,
 *     a petición de ventas: «que el idioma esté bien en todo el entorno»):
 *     `I18N.estado('RequiresReview')` → «En revisión». La base los sigue
 *     guardando en inglés; sólo cambia lo que se pinta.
 */
const I18N = (() => {
    'use strict';

    const CLAVE = 'cgr-idioma';
    const POR_DEFECTO = 'en';

    const IDIOMAS = [
        { codigo: 'en', etiqueta: 'English',  corto: 'EN' },
        { codigo: 'es', etiqueta: 'Español',  corto: 'ES' },
        { codigo: 'fr', etiqueta: 'Français', corto: 'FR' },
    ];

    const TEXTOS = {
        // --- Navegación y estructura ------------------------------------
        'nav.main':      { en: 'Main',     es: 'Principal',  fr: 'Principal' },
        'nav.mail':      { en: 'Mail',     es: 'Correo',     fr: 'Courrier' },
        'nav.quoting':   { en: 'Quoting',  es: 'Cotización', fr: 'Chiffrage' },
        'nav.resumen':   { en: 'Overview', es: 'Resumen',    fr: 'Aperçu' },
        'nav.monitor':   { en: 'Monitor',  es: 'Monitor',    fr: 'Moniteur' },
        'nav.profile':   { en: 'Profile',  es: 'Perfil',     fr: 'Profil' },
        'nav.signout':   { en: 'Sign out', es: 'Cerrar sesión', fr: 'Se déconnecter' },
        'nav.menu':      { en: 'Menu',     es: 'Menú',       fr: 'Menu' },

        'pagina.mail.titulo':        { en: 'Mail', es: 'Correo', fr: 'Courrier' },
        'pagina.mail.sub':           { en: 'Inbox', es: 'Bandeja de entrada', fr: 'Boîte de réception' },
        'pagina.quoting.titulo':     { en: 'Quoting', es: 'Cotización', fr: 'Chiffrage' },
        'pagina.quoting.sub':        { en: 'Quote list and calculators', es: 'Lista de cotizaciones y calculadoras', fr: 'Liste des devis et calculatrices' },
        'pagina.rfqDetalle.titulo':  { en: 'RFQ Detail', es: 'Detalle de RFQ', fr: 'Détail de la RFQ' },
        'pagina.rfqDetalle.sub':     { en: 'Extracted data and feasibility', es: 'Datos extraídos y factibilidad', fr: 'Données extraites et faisabilité' },
        'pagina.cotizacion.titulo':  { en: 'Quote', es: 'Cotización', fr: 'Devis' },
        'pagina.cotizacion.sub':     { en: 'Review and send the proposal', es: 'Revisa y envía la propuesta', fr: 'Vérifier et envoyer la proposition' },
        'pagina.resumen.titulo':     { en: 'Overview', es: 'Resumen', fr: 'Aperçu' },
        'pagina.resumen.sub':        { en: 'How everything is going right now', es: 'Cómo va todo ahora mismo', fr: "Où en est tout, maintenant" },
        'pagina.monitor.titulo':     { en: 'Monitor', es: 'Monitor', fr: 'Moniteur' },
        'pagina.monitor.sub':        { en: 'System event log', es: 'Registro de eventos del sistema', fr: 'Journal des événements' },
        'pagina.perfil.titulo':      { en: 'Profile', es: 'Perfil', fr: 'Profil' },
        'pagina.perfil.sub':         { en: 'Your account', es: 'Tu cuenta', fr: 'Votre compte' },
        'pagina.perfil.subAdmin':    { en: 'Your account, users and system settings', es: 'Tu cuenta, usuarios y configuración del sistema', fr: 'Votre compte, les utilisateurs et la configuration' },

        // --- Portada y acceso -------------------------------------------
        // --- Información legal (js/components/legal.js, /legal/) -----------
        'legal.privacidad': { en: 'Privacy notice', es: 'Aviso de privacidad', fr: 'Politique de confidentialité' },
        'legal.cookies':    { en: 'Cookies', es: 'Cookies', fr: 'Cookies' },
        'legal.terminos':   { en: 'Terms of use', es: 'Términos de uso', fr: "Conditions d’utilisation" },
        'legal.banner':     { en: 'Pohua only uses one technical cookie and local storage that it needs to work and to remember your preferences. No advertising, analytics or third-party cookies.',
                              es: 'Pohua sólo usa una cookie técnica y almacenamiento local necesarios para funcionar y para recordar sus preferencias. No usamos cookies de publicidad, de analítica ni de terceros.',
                              fr: 'Pohua utilise uniquement un cookie technique et un stockage local nécessaires à son fonctionnement et à la mémorisation de vos préférences. Aucun cookie publicitaire, de mesure d’audience ou tiers.' },
        'legal.entendido':  { en: 'Got it', es: 'Entendido', fr: 'J’ai compris' },
        'legal.masCookies': { en: 'Cookie policy', es: 'Política de cookies', fr: 'Politique cookies' },
        'legal.aceptTitulo':{ en: 'Privacy notice and terms of use', es: 'Aviso de privacidad y términos de uso', fr: 'Politique de confidentialité et conditions d’utilisation' },
        'legal.aceptTexto': { en: 'Before you continue, please read the Pohua privacy notice and terms of use. Your acceptance is recorded with the date and version.',
                              es: 'Antes de continuar, lea el aviso de privacidad y los términos de uso de Pohua. Su aceptación queda registrada con la fecha y la versión.',
                              fr: 'Avant de continuer, lisez la politique de confidentialité et les conditions d’utilisation de Pohua. Votre acceptation est enregistrée avec la date et la version.' },
        'legal.aceptCambio':{ en: 'The documents have changed since you last accepted them.', es: 'Los documentos cambiaron desde su última aceptación.', fr: 'Les documents ont changé depuis votre dernière acceptation.' },
        'legal.aceptCasilla':{ en: 'I have read the privacy notice and I accept the terms of use.', es: 'He leído el aviso de privacidad y acepto los términos de uso.', fr: 'J’ai lu la politique de confidentialité et j’accepte les conditions d’utilisation.' },
        'legal.aceptar':    { en: 'Accept and continue', es: 'Aceptar y continuar', fr: 'Accepter et continuer' },
        'legal.salir':      { en: 'Log out', es: 'Salir', fr: 'Se déconnecter' },
        'legal.fallo':      { en: 'Could not record your acceptance: {motivo}', es: 'No se pudo registrar la aceptación: {motivo}', fr: 'Impossible d’enregistrer votre acceptation : {motivo}' },
        'legal.login':      { en: 'By signing in you accept the {terminos}. See the {privacidad} and the {cookies}.',
                              es: 'Al entrar acepta los {terminos}. Consulte el {privacidad} y la {cookies}.',
                              fr: 'En vous connectant, vous acceptez les {terminos}. Consultez la {privacidad} et la {cookies}.' },
        'legal.loginCookies':{ en: 'cookie policy', es: 'política de cookies', fr: 'politique cookies' },

        'home.subtitulo': { en: 'Automatic quoting for industrial springs', es: 'Cotización automática de resortes industriales', fr: 'Chiffrage automatique de ressorts industriels' },
        'home.entrar':    { en: 'Sign In', es: 'Entrar', fr: 'Se connecter' },
        'home.continuar': { en: 'Continue', es: 'Continuar', fr: 'Continuer' },
        'nav.portada':    { en: 'Home screen', es: 'Pantalla de inicio', fr: 'Écran d’accueil' },

        'login.titulo':   { en: 'Sign In', es: 'Entrar', fr: 'Connexion' },
        'login.ayuda':    { en: 'Enter your credentials to access the quoter.', es: 'Escribe tus credenciales para entrar al cotizador.', fr: 'Saisissez vos identifiants pour accéder au chiffrage.' },
        'login.correo':   { en: 'Email', es: 'Correo', fr: 'E-mail' },
        'login.password': { en: 'Password', es: 'Contraseña', fr: 'Mot de passe' },
        'login.marcadorCorreo':   { en: 'name@company.com', es: 'nombre@empresa.com', fr: 'nom@entreprise.com' },
        'login.marcadorPassword': { en: 'Your password', es: 'Tu contraseña', fr: 'Votre mot de passe' },
        'login.volver':   { en: 'Back to home', es: 'Volver a la portada', fr: "Retour à l'accueil" },
        'login.entrar':   { en: 'Sign In', es: 'Entrar', fr: 'Se connecter' },
        'login.entrando': { en: 'Signing in...', es: 'Entrando...', fr: 'Connexion...' },
        'login.faltan':   { en: 'Enter your email and password.', es: 'Escribe tu correo y tu contraseña.', fr: 'Saisissez votre e-mail et votre mot de passe.' },
        'login.malas':    { en: 'Incorrect email or password.', es: 'Correo o contraseña incorrectos.', fr: 'E-mail ou mot de passe incorrect.' },
        'login.sinServicio': { en: 'The service is unavailable right now. Please try again later.', es: 'El servicio no está disponible ahora mismo. Inténtalo más tarde.', fr: "Le service est indisponible pour le moment. Réessayez plus tard." },
        'login.sinRed':   { en: 'Cannot reach the server. Check your connection and try again.', es: 'No se puede contactar con el servidor. Revisa tu conexión e inténtalo de nuevo.', fr: 'Impossible de joindre le serveur. Vérifiez votre connexion et réessayez.' },
        'login.fallo':    { en: 'Could not sign in. Please try again.', es: 'No se pudo entrar. Inténtalo de nuevo.', fr: 'Connexion impossible. Réessayez.' },

        // --- Mail: tarjetas y recorrido ---------------------------------
        'tarjeta.estado':     { en: 'Service Status', es: 'Estado del servicio', fr: 'État du service' },
        'tarjeta.correos':    { en: 'Emails Processed', es: 'Correos procesados', fr: 'Courriels traités' },
        'tarjeta.rfqs':       { en: 'Total RFQs', es: 'RFQs totales', fr: 'RFQ au total' },
        'tarjeta.errores':    { en: 'Errors', es: 'Errores', fr: 'Erreurs' },
        'estado.corriendo':   { en: 'Running', es: 'En marcha', fr: 'En marche' },
        'estado.parado':      { en: 'Stopped', es: 'Detenido', fr: 'Arrêté' },

        'flujo.titulo':       { en: "From the customer's email to Sales", es: 'Del correo del cliente hasta Sales', fr: "Du courriel du client jusqu'à Sales" },
        'flujo.corriendo':    { en: 'Running', es: 'En marcha', fr: 'En marche' },
        'flujo.ultimoCiclo':  { en: 'Running · last cycle {hora}', es: 'En marcha · último ciclo {hora}', fr: 'En marche · dernier cycle {hora}' },
        'flujo.parado':       { en: 'Service stopped — nothing is moving right now', es: 'Servicio detenido: ahora mismo no se mueve nada', fr: 'Service arrêté — rien ne circule en ce moment' },
        'flujo.error':        { en: 'Could not load the flow: {motivo}', es: 'No se pudo cargar el recorrido: {motivo}', fr: 'Impossible de charger le parcours : {motivo}' },
        'flujo.alt':          { en: 'Path of an email from the customer to Sales', es: 'Recorrido de un correo desde el cliente hasta Sales', fr: "Parcours d'un courriel du client jusqu'à Sales" },

        'etapa.cliente':      { en: 'Customer email', es: 'Correo del cliente', fr: 'Courriel du client' },
        'etapa.cliente.det':  { en: '{n} in the last 7 days', es: '{n} en los últimos 7 días', fr: '{n} ces 7 derniers jours' },
        'etapa.extraccion':   { en: 'Data extracted', es: 'Datos extraídos', fr: 'Données extraites' },
        'etapa.extraccion.det': { en: 'RFQs registered from those emails', es: 'RFQs registradas a partir de esos correos', fr: 'RFQ enregistrées à partir de ces courriels' },
        'etapa.revision':     { en: 'Needs review', es: 'Necesita revisión', fr: 'À vérifier' },
        'etapa.revision.det': { en: 'Low-confidence extraction: a person checks it', es: 'Extracción con poca confianza: la revisa una persona', fr: 'Extraction peu fiable : une personne vérifie' },
        'etapa.dictamen':     { en: 'Awaiting decision', es: 'Esperando dictamen', fr: 'En attente de décision' },
        'etapa.dictamen.det': { en: 'Waiting for approve or decline', es: 'Esperando aprobación o rechazo', fr: "En attente d'approbation ou de refus" },
        'etapa.sales':        { en: 'Ready for Sales', es: 'Listo para Sales', fr: 'Prêt pour Sales' },
        'etapa.sales.det':    { en: '{n} declined', es: '{n} rechazadas', fr: '{n} refusées' },
        'etapa.incompletas':  { en: 'Waiting on customer', es: 'Esperando al cliente', fr: 'En attente du client' },
        'etapa.incompletas.det': { en: 'Missing data: we asked the buyer', es: 'Faltan datos: se le pidieron al comprador', fr: 'Données manquantes : demandées à l’acheteur' },
        'etapa.oferta':       { en: 'Quote sent', es: 'Oferta enviada', fr: 'Devis envoyé' },
        'etapa.oferta.det':   { en: 'Offer PDF emailed to the customer', es: 'PDF de la oferta enviado al cliente', fr: 'PDF de l’offre envoyé au client' },

        'boton.correrCiclo':  { en: 'Run Cycle', es: 'Ejecutar ciclo', fr: 'Lancer un cycle' },
        'boton.correrCiclo.ayuda': { en: 'Run one detection cycle', es: 'Ejecuta un ciclo de detección', fr: 'Lancer un cycle de détection' },
        'boton.arrancar':     { en: 'Start Service', es: 'Arrancar servicio', fr: 'Démarrer le service' },
        'boton.detener':      { en: 'Stop Service', es: 'Detener servicio', fr: 'Arrêter le service' },

        'barra.servicioParado':    { en: 'Service stopped', es: 'Servicio detenido', fr: 'Service arrêté' },
        'barra.servicioCorriendo': { en: 'Service running (every {n}m)', es: 'Servicio en marcha (cada {n} min)', fr: 'Service actif (toutes les {n} min)' },
        'barra.enEspera':          { en: 'Waiting — opens {cuando}', es: 'En espera — abre {cuando}', fr: 'En attente — ouvre {cuando}' },

        // --- Horario de atención ------------------------------------------
        // La ventana es la de la planta; las horas se escriben en la casa del
        // reloj de arriba, que es la del idioma mientras nadie lo toque.
        'horario.ventana':   { en: 'Answering hours: {franja}, {dias} ({ciudad} time)',
                               es: 'Horario de atención: {franja}, {dias} (hora de {ciudad})',
                               fr: 'Heures de traitement : {franja}, {dias} (heure de {ciudad})' },
        'horario.lunVie':    { en: 'Mon–Fri', es: 'de lunes a viernes', fr: 'du lundi au vendredi' },
        'horario.enHorario': { en: 'Running', es: 'En marcha', fr: 'En marche' },
        'horario.enEspera':  { en: 'Waiting', es: 'En espera', fr: 'En attente' },
        'horario.hasta':     { en: 'Answering until {cuando}', es: 'Contestando hasta {cuando}', fr: "Traitement jusqu'à {cuando}" },
        'horario.abre':      { en: 'Opens {cuando}', es: 'Abre {cuando}', fr: 'Ouvre {cuando}' },
        'horario.fuera':     { en: 'Outside answering hours', es: 'Fuera del horario de atención', fr: 'Hors des heures de traitement' },
        'horario.esperan':   { en: 'Emails wait unread in the inbox until it opens.',
                               es: 'Los correos esperan sin leer en el buzón hasta la apertura.',
                               fr: "Les courriels attendent non lus dans la boîte jusqu'à l'ouverture." },

        // --- Monitor -----------------------------------------------------
        'monitor.titulo':    { en: 'Service log', es: 'Registro del servicio', fr: 'Journal du service' },
        'monitor.lineas':    { en: '{n} lines', es: '{n} líneas', fr: '{n} lignes' },
        'monitor.refrescar': { en: 'Refresh now', es: 'Actualizar ahora', fr: 'Actualiser' },
        'monitor.cargando':  { en: 'Loading the log…', es: 'Cargando el registro…', fr: 'Chargement du journal…' },
        'monitor.vacio':     { en: 'The log is empty.', es: 'El registro está vacío.', fr: 'Le journal est vide.' },
        'monitor.sinFichero': { en: 'No log file yet.', es: 'Todavía no hay fichero de registro.', fr: 'Pas encore de fichier journal.' },
        // El lector local: sólo cuando Pohua corre dentro de la aplicación de
        // escritorio, que es la que abre el buzón por Outlook.
        'lector.titulo':   { en: 'Local reader', es: 'Lector local', fr: 'Lecteur local' },
        'lector.nota':     { en: 'This computer reads the mailbox through its desktop Outlook.', es: 'Esta computadora lee el buzón por su Outlook de escritorio.', fr: 'Cet ordinateur lit la boîte via son Outlook de bureau.' },
        'lector.iniciar':  { en: 'Start reader', es: 'Iniciar lector', fr: 'Démarrer le lecteur' },
        'lector.parar':    { en: 'Stop', es: 'Detener', fr: 'Arrêter' },
        'lector.ahora':    { en: 'Read now', es: 'Leer ahora', fr: 'Lire maintenant' },
        'lector.leidos':   { en: 'Emails read', es: 'Correos leídos', fr: 'Courriels lus' },
        'lector.rfqs':     { en: 'RFQs created', es: 'RFQ dados de alta', fr: 'RFQ créées' },
        'lector.errores':  { en: 'With errors', es: 'Con error', fr: 'En erreur' },
        'lector.detenido': { en: 'Stopped', es: 'Detenido', fr: 'Arrêté' },
        'lector.leyendo':  { en: 'Reading the mailbox', es: 'Leyendo el buzón', fr: 'Lecture de la boîte' },
        'lector.espera':   { en: 'Waiting (outside hours)', es: 'En espera (fuera de horario)', fr: 'En attente (hors horaires)' },
        'lector.vacio':    { en: 'Nothing yet: the reader has not started.', es: 'Nada todavía: el lector no ha arrancado.', fr: 'Rien encore : le lecteur n\'a pas démarré.' },

        // --- Comprobación del flujo (Perfil → Sistema) --------------------
        // Ojo: esta clave era 'flujo.titulo' y pisaba a la del recorrido de
        // Mail (dos claves iguales en el mismo objeto: manda la última), así
        // que la cabecera de Mail salía como '¿Listo para el flujo?'.
        'flujo.listoTitulo':{ en: 'Ready to run the flow?', es: '¿Listo para el flujo?', fr: 'Prêt pour le flux ?' },
        'flujo.comprobar':  { en: 'Check again', es: 'Comprobar de nuevo', fr: 'Vérifier à nouveau' },
        'flujo.comprobando':{ en: 'Checking…', es: 'Comprobando…', fr: 'Vérification…' },
        'flujo.listo':      { en: 'Nothing missing: the flow can run.', es: 'No falta nada: el flujo puede correr.', fr: 'Rien ne manque : le flux peut tourner.' },
        'flujo.faltan':     { en: '{n} thing(s) missing before it can run', es: 'Faltan {n} cosa(s) para poder probar', fr: '{n} élément(s) manquant(s) avant de pouvoir tester' },
        'flujo.avisos':     { en: '{n} to look at', es: '{n} para mirar', fr: '{n} à regarder' },
        'flujo.cuando':     { en: 'Checked at {hora}', es: 'Comprobado a las {hora}', fr: 'Vérifié à {hora}' },
        'flujo.fallo':      { en: 'The check could not run: {motivo}', es: 'No se pudo comprobar: {motivo}', fr: 'Vérification impossible : {motivo}' },

        // --- Cotización --------------------------------------------------
        'quoting.enObras': { en: 'Quoting is being rebuilt.', es: 'La pantalla de cotización se está rehaciendo.', fr: "L'écran de chiffrage est en refonte." },

        // --- Cotización: las tres caras del núcleo de ISC ------------------
        'quoting.tab.conexiones': { en: 'Connections', es: 'Conexiones', fr: 'Connexions' },
        'quoting.tab.precio':     { en: 'Price Calculator', es: 'Calculadora de precios', fr: 'Calculatrice de prix' },
        'quoting.tab.resortes':   { en: 'Spring Engineering', es: 'Ingeniería de resortes', fr: 'Ingénierie des ressorts' },
        'quoting.tab.lector':     { en: 'Drawing Reader', es: 'Lector de planos', fr: 'Lecteur de plans' },

        'quoting.comprobando':    { en: 'Checking what is installed...', es: 'Comprobando qué hay puesto...', fr: 'Vérification de ce qui est installé...' },
        'quoting.reintentar':     { en: 'Check again', es: 'Volver a comprobar', fr: 'Vérifier à nouveau' },

        'quoting.listo':          { en: 'Everything is connected', es: 'Todo está conectado', fr: 'Tout est connecté' },
        'quoting.listoSub':       { en: 'The core, Node, the reader and both calculators are in place.',
                                    es: 'El núcleo, Node, el lector y las dos calculadoras están en su sitio.',
                                    fr: 'Le noyau, Node, le lecteur et les deux calculatrices sont en place.' },
        'quoting.faltan':         { en: 'Something is missing', es: 'Falta algo', fr: 'Il manque quelque chose' },
        'quoting.faltanSub':      { en: 'Quoting works with what is here, and says what is not.',
                                    es: 'La cotización funciona con lo que hay, y dice lo que no.',
                                    fr: 'Le chiffrage fonctionne avec ce qui est là, et déclare ce qui manque.' },
        'quoting.sinDiagnostico': { en: 'Could not read the diagnosis', es: 'No se pudo leer el diagnóstico', fr: 'Diagnostic illisible' },

        'quoting.pieza.node':         { en: 'Node', es: 'Node', fr: 'Node' },
        'quoting.pieza.motor':        { en: 'Costing engine', es: 'Motor de costeo', fr: 'Moteur de coût' },
        'quoting.pieza.lector':       { en: 'Drawing reader', es: 'Lector de planos', fr: 'Lecteur de plans' },
        'quoting.pieza.calculadoras': { en: 'Calculators', es: 'Calculadoras', fr: 'Calculatrices' },

        'quoting.motor.local':     { en: 'Local copy', es: 'Copia local', fr: 'Copie locale' },
        'quoting.motor.nucleo':    { en: 'Core engine', es: 'Motor del núcleo', fr: 'Moteur du noyau' },
        'quoting.motor.sha':       { en: 'Core commit', es: 'Commit del núcleo', fr: 'Commit du noyau' },
        'quoting.motor.sinPiezas': { en: 'Missing from the core', es: 'Falta en el núcleo', fr: 'Manque dans le noyau' },

        'quoting.piezaLista': { en: 'Ready to mount', es: 'Lista para montar', fr: 'Prête à monter' },
        'quoting.abriendo':   { en: 'Opening...', es: 'Abriendo...', fr: 'Ouverture...' },
        'quoting.sinPuerta':  { en: 'Could not open the reader session', es: 'No se pudo abrir la sesión del lector', fr: "Impossible d'ouvrir la session du lecteur" },
        'quoting.lector.modo':    { en: 'Mode', es: 'Modo', fr: 'Mode' },
        'quoting.lector.motor':   { en: 'Engine', es: 'Motor', fr: 'Moteur' },
        'quoting.lector.router':  { en: 'Router model', es: 'Modelo router', fr: 'Modèle routeur' },
        'quoting.lector.extractor': { en: 'Extractor model', es: 'Modelo extractor', fr: 'Modèle extracteur' },
        'quoting.lector.tipos':   { en: 'Spring types', es: 'Tipos de resorte', fr: 'Types de ressort' },
        'quoting.lector.demo':    { en: 'DEMO mode: the values do NOT come from the drawing. Do not quote from them.',
                                    es: 'Modo DEMO: los valores NO salen del plano. No cotices con ellos.',
                                    fr: "Mode DÉMO : les valeurs ne viennent PAS du plan. Ne chiffrez pas avec." },
        'quoting.lector.donde':   { en: 'Drawings are read from inside the price calculator: open that tab and use its reader button.',
                                    es: 'Los planos se leen desde dentro de la calculadora de precios: abre esa pestaña y usa su botón de leer.',
                                    fr: "Les plans se lisent depuis la calculatrice de prix : ouvrez cet onglet et utilisez son bouton de lecture." },
        'quoting.piezaFalta': { en: 'Not ready yet', es: 'Todavía no está lista', fr: "Pas encore prête" },

        'quoting.sinPermiso': { en: 'Your role cannot use the calculators yet: it needs the "precio:calcular" permission. An administrator grants it from Profile → Users.',
                                es: 'Tu rol todavía no puede usar las calculadoras: le falta el permiso "precio:calcular". Lo concede un administrador desde Perfil → Usuarios.',
                                fr: 'Votre rôle ne peut pas encore utiliser les calculateurs : il lui manque la permission « precio:calcular ». Un administrateur l’accorde depuis Profil → Utilisateurs.' },
        'quoting.pendiente.precio':   { en: 'The calculator HTML is generated from the core with apps/calculadora/construir.py. Without it there is nothing to serve.',
                                        es: 'El HTML de la calculadora se genera desde el núcleo con apps/calculadora/construir.py. Sin él no hay nada que servir.',
                                        fr: "Le HTML de la calculatrice se génère depuis le noyau avec apps/calculadora/construir.py. Sans lui, rien à servir." },
        'quoting.pendiente.resortes': { en: 'The spring calculator is served as a sibling of the price one, so both are generated by the same build.',
                                        es: 'El calculador de resortes se sirve como hermano del de precios, así que los genera la misma construcción.',
                                        fr: "La calculatrice de ressorts est servie à côté de celle des prix : la même construction les génère." },
        'quoting.pendiente.lector':   { en: 'The reader is the Flask program in apps/lector of the core, mounted inside this API.',
                                        es: 'El lector es el programa Flask de apps/lector del núcleo, montado dentro de esta API.',
                                        fr: "Le lecteur est le programme Flask d'apps/lector du noyau, monté dans cette API." },


        // --- Asistente ---------------------------------------------------
        'asis.marcador':  { en: 'Ask about your RFQs or analyze trends…', es: 'Pregunta por tus RFQs o analiza tendencias…', fr: 'Posez une question sur vos RFQ ou analysez les tendances…' },
        'asis.enviar':    { en: 'Ask the assistant', es: 'Preguntar al asistente', fr: "Interroger l'assistant" },
        'asis.abrir':          { en: 'Open the assistant', es: 'Abrir el asistente', fr: 'Ouvrir l\'assistant' },
        'asis.chat':           { en: 'Assistant', es: 'Asistente', fr: 'Assistant' },
        'asis.resumen':   { en: 'Summarize', es: 'Resumen', fr: 'Résumé' },
        'asis.atencion':  { en: 'Needs attention', es: 'Requiere atención', fr: 'À traiter' },
        'asis.exportar':  { en: 'Export to Excel', es: 'Exportar a Excel', fr: 'Exporter vers Excel' },

        // Los accesos rápidos que sólo salen en su sección (Monitor, Mail,
        // Quoting, Overview): los decide js/components/assistant.js.
        // Abrir un RFQ dentro de la calculadora (js/pages/quoting.js).
        // Por qué la ficha del RFQ no tiene cotas del resorte (rfq-detail.js).
        'plano.sinAdjunto':  { en: 'The email brought no drawing — these values are read from one.', es: 'El correo no traía ningún plano: estos datos salen del dibujo.', fr: 'Le courriel n’apportait aucun plan : ces valeurs viennent du dessin.' },
        'plano.sinFormato':  { en: 'It brought {ficheros}, a format the reader does not open. It reads: {soportados}.', es: 'Traía {ficheros}, que no es un formato que el lector abra. Lee: {soportados}.', fr: 'Il apportait {ficheros}, un format que le lecteur n’ouvre pas. Il lit : {soportados}.' },
        'plano.fallo':       { en: 'Reading {ficheros} failed: {motivo}', es: 'Se intentó leer {ficheros} y falló: {motivo}', fr: 'La lecture de {ficheros} a échoué : {motivo}' },
        'rev.geometria':   { en: 'Spring geometry', es: 'Geometría del resorte', fr: 'Géométrie du ressort' },
        'rev.recalcular':  { en: 'Recalculate', es: 'Recalcular', fr: 'Recalculer' },
        'rev.recalculando':{ en: 'Recalculating…', es: 'Recalculando…', fr: 'Recalcul…' },
        'rev.recalculado': { en: 'Verdict redone with {n} corrected value(s).', es: 'Dictamen rehecho con {n} valor(es) corregido(s).', fr: 'Verdict refait avec {n} valeur(s) corrigée(s).' },
        'rev.recalculadoSinCambios': { en: 'Verdict redone. Nothing was changed.', es: 'Dictamen rehecho. No cambió ningún valor.', fr: 'Verdict refait. Aucune valeur modifiée.' },
        'rev.espirasDeducidas': { en: 'Total coils not on the drawing: {n} used for the weight ({metodo}).', es: 'El plano no da las espiras totales: se usan {n} para el peso ({metodo}).', fr: 'Le plan ne donne pas les spires totales : {n} sont utilisées pour le poids ({metodo}).' },
        'rev.recalcularNota': { en: 'The verdict and the flags come from these values. Correct them and recalculate before approving or declining.', es: 'El veredicto y los motivos salen de estos valores. Corrígelos y recalcula antes de aprobar o declinar.', fr: 'Le verdict et les motifs viennent de ces valeurs. Corrigez-les et recalculez avant d’approuver ou de refuser.' },
        'rev.ajustadoPor': { en: 'corrected by {quien}', es: 'corregido por {quien}', fr: 'corrigé par {quien}' },
        'plano.releer':      { en: 'Read the drawing with AI', es: 'Leer el plano con IA', fr: 'Lire le plan avec l’IA' },
        'plano.releyendo':   { en: 'Reading the drawing…', es: 'Leyendo el plano…', fr: 'Lecture du plan…' },
        'plano.releido':     { en: 'Drawing read: {ficheros}.', es: 'Plano leído: {ficheros}.', fr: 'Plan lu : {ficheros}.' },
        'plano.sinCotas':    { en: 'The drawing was read and gave no dimensions.', es: 'El plano se leyó y no dio ninguna cota.', fr: 'Le plan a été lu et n’a donné aucune cote.' },
        'ficha.comercial':   { en: 'Commercial Data', es: 'Datos comerciales', fr: 'Données commerciales' },
        'ficha.fisica':      { en: 'Spring Physics (AI Extracted)', es: 'Geometría del resorte (extraída por IA)', fr: 'Géométrie du ressort (extraite par IA)' },
        'ficha.cliente':     { en: 'Customer', es: 'Cliente', fr: 'Client' },
        'ficha.parte':       { en: 'Part Number', es: 'Número de parte', fr: 'Référence' },
        'ficha.volumen':     { en: 'Volume (EAU)', es: 'Volumen (EAU)', fr: 'Volume (EAU)' },
        'ficha.material':    { en: 'Required Material', es: 'Material pedido', fr: 'Matière demandée' },
        'ficha.remitente':   { en: 'Sender', es: 'Remitente', fr: 'Expéditeur' },
        'ficha.tipo':        { en: 'Type', es: 'Tipo', fr: 'Type' },
        'ficha.alambre':     { en: 'Wire Diameter', es: 'Diámetro de alambre', fr: 'Diamètre du fil' },
        'ficha.exterior':    { en: 'Outer Diameter', es: 'Diámetro exterior', fr: 'Diamètre extérieur' },
        'ficha.libre':       { en: 'Free Length', es: 'Longitud libre', fr: 'Longueur libre' },
        'ficha.espiras':     { en: 'Total Coils', es: 'Espiras totales', fr: 'Spires totales' },
        'ficha.confianza':   { en: 'AI Confidence', es: 'Confianza de la IA', fr: 'Confiance de l’IA' },
        'ficha.banderas':    { en: 'Review Flags', es: 'Motivos de revisión', fr: 'Motifs de révision' },
        // El dictamen del Spring Engineering Calculator (components/spring-calc.js).
        'spring.titulo':     { en: 'Spring Calc', es: 'Spring Calc', fr: 'Spring Calc' },
        'spring.noFactible': { en: 'NOT FEASIBLE — the plant cannot make this spring', es: 'NO FACTIBLE: la planta no puede fabricar este resorte', fr: 'NON FAISABLE : l’usine ne peut pas fabriquer ce ressort' },
        'spring.noFactibleCorto': { en: 'Not feasible', es: 'No factible', fr: 'Non faisable' },
        'spring.bloqueo.alambre_maximo': { en: 'wire Ø {valor} mm reaches the ISC limit of {pulg}" ({mm} mm). Not feasible — do not price.', es: 'el alambre de Ø {valor} mm llega al límite de ISC de {pulg}" ({mm} mm). No factible: no se cotiza.', fr: 'le fil de Ø {valor} mm atteint la limite ISC de {pulg}" ({mm} mm). Non faisable : ne pas chiffrer.' },
        'spring.bloqueo.sin_maquina': { en: 'no coiler in the shop takes {alambre} mm wire with {od} mm OD. The thickest wire the shop coils for this spring type is {max} mm.', es: 'ninguna enrolladora del taller admite alambre de {alambre} mm con {od} mm de DE. Lo más grueso que enrolla el taller para este tipo de resorte es {max} mm.', fr: 'aucune enrouleuse de l’atelier n’accepte un fil de {alambre} mm avec {od} mm de DE. Le fil le plus épais que l’atelier enroule pour ce type de ressort est {max} mm.' },
        'spring.bloqueo.sin_maquinaSinOd': { en: 'no coiler in the shop takes {alambre} mm wire. The thickest wire the shop coils for this spring type is {max} mm.', es: 'ninguna enrolladora del taller admite alambre de {alambre} mm. Lo más grueso que enrolla el taller para este tipo de resorte es {max} mm.', fr: 'aucune enrouleuse de l’atelier n’accepte un fil de {alambre} mm. Le fil le plus épais que l’atelier enroule pour ce type de ressort est {max} mm.' },
        'spring.puntaje':    { en: 'score {score}/100, {banda}', es: 'puntaje {score}/100, {banda}', fr: 'score {score}/100, {banda}' },
        'spring.soloGeometria': { en: '(geometry only — no working point on the drawing)', es: '(sólo geometría: el plano no trae punto de trabajo)', fr: '(géométrie seule : pas de point de travail sur le plan)' },
        'spring.maquina':    { en: 'coiler {maq}', es: 'enrolladora {maq}', fr: 'enrouleuse {maq}' },
        'spring.cotizadoAMano': { en: 'Quoted manually by the PM', es: 'Cotizado a mano por el PM', fr: 'Chiffré à la main par le PM' },
        'spring.intervencion':    { en: 'Spring Calc says the plant cannot make it, but the PM has quoted it manually in the full quote: feasibility is the PM’s call.', es: 'Según Spring Calc la planta no puede hacerlo, pero el PM ya lo cotizó a mano en la cotización completa: la factibilidad la decide el PM.', fr: 'Selon Spring Calc l’usine ne peut pas le faire, mais le PM l’a chiffré à la main dans le devis complet : la faisabilité est la décision du PM.' },
        'spring.intervencionPor': { en: 'Spring Calc says the plant cannot make it, but {por} has quoted it manually in the full quote: feasibility is the PM’s call.', es: 'Según Spring Calc la planta no puede hacerlo, pero {por} ya lo cotizó a mano en la cotización completa: la factibilidad la decide el PM.', fr: 'Selon Spring Calc l’usine ne peut pas le faire, mais {por} l’a chiffré à la main dans le devis complet : la faisabilité est la décision du PM.' },
        'rev.aprobarConPm':  { en: 'Spring Calc said not feasible. Approving uses your manual quote from the full quote.', es: 'Spring Calc dijo no factible. Al aprobar se usa tu cotización manual de la cotización completa.', fr: 'Spring Calc a dit non faisable. L’approbation utilise votre chiffrage manuel du devis complet.' },
        'rev.noAprobable':   { en: 'Approve is disabled: Spring Calc says the plant cannot make this spring. Quote it manually with “Open full quote” and come back here to give feasibility, or decline it.', es: 'Aprobar está deshabilitado: según Spring Calc la planta no puede fabricar este resorte. Cotízalo a mano con «Abrir cotización completa» y regresa aquí para dar factibilidad, o recházalo.', fr: 'Approuver est désactivé : selon Spring Calc, l’usine ne peut pas fabriquer ce ressort. Chiffrez-le à la main avec « Ouvrir le devis complet » puis revenez ici pour donner la faisabilité, ou refusez-le.' },
        'ficha.notasPm':     { en: 'PM Notes', es: 'Notas del PM', fr: 'Notes du PM' },
        'plano.leidoVacio':  { en: 'The drawing ({ficheros}) was read and gave no dimensions.', es: 'El plano ({ficheros}) se leyó y no dio ninguna cota.', fr: 'Le plan ({ficheros}) a été lu et n’a donné aucune cote.' },

        // --- Los motivos del dictamen de factibilidad --------------------
        // El motor (app/feasibility/engine.py) razona con un código, el campo,
        // el valor y el límite; desde la migración 022 eso se guarda con la
        // bandera y la frase se arma aquí, en el idioma puesto.
        'factib.tipo_desconocido':      { en: 'The spring type could not be determined; it is judged only against the common ranges.', es: 'No se pudo determinar el tipo de resorte; se evalúa sólo con los rangos comunes.', fr: 'Le type de ressort n’a pas pu être déterminé ; il est jugé seulement sur les plages communes.' },
        'factib.tipo_no_fabricable':    { en: 'Spring type not manufacturable: {valor}. The plant makes {limite}.', es: 'Tipo de resorte no fabricable: {valor}. La planta fabrica {limite}.', fr: 'Type de ressort non fabricable : {valor}. L’usine fabrique {limite}.' },
        'factib.material_ausente':      { en: 'The drawing does not state a material.', es: 'El plano no declara material.', fr: 'Le plan ne déclare pas de matière.' },
        'factib.material_no_soportado': { en: 'Material not supported: {valor}. It matches none of the plant materials.', es: 'Material no soportado: {valor}. No coincide con ninguno de los materiales de la planta.', fr: 'Matière non prise en charge : {valor}. Elle ne correspond à aucune matière de l’usine.' },
        'factib.material_fuera_de_rango': { en: 'Wire of {valor} mm falls outside the gauges in which this material is available.', es: 'El alambre de {valor} mm queda fuera de los calibres en que se consigue este material.', fr: 'Le fil de {valor} mm sort des calibres dans lesquels cette matière est disponible.' },
        'factib.dato_ausente':          { en: '{Campo} is missing and is needed to decide.', es: 'Falta {campo} para dictaminar.', fr: '{Campo} manque et est nécessaire pour décider.' },
        'factib.dato_no_numerico':      { en: '{Campo} is not a number: {valor}.', es: '{Campo} no es un número: {valor}.', fr: '{Campo} n’est pas un nombre : {valor}.' },
        'factib.fuera_de_rango':        { en: '{Campo} out of range: {valor}{unidad} (manufacturable {limite}).', es: '{Campo} fuera de rango: {valor}{unidad} (fabricable {limite}).', fr: '{Campo} hors plage : {valor}{unidad} (fabricable {limite}).' },
        'factib.fuera_del_preferido':   { en: '{Campo} at {valor}{unidad}: manufacturable, but outside the usual range ({limite}).', es: '{Campo} en {valor}{unidad}: fabricable, pero fuera del rango habitual ({limite}).', fr: '{Campo} à {valor}{unidad} : fabricable, mais hors de la plage habituelle ({limite}).' },
        'factib.tolerancia_mas_fina':   { en: 'The drawing asks for ±{valor} mm and the plant\'s minimum tolerance is ±{limite} mm.', es: 'El plano pide ±{valor} mm y la tolerancia mínima de la planta es ±{limite} mm.', fr: 'Le plan demande ±{valor} mm et la tolérance minimale de l’usine est ±{limite} mm.' },
        'factib.confianza_baja':        { en: 'The drawing was read with {valor} confidence, below the {limite} minimum.', es: 'La extracción del plano quedó en {valor} de confianza, por debajo del mínimo de {limite}.', fr: 'La lecture du plan est à {valor} de confiance, sous le minimum de {limite}.' },

        // Los campos del resorte, para poder nombrarlos dentro de los motivos.
        'campo.diametro_alambre_mm':    { en: 'wire diameter', es: 'diámetro de alambre', fr: 'diamètre du fil' },
        'campo.diametro_exterior_mm':   { en: 'outer diameter', es: 'diámetro exterior', fr: 'diamètre extérieur' },
        'campo.diametro_interior_mm':   { en: 'inner diameter', es: 'diámetro interior', fr: 'diamètre intérieur' },
        'campo.diametro_medio_mm':      { en: 'mean diameter', es: 'diámetro medio', fr: 'diamètre moyen' },
        'campo.longitud_libre_mm':      { en: 'free length', es: 'longitud libre', fr: 'longueur libre' },
        'campo.longitud_cuerpo_mm':     { en: 'body length', es: 'longitud del cuerpo', fr: 'longueur du corps' },
        'campo.numero_espiras_totales': { en: 'number of coils', es: 'número de espiras', fr: 'nombre de spires' },
        'campo.numero_espiras_activas': { en: 'active coils', es: 'espiras activas', fr: 'spires actives' },
        'campo.angulo_brazos_grados':   { en: 'angle between legs', es: 'ángulo entre brazos', fr: 'angle entre les branches' },
        'campo.longitud_gancho_mm':     { en: 'hook length', es: 'longitud del gancho', fr: 'longueur du crochet' },
        'campo.constante_resorte_N_mm': { en: 'spring rate', es: 'constante del resorte', fr: 'raideur du ressort' },
        'campo.material':               { en: 'material', es: 'material', fr: 'matière' },
        'campo.part_number':            { en: 'part number', es: 'número de parte', fr: 'référence' },
        'campo.volumen':                { en: 'volume (EAU)', es: 'volumen (EAU)', fr: 'volume (EAU)' },
        'campo.customer':               { en: 'customer', es: 'cliente', fr: 'client' },
        'campo.tiene_adjunto':          { en: 'drawing attached', es: 'plano adjunto', fr: 'plan joint' },
        'campo.indice_resorte':         { en: 'spring index (Dm/d)', es: 'índice del resorte (Dm/d)', fr: 'indice du ressort (Dm/d)' },
        'campo.tipo_resorte':           { en: 'spring type', es: 'tipo de resorte', fr: 'type de ressort' },
        'campo.tolerancias':            { en: 'tolerances', es: 'tolerancias', fr: 'tolérances' },
        'campo.confianza':              { en: 'reading confidence', es: 'confianza de la lectura', fr: 'confiance de la lecture' },

        // Los motivos de un costeo incompleto y de una oferta que no está
        // lista. El servidor los manda con su CÓDIGO (pricing/mensajes.py)
        // porque él no sabe en qué idioma está Pohua: la frase se arma aquí.
        // Si llega un código que esta versión no conoce, se enseña el texto
        // que vino del servidor y no un hueco.
        'costeo.PARAMETROS_SIN_JUEGO':   { en: 'No current parameter set in the database; the engine defaults are used.', es: 'No hay un juego de parámetros vigente en la base; se usan los del motor.', fr: 'Aucun jeu de paramètres en vigueur dans la base ; ceux du moteur sont utilisés.' },
        'costeo.PARAMETROS_ILEGIBLES':   { en: 'Costing parameters could not be read: {error}', es: 'Parámetros de costeo ilegibles: {error}', fr: 'Paramètres de calcul illisibles : {error}' },
        'costeo.SIN_DIAMETRO_ALAMBRE':   { en: 'Wire diameter is missing: without it no machine can be chosen and no material price looked up.', es: 'Falta el diámetro de alambre: sin él no se puede elegir máquina ni buscar el precio del material.', fr: 'Le diamètre du fil manque : sans lui, impossible de choisir une machine ni de chercher le prix de la matière.' },
        'costeo.SIN_PESO_POR':           { en: 'Wire weight could not be calculated: {campo} is missing. Without the weight, material cost would come out at zero.', es: 'No se pudo calcular el peso del alambre: falta {campo}. Sin el peso, el costo del material saldría en cero.', fr: 'Le poids du fil n’a pas pu être calculé : {campo} manque. Sans le poids, le coût matière sortirait à zéro.' },
        'costeo.SIN_MAQUINA_CAPAZ':      { en: 'No active machine in the catalogue can make a {tipo} spring with {diametro} mm wire.', es: 'Ninguna máquina activa del catálogo puede hacer un resorte de {tipo} con alambre de {diametro} mm.', fr: 'Aucune machine active du catalogue ne peut faire un ressort de {tipo} avec un fil de {diametro} mm.' },
        'costeo.MAQUINA_SIN_TARIFA':     { en: 'Machine {maquina} has no current rate in the catalogue.', es: 'La máquina {maquina} no tiene tarifa vigente en el catálogo.', fr: 'La machine {maquina} n’a pas de tarif en vigueur au catalogue.' },
        'costeo.MAQUINA_FALLO':          { en: 'Machine selection failed: {error}', es: 'Selección de máquina fallida: {error}', fr: 'Échec du choix de la machine : {error}' },
        'costeo.MATERIAL_SIN_CATALOGO':  { en: 'Material \'{material}\' is not in the materials catalogue.', es: 'El material \'{material}\' no está en el catálogo de materiales.', fr: 'La matière \'{material}\' n’est pas au catalogue des matières.' },
        'costeo.MATERIAL_SIN_PRECIO':    { en: 'Material \'{material}\' has no price in the catalogue.', es: 'El material \'{material}\' no tiene precio en el catálogo.', fr: 'La matière \'{material}\' n’a pas de prix au catalogue.' },
        'costeo.MATERIAL_ILEGIBLE':      { en: 'Material price could not be read: {error}', es: 'Precio de material ilegible: {error}', fr: 'Prix de la matière illisible : {error}' },
        'costeo.SIN_MATERIAL':           { en: 'No material was given: the wire cannot be costed.', es: 'No se indicó material: no se puede costear el alambre.', fr: 'Aucune matière indiquée : impossible de chiffrer le fil.' },
        'costeo.SIN_EMPAQUES':           { en: 'There are no active packings in the catalogue.', es: 'No hay empaques activos en el catálogo.', fr: 'Aucun emballage actif au catalogue.' },
        'costeo.EMPAQUE_ILEGIBLE':       { en: 'Packing could not be read: {error}', es: 'Empaque ilegible: {error}', fr: 'Emballage illisible : {error}' },
        'costeo.SIN_CANTIDAD':           { en: 'No quantity was given: tiered costing needs a volume.', es: 'No se indicó cantidad: el costeo por escalones necesita un volumen.', fr: 'Aucune quantité indiquée : le chiffrage par paliers a besoin d’un volume.' },
        'costeo.SIN_PESO_ALAMBRE':       { en: 'Wire weight could not be calculated (diameter, mean diameter or coils are missing): material cost would come out at zero.', es: 'No se pudo calcular el peso del alambre (faltan diámetro, diámetro medio o número de espiras): el costo de material saldría en cero.', fr: 'Le poids du fil n’a pas pu être calculé (diamètre, diamètre moyen ou spires manquants) : le coût matière sortirait à zéro.' },
        'costeo.PESO_SOLO_CUERPO':       { en: 'The weight covers only the spring body; hooks or legs are still to be captured, so material is understated.', es: 'El peso sólo cubre el cuerpo del resorte; faltan ganchos o patas por capturar, así que el material está subestimado.', fr: 'Le poids ne couvre que le corps du ressort ; crochets ou pattes restent à saisir, la matière est donc sous-estimée.' },
        'costeo.SIN_CANTIDADES_RFQ':     { en: 'The RFQ brings no quantity: there are no tiers to cost.', es: 'El RFQ no trae ninguna cantidad: no hay tramos que costear.', fr: 'La RFQ n’apporte aucune quantité : il n’y a pas de paliers à chiffrer.' },
        'costeo.SIN_MATERIAL_NI_DIAMETRO': { en: 'Without material or wire diameter there is nothing to cost: capture them in the full quote.', es: 'Sin material ni diámetro de alambre no se puede costear: hay que capturarlos en la cotización completa.', fr: 'Sans matière ni diamètre de fil, rien à chiffrer : à saisir dans la cotation complète.' },
        'costeo.OFERTA_NO_APROBADA':     { en: 'The RFQ is in \'{estado}\': only an approved RFQ can be quoted.', es: 'El RFQ está en \'{estado}\': sólo se oferta un RFQ aprobado.', fr: 'La RFQ est en \'{estado}\' : seule une RFQ approuvée peut être proposée.' },
        'costeo.OFERTA_SIN_TRAMOS':      { en: 'There are no costed tiers: {detalle}', es: 'No hay tramos costeados: {detalle}', fr: 'Aucun palier chiffré : {detalle}' },
        'costeo.OFERTA_ORIENTATIVA':     { en: 'The price is indicative: {detalle}', es: 'El costeo es orientativo: {detalle}', fr: 'Le prix est indicatif : {detalle}' },
        'costeo.OFERTA_SIN_DESTINO':     { en: 'There is nobody to send it to: the RFQ has no sender.', es: 'No hay a quién mandarla: el RFQ no trae remitente.', fr: 'Personne à qui l’envoyer : la RFQ n’a pas d’expéditeur.' },

        'rev.sinPdf':        { en: 'There is no quote to preview yet.', es: 'Todavía no hay cotización que previsualizar.', fr: 'Aucune cotation à prévisualiser pour l’instant.' },
        'quoting.volverRevision': { en: '\u2190 Back to review \u00b7 {rfq}', es: '\u2190 Volver a la revisi\u00f3n \u00b7 {rfq}', fr: '\u2190 Retour \u00e0 la revue \u00b7 {rfq}' },
        'quoting.cotizacionNoGuardada': { en: 'The quote could not be saved to the RFQ; the review shows the last saved numbers.', es: 'No se pudo guardar la cotización en el RFQ; la revisión enseña lo último guardado.', fr: 'Le devis n’a pas pu être enregistré dans le RFQ ; la revue montre les derniers chiffres enregistrés.' },
        'quoting.rfqFallo':  { en: 'Could not open the RFQ in the calculator: {motivo}', es: 'No se pudo abrir el RFQ en la calculadora: {motivo}', fr: 'Impossible d’ouvrir la RFQ dans le calculateur : {motivo}' },
        'quoting.rfqParcial':{ en: 'The RFQ opens with what could be read: {motivo}', es: 'El RFQ abre con lo que se pudo leer: {motivo}', fr: 'La RFQ s’ouvre avec ce qui a pu être lu : {motivo}' },

        'asis.errores':   { en: 'Errors', es: 'Errores', fr: 'Erreurs' },
        'asis.estado':    { en: 'Service status', es: 'Estado del servicio', fr: 'État du service' },
        'asis.registro':  { en: 'Download log', es: 'Descargar registro', fr: 'Télécharger le journal' },
        'asis.recorrido': { en: 'Mail flow', es: 'Recorrido del correo', fr: 'Parcours du courrier' },
        'asis.topClientes': { en: 'Top customers', es: 'Clientes de la semana', fr: 'Clients de la semaine' },

        'asis.tituloErrores':   { en: 'What failed', es: 'Lo que falló', fr: 'Ce qui a échoué' },
        'asis.tituloEstado':    { en: 'Service status', es: 'Estado del servicio', fr: 'État du service' },
        'asis.tituloRecorrido': { en: 'Mail flow', es: 'Recorrido del correo', fr: 'Parcours du courrier' },
        'asis.tituloClientes':  { en: 'Customers this week', es: 'Clientes de esta semana', fr: 'Clients de cette semaine' },

        'asis.deLineas':   { en: 'out of the last {n} lines', es: 'de las últimas {n} líneas', fr: 'sur les {n} dernières lignes' },
        'asis.sinErrores': { en: 'Nothing failed in the lines loaded.', es: 'No falló nada en las líneas cargadas.', fr: 'Rien n’a échoué dans les lignes chargées.' },
        'asis.sinDatos':   { en: 'Nothing to show yet.', es: 'Todavía no hay nada que enseñar.', fr: 'Rien à afficher pour l’instant.' },
        'asis.sinSemana':  { en: 'No requests came in over the last seven days.', es: 'No entró ninguna solicitud en los últimos siete días.', fr: 'Aucune demande reçue ces sept derniers jours.' },
        'asis.recorridoNota': { en: 'Amber = waiting on a person', es: 'Ámbar = esperando a una persona', fr: 'Ambre = en attente d’une personne' },
        'asis.semanaNota': { en: '{n} requests · {nuevos} not in the catalog yet', es: '{n} solicitudes · {nuevos} todavía sin dar de alta', fr: '{n} demandes · {nuevos} pas encore au catalogue' },
        'asis.estrella':   { en: 'key account', es: 'cuenta clave', fr: 'compte clé' },
        'asis.nuevo':      { en: 'new', es: 'nuevo', fr: 'nouveau' },
        'asis.registroHecho': { en: 'Log downloaded.', es: 'Registro descargado.', fr: 'Journal téléchargé.' },

        'asis.est.servicio':   { en: 'Service', es: 'Servicio', fr: 'Service' },
        'asis.est.enMarcha':   { en: 'Running', es: 'En marcha', fr: 'En marche' },
        'asis.est.parado':     { en: 'Stopped', es: 'Parado', fr: 'Arrêté' },
        'asis.est.espera':     { en: 'Waiting — outside business hours', es: 'En espera — fuera del horario', fr: 'En attente — hors horaires' },
        'asis.est.buzon':      { en: 'Mailbox', es: 'Buzón', fr: 'Boîte' },
        'asis.est.intervalo':  { en: 'Every', es: 'Cada', fr: 'Toutes les' },
        'asis.est.minutos':    { en: '{n} min', es: '{n} min', fr: '{n} min' },
        'asis.est.ultimo':     { en: 'Last round', es: 'Última vuelta', fr: 'Dernier tour' },
        'asis.est.siguiente':  { en: 'Next round', es: 'Próxima vuelta', fr: 'Prochain tour' },
        'asis.est.procesados': { en: 'Emails read', es: 'Correos leídos', fr: 'Courriels lus' },
        'asis.est.rfqs':       { en: 'RFQs created', es: 'RFQ creados', fr: 'RFQ créés' },
        'asis.est.errores':    { en: 'Errors', es: 'Errores', fr: 'Erreurs' },
        'asis.cerrar':    { en: 'Close', es: 'Cerrar', fr: 'Fermer' },
        'asis.pensando':  { en: 'Thinking…', es: 'Pensando…', fr: 'Réflexion…' },
        'asis.deLaBase':  { en: 'Counted in the database', es: 'Contado en la base de datos', fr: 'Compté dans la base de données' },
        'asis.deLaBase2': { en: 'From the database', es: 'De la base de datos', fr: 'Depuis la base de données' },
        'asis.total':     { en: 'Total RFQs', es: 'RFQs totales', fr: 'RFQ au total' },
        'asis.dias7':     { en: 'Last 7 days', es: 'Últimos 7 días', fr: '7 derniers jours' },
        'asis.dias30':    { en: 'Last 30 days', es: 'Últimos 30 días', fr: '30 derniers jours' },
        'asis.clientes':  { en: 'Customers', es: 'Clientes', fr: 'Clients' },
        'asis.porEstado': { en: 'By state', es: 'Por estado', fr: 'Par état' },
        'asis.materiales': { en: 'Top materials', es: 'Materiales más pedidos', fr: 'Matériaux les plus demandés' },
        'asis.sinRfqs':   { en: 'No RFQs registered yet.', es: 'Todavía no hay RFQs registradas.', fr: 'Aucune RFQ enregistrée.' },
        'asis.sinMaterial': { en: 'No material recorded.', es: 'Ningún material registrado.', fr: 'Aucun matériau enregistré.' },
        'asis.nadaPendiente': { en: 'Nothing waiting: every RFQ has a decision.', es: 'Nada pendiente: todas las RFQ tienen dictamen.', fr: 'Rien en attente : toutes les RFQ ont une décision.' },
        // Por qué espera un RFQ, cuando el sistema no le puso ninguna bandera.
        'motivo.validacion': { en: 'Quote validation required', es: 'Falta validar la cotización', fr: 'Validation du devis requise' },
        'motivo.revision':   { en: 'Feasibility review required', es: 'Falta revisar la factibilidad', fr: 'Revue de faisabilité requise' },
        'motivo.oferta':     { en: 'Approved: send the offer', es: 'Aprobado: falta enviar la oferta', fr: 'Approuvée : envoyer l’offre' },
        'oferta.enviarAhora': { en: 'Send offer', es: 'Enviar oferta', fr: 'Envoyer l’offre' },
        'oferta.enCola':     { en: 'Offer queued: it goes out through Outlook on the next cycle', es: 'Oferta en cola: sale por Outlook en el siguiente ciclo', fr: 'Offre en file : elle part par Outlook au prochain cycle' },
        'ficha.deshacerAprobacion': { en: 'Undo approval', es: 'Deshacer aprobación', fr: 'Annuler l’approbation' },
        'dlg.deshacer.titulo':  { en: 'Undo the approval', es: 'Deshacer la aprobación', fr: 'Annuler l’approbation' },
        'dlg.deshacer.mensaje': { en: 'The RFQ goes back to review. The customer received nothing: the offer had not been sent.', es: 'El RFQ vuelve a revisión. El cliente no recibió nada: la oferta no había salido.', fr: 'La RFQ revient en revue. Le client n’a rien reçu : l’offre n’était pas partie.' },
        'dlg.deshacer.motivo':  { en: 'Why', es: 'Por qué', fr: 'Pourquoi' },
        'dlg.deshacer.ejemplo': { en: 'e.g. approved by mistake when switching tabs', es: 'p. ej. se aprobó sin querer al cambiar de pestaña', fr: 'p. ex. approuvée par erreur en changeant d’onglet' },
        'dlg.deshacer.si':      { en: 'Undo approval', es: 'Deshacer aprobación', fr: 'Annuler l’approbation' },
        'aviso.aprobacionDeshecha': { en: 'Approval undone: the RFQ is back in review.', es: 'Aprobación deshecha: el RFQ vuelve a revisión.', fr: 'Approbation annulée : la RFQ revient en revue.' },
        'ficha.enviarOferta': { en: 'Send offer →', es: 'Enviar oferta →', fr: 'Envoyer l’offre →' },
        'asis.esperando': { en: '{n} waiting · {c} with critical flags', es: '{n} pendientes · {c} con banderas críticas', fr: '{n} en attente · {c} avec alertes critiques' },
        'asis.tokens':    { en: '{entrada} in / {salida} out tokens', es: '{entrada} tokens de entrada / {salida} de salida', fr: '{entrada} jetons entrants / {salida} sortants' },
        'asis.col.rfq':      { en: 'RFQ', es: 'RFQ', fr: 'RFQ' },
        'asis.col.cliente':  { en: 'Customer', es: 'Cliente', fr: 'Client' },
        'asis.col.pieza':    { en: 'Part', es: 'Pieza', fr: 'Pièce' },
        'asis.col.estado':   { en: 'State', es: 'Estado', fr: 'État' },
        'asis.col.espera':   { en: 'Waiting', es: 'Esperando', fr: 'En attente' },
        'asis.col.bandera':  { en: 'Flag', es: 'Bandera', fr: 'Alerte' },
        'asis.col.fecha':    { en: 'Date', es: 'Fecha', fr: 'Date' },
        'asis.col.resultado': { en: 'Result', es: 'Resultado', fr: 'Résultat' },
        'asis.dictaminados': { en: 'Decided RFQs', es: 'RFQ dictaminados', fr: 'RFQ décidées' },
        'asis.siguiente':    { en: 'Next pending', es: 'Siguiente pendiente', fr: 'Suivante en attente' },
        'asis.revisar':      { en: 'Review', es: 'Revisar', fr: 'Réviser' },
        'asis.hoja':         { en: 'Open in the sheet', es: 'Abrir en la hoja', fr: 'Ouvrir dans la feuille' },
        'asis.espera':       { en: 'Waiting on customer', es: 'Esperando al cliente', fr: 'En attente du client' },
        'asis.ciclo':        { en: 'Read mail now', es: 'Leer correo ahora', fr: 'Lire le courrier' },
        'asis.tituloEspera': { en: 'Waiting on the customer', es: 'Esperando al cliente', fr: 'En attente du client' },
        'asis.esperaNota':   { en: '{n} with missing data · we asked the buyer', es: '{n} con datos faltantes · se le pidieron al comprador', fr: '{n} avec données manquantes · demandées à l’acheteur' },
        'asis.nadaEspera':   { en: 'No RFQ is waiting on a customer.', es: 'Ningún RFQ está esperando al cliente.', fr: 'Aucune RFQ n’attend le client.' },
        'asis.col.falta':    { en: 'Missing', es: 'Falta', fr: 'Manque' },
        'asis.tituloDictaminados': { en: 'Decided RFQs', es: 'RFQ dictaminados', fr: 'RFQ décidées' },
        'asis.dictaminadosNota': { en: '{a} approved · {d} declined', es: '{a} aprobados · {d} rechazados', fr: '{a} approuvées · {d} refusées' },
        'asis.errResumen':   { en: 'Could not load the summary', es: 'No se pudo cargar el resumen', fr: 'Impossible de charger le résumé' },
        'asis.errLista':     { en: 'Could not load the list', es: 'No se pudo cargar la lista', fr: 'Impossible de charger la liste' },
        'asis.errPregunta':  { en: 'Could not ask the assistant', es: 'No se pudo consultar al asistente', fr: "Impossible d'interroger l'assistant" },
        'asis.tituloResumen': { en: 'Summary', es: 'Resumen', fr: 'Résumé' },
        'asis.tituloAtencion': { en: 'Needs attention', es: 'Requiere atención', fr: 'À traiter' },
        'asis.tituloChat':   { en: 'Assistant', es: 'Asistente', fr: 'Assistant' },

        // --- Perfil ------------------------------------------------------
        'perfil.tab.mio':      { en: 'My profile', es: 'Mi perfil', fr: 'Mon profil' },
        'perfil.tab.usuarios': { en: 'Users', es: 'Usuarios', fr: 'Utilisateurs' },
        'perfil.tab.sistema':  { en: 'System', es: 'Sistema', fr: 'Système' },
        'perfil.foto':         { en: 'Photo', es: 'Foto', fr: 'Photo' },
        'perfil.cambiarFoto':  { en: 'Change photo', es: 'Cambiar foto', fr: 'Changer la photo' },
        'perfil.quitarFoto':   { en: 'Remove', es: 'Quitar', fr: 'Supprimer' },
        'perfil.notaFoto':     { en: 'Cropped to a {lado}×{lado} square in your browser.', es: 'Se recorta a un cuadrado de {lado}×{lado} en tu navegador.', fr: 'Recadrée en carré {lado}×{lado} dans votre navigateur.' },
        'perfil.datos':        { en: 'Details', es: 'Datos', fr: 'Informations' },
        'perfil.nombre':       { en: 'Name', es: 'Nombre', fr: 'Nom' },
        'perfil.correo':       { en: 'Email', es: 'Correo', fr: 'E-mail' },
        'perfil.notaCorreo':   { en: 'Your sign-in identity. RFQ decisions are recorded against it, so it cannot be changed.', es: 'Es tu identidad de acceso. Los dictámenes sobre RFQs quedan firmados con ella, así que no se puede cambiar.', fr: "C'est votre identifiant de connexion. Les décisions sur les RFQ y sont rattachées : il ne peut pas être modifié." },
        'perfil.rol':          { en: 'Role', es: 'Rol', fr: 'Rôle' },
        'perfil.guardar':      { en: 'Save changes', es: 'Guardar cambios', fr: 'Enregistrer' },
        'perfil.password':     { en: 'Password', es: 'Contraseña', fr: 'Mot de passe' },
        'perfil.pwActual':     { en: 'Current password', es: 'Contraseña actual', fr: 'Mot de passe actuel' },
        'perfil.pwNueva':      { en: 'New password', es: 'Contraseña nueva', fr: 'Nouveau mot de passe' },
        'perfil.pwRepetir':    { en: 'Repeat new password', es: 'Repite la nueva', fr: 'Confirmez le nouveau' },
        'perfil.pwMinimo':     { en: 'At least 12 characters.', es: 'Al menos 12 caracteres.', fr: 'Au moins 12 caractères.' },

        // --- Contraseñas: el ojo y los requisitos -------------------------
        // Los requisitos son los del servidor (app/auth/passwords.py). El
        // número va en {n} y no escrito a mano: si algún día sube el mínimo,
        // se cambia en un sitio y las tres lenguas lo siguen.
        'pw.ver':              { en: 'Show password', es: 'Ver la contraseña', fr: 'Afficher le mot de passe' },
        'pw.ocultar':          { en: 'Hide password', es: 'Ocultar la contraseña', fr: 'Masquer le mot de passe' },
        'pw.debe':             { en: 'It must have:', es: 'Debe cumplir:', fr: 'Elle doit avoir\u00a0:' },
        'pw.regla.largo':      { en: 'At least {n} characters', es: 'Al menos {n} caracteres', fr: 'Au moins {n} caractères' },
        'pw.regla.variedad':   { en: 'At least {n} different characters', es: 'Al menos {n} caracteres distintos', fr: 'Au moins {n} caractères différents' },
        'pw.regla.comun':      { en: 'Not a common password', es: 'Que no sea una contraseña común', fr: 'Pas un mot de passe courant' },
        'pw.regla.igual':      { en: 'Both entries match', es: 'Que las dos coincidan', fr: 'Les deux saisies concordent' },

        // --- Primer acceso con contraseña temporal ------------------------
        'pw.inicial.titulo':   { en: 'Set your own password', es: 'Pon tu propia contraseña', fr: 'Définissez votre mot de passe' },
        'pw.inicial.mensaje':  { en: 'Hi {nombre}. You signed in with a temporary password. Choose your own now: nobody else will know it, and it is the one you will use from here on.', es: 'Hola, {nombre}. Entraste con una contraseña temporal. Pon ahora la tuya: nadie más la sabrá, y es la que usarás a partir de ahora.', fr: 'Bonjour {nombre}. Vous vous êtes connecté avec un mot de passe temporaire. Choisissez le vôtre maintenant : personne d\'autre ne le connaîtra, et c\'est celui que vous utiliserez désormais.' },
        'pw.inicial.temporal': { en: 'Temporary password (the one you just used)', es: 'Contraseña temporal (con la que acabas de entrar)', fr: 'Mot de passe temporaire (celui que vous venez d\'utiliser)' },
        'pw.inicial.luego':    { en: 'Later', es: 'Luego', fr: 'Plus tard' },
        'pw.inicial.noCumple': { en: 'The new password does not meet the requirements below.', es: 'La contraseña nueva no cumple los requisitos de abajo.', fr: 'Le nouveau mot de passe ne respecte pas les exigences ci-dessous.' },
        'pw.inicial.recordatorio': { en: 'You are still on a temporary password. Change it from the banner or from your profile.', es: 'Sigues con una contraseña temporal. Cámbiala desde la franja de arriba o desde tu perfil.', fr: 'Vous utilisez encore un mot de passe temporaire. Changez-le depuis le bandeau ou votre profil.' },
        'pw.inicial.franja':   { en: 'You are using a temporary password. Set your own to keep your account yours.', es: 'Estás usando una contraseña temporal. Pon la tuya para que la cuenta sea sólo tuya.', fr: 'Vous utilisez un mot de passe temporaire. Définissez le vôtre pour que le compte reste le vôtre.' },
        'pw.inicial.ahora':    { en: 'Change it now', es: 'Cambiarla ahora', fr: 'Le changer maintenant' },
        'perfil.cambiarPw':    { en: 'Change password', es: 'Cambiar contraseña', fr: 'Changer le mot de passe' },

        'usuarios.titulo':     { en: 'Users', es: 'Usuarios', fr: 'Utilisateurs' },
        'usuarios.alta':       { en: 'Add user', es: 'Añadir usuario', fr: 'Ajouter un utilisateur' },
        'usuarios.ninguno':    { en: 'No users yet.', es: 'Todavía no hay usuarios.', fr: 'Aucun utilisateur.' },
        'usuarios.col.usuario': { en: 'User', es: 'Usuario', fr: 'Utilisateur' },
        'usuarios.col.rol':     { en: 'Role', es: 'Rol', fr: 'Rôle' },
        'usuarios.col.acceso':  { en: 'Last sign-in', es: 'Último acceso', fr: 'Dernière connexion' },
        'usuarios.col.estado':  { en: 'Status', es: 'Estado', fr: 'Statut' },
        'usuarios.activo':      { en: 'Active', es: 'Activo', fr: 'Actif' },
        'usuarios.baja':        { en: 'Disabled', es: 'De baja', fr: 'Désactivé' },
        'usuarios.resetear':    { en: 'Reset password', es: 'Restablecer contraseña', fr: 'Réinitialiser le mot de passe' },
        'usuarios.darBaja':     { en: 'Disable', es: 'Dar de baja', fr: 'Désactiver' },
        'usuarios.darAlta':     { en: 'Enable', es: 'Dar de alta', fr: 'Activer' },
        'usuarios.noTuRol':     { en: 'You cannot change your own role.', es: 'No puedes cambiarte el rol a ti mismo.', fr: 'Vous ne pouvez pas modifier votre propre rôle.' },
        'usuarios.noTuBaja':    { en: 'You cannot disable yourself.', es: 'No puedes darte de baja a ti mismo.', fr: 'Vous ne pouvez pas vous désactiver.' },
        'usuarios.noTuPw':      { en: 'Change your own password in Details.', es: 'Tu contraseña se cambia en Datos.', fr: 'Changez votre mot de passe dans Informations.' },
        'usuarios.nota':        { en: 'Passwords are never visible: new users get a generated one, shown once, and must change it on first sign-in. Only an admin can reset one.', es: 'Las contraseñas nunca se ven: al alta se genera una, se enseña una vez y hay que cambiarla al primer acceso. Sólo un administrador puede restablecerla.', fr: "Les mots de passe ne sont jamais visibles : à la création, l'un est généré et affiché une fois ; il faut le changer à la première connexion. Seul un administrateur peut le réinitialiser." },
        'usuarios.tu':          { en: '(you)', es: '(tú)', fr: '(vous)' },
        'usuarios.nunca':       { en: 'never', es: 'nunca', fr: 'jamais' },
        'usuarios.acciones':    { en: 'Actions', es: 'Acciones', fr: 'Actions' },
        'usuarios.accionesDe':  { en: 'Actions for {nombre}', es: 'Acciones de {nombre}', fr: 'Actions pour {nombre}' },
        'usuarios.temporal':    { en: 'Temporary', es: 'Temporal', fr: 'Temporaire' },
        'usuarios.temporalAyuda': { en: 'Still on the temporary password set by an admin: has not signed in yet, or has not set their own.', es: 'Sigue con la contraseña temporal que puso un administrador: no ha entrado todavía, o no ha puesto la suya.', fr: "Toujours sur le mot de passe temporaire défini par un administrateur : pas encore connecté, ou n'a pas défini le sien." },
        'usuarios.resetearNota': { en: 'Generates a new one and shows it to you', es: 'Genera una nueva y te la enseña', fr: 'En génère un nouveau et vous le montre' },
        'usuarios.externoNota': { en: 'Just a label: does not change permissions', es: 'Sólo una marca: no cambia permisos', fr: 'Simple étiquette : ne change pas les permissions' },
        'usuarios.darBajaNota': { en: 'They cannot sign in; history is kept', es: 'No podrá entrar; su historial se conserva', fr: 'Ne pourra plus se connecter ; historique conservé' },
        'usuarios.darAltaNota': { en: 'They can sign in again', es: 'Podrá volver a entrar', fr: 'Pourra se reconnecter' },

        'sistema.titulo':   { en: 'System configuration', es: 'Configuración del sistema', fr: 'Configuration du système' },
        'sistema.ajuste':   { en: 'Setting', es: 'Ajuste', fr: 'Paramètre' },
        'sistema.valor':    { en: 'Value', es: 'Valor', fr: 'Valeur' },
        'sistema.sinPoner': { en: 'not set', es: 'sin poner', fr: 'non défini' },
        'sistema.cargando': { en: 'Loading…', es: 'Cargando…', fr: 'Chargement…' },

        // --- Diálogos -----------------------------------------------------
        'dlg.cancelar':  { en: 'Cancel', es: 'Cancelar', fr: 'Annuler' },
        'dlg.confirmar': { en: 'Confirm', es: 'Confirmar', fr: 'Confirmer' },
        'dlg.crear':     { en: 'Create', es: 'Crear', fr: 'Créer' },

        'dlg.salir.titulo':  { en: 'Sign out', es: 'Cerrar sesión', fr: 'Se déconnecter' },
        'dlg.salir.mensaje': { en: 'You will need to sign in again to use the quoter.', es: 'Tendrás que entrar de nuevo para usar el cotizador.', fr: 'Vous devrez vous reconnecter pour utiliser le chiffrage.' },

        'dlg.aprobar.titulo':  { en: 'Approve feasibility', es: 'Aprobar factibilidad', fr: 'Approuver la faisabilité' },
        'dlg.aprobar.mensaje': { en: 'The RFQ will move to quoting.', es: 'La RFQ pasará a cotización.', fr: 'La RFQ passera au chiffrage.' },
        'dlg.aprobar.si':      { en: 'Approve', es: 'Aprobar', fr: 'Approuver' },

        'dlg.rechazar.titulo':  { en: 'Decline RFQ', es: 'Rechazar RFQ', fr: 'Refuser la RFQ' },
        'dlg.rechazar.mensaje': { en: 'A decline email will be sent to the customer, with your note in it. This cannot be undone.', es: 'Se enviará un correo de rechazo al cliente, con tu nota incluida. No se puede deshacer.', fr: 'Un courriel de refus sera envoyé au client, avec votre note. Action irréversible.' },
        'dlg.rechazar.motivo':  { en: 'Note for the customer (goes in the email body and is saved in the notes)', es: 'Nota para el cliente (va en el cuerpo del correo y se guarda en las notas)', fr: 'Note pour le client (dans le corps du courriel et conservée dans les notes)' },
        'dlg.rechazar.ejemplo': { en: 'e.g. wire diameter outside our range', es: 'p. ej. diámetro de alambre fuera de nuestro rango', fr: 'ex. diamètre de fil hors de notre plage' },
        'dlg.devolver.titulo':  { en: 'Send back for review', es: 'Devolver para revisión', fr: 'Renvoyer pour révision' },
        'dlg.devolver.mensaje': { en: 'Nothing is sent to the customer. The RFQ goes back to the review queue with your note.', es: 'No se manda nada al cliente. La RFQ vuelve a la cola de revisión con tu nota.', fr: 'Rien n’est envoyé au client. La RFQ retourne dans la file de révision avec votre note.' },
        'dlg.devolver.motivo':  { en: 'What needs fixing', es: 'Qué hay que corregir', fr: 'Ce qu’il faut corriger' },
        'dlg.devolver.ejemplo': { en: 'e.g. the drawing does not give the number of coils', es: 'p. ej. el plano no da el número de espiras', fr: 'ex. le plan ne donne pas le nombre de spires' },
        'dlg.devolver.si':      { en: 'Send back', es: 'Devolver', fr: 'Renvoyer' },
        'dlg.rechazar.si':      { en: 'Decline and notify', es: 'Rechazar y avisar', fr: 'Refuser et notifier' },

        // --- La ventana de revisión del PM --------------------------------
        'rev.cargando':      { en: 'Loading review…', es: 'Cargando la revisión…', fr: 'Chargement de la revue…' },
        'rev.cerrar':        { en: 'Close', es: 'Cerrar', fr: 'Fermer' },
        'rev.todosTramos':   { en: 'All tiers', es: 'Todos los tramos', fr: 'Tous les paliers' },
        'rev.tramos':        { en: 'Quantity tiers', es: 'Tramos de cantidad', fr: 'Paliers de quantité' },
        'rev.material':      { en: 'Material', es: 'Material', fr: 'Matière' },
        'rfqEstado.New':            { en: 'New', es: 'Nuevo', fr: 'Nouveau' },
        'rfqEstado.RequiresReview': { en: 'Requires review', es: 'En revisión', fr: 'À réviser' },
        'rfqEstado.Approved':       { en: 'Approved', es: 'Aprobado', fr: 'Approuvé' },
        'rfqEstado.Declined':       { en: 'Declined', es: 'Rechazado', fr: 'Refusé' },
        'rfqEstado.Incomplete':     { en: 'Waiting on customer', es: 'Esperando al cliente', fr: 'En attente du client' },
        'rev.cotizacion':    { en: 'Quote {n}', es: 'Cotización {n}', fr: 'Devis {n}' },
        'rev.tramo':         { en: 'Tier {n}', es: 'Tramo {n}', fr: 'Palier {n}' },
        'rev.pzas':          { en: 'pcs', es: 'pzas', fr: 'pcs' },
        'rev.pza':           { en: 'pc', es: 'pza', fr: 'pc' },
        'rev.cascada':       { en: 'Margin waterfall', es: 'Cascada de margen', fr: 'Cascade de marge' },
        'rev.porPieza':      { en: 'Per piece', es: 'Por pieza', fr: 'Par pièce' },
        'rev.maquinaH':      { en: 'machine h', es: 'h máquina', fr: 'h machine' },
        'rev.ccvHora':       { en: 'C/CV per h', es: 'C/CV por h', fr: 'C/CV par h' },
        'rev.ccvHoraLargo':  { en: 'C/CV per machine hour', es: 'C/CV por hora máquina', fr: 'C/CV par heure machine' },
        'rev.pdfError':      { en: 'Could not generate the PDF', es: 'Error al generar el PDF', fr: 'Impossible de générer le PDF' },
        'ficha.esperaTitulo': { en: 'Waiting on the customer', es: 'Esperando al cliente', fr: 'En attente du client' },
        'ficha.esperaTexto':  { en: 'The request came in incomplete. We emailed the buyer asking for what is missing; it goes to review as soon as they reply with everything.', es: 'La petición llegó incompleta. Se le escribió al comprador pidiendo lo que falta; pasa a revisión en cuanto conteste con todo.', fr: 'La demande est arrivée incomplète. Nous avons écrit à l’acheteur pour demander ce qui manque ; elle passe en revue dès qu’il répond avec tout.' },
        'ficha.esperaFalta':  { en: 'Missing: {campos}', es: 'Falta: {campos}', fr: 'Manque : {campos}' },
        'ficha.cotizar':     { en: 'Quote →', es: 'Cotizar →', fr: 'Chiffrer →' },
        'quoting.tab.quote': { en: 'Quote', es: 'Cotización', fr: 'Devis' },
        'quoting.tab.spring':{ en: 'Spring Calc', es: 'Calc. de resortes', fr: 'Calc. ressorts' },
        'tema.cambiarA.light': { en: 'Switch to light mode', es: 'Cambiar a modo claro', fr: 'Passer en mode clair' },
        'tema.cambiarA.dark':  { en: 'Switch to dark mode', es: 'Cambiar a modo oscuro', fr: 'Passer en mode sombre' },
        'rev.pm.cotizado':   { en: 'Quoted by the PM', es: 'Cotizado por el PM', fr: 'Chiffré par le PM' },
        'rev.ver.boton':     { en: 'Versions ({n})', es: 'Versiones ({n})', fr: 'Versions ({n})' },
        'rev.ver.titulo':    { en: 'PM quote versions', es: 'Versiones de la cotización del PM', fr: 'Versions du devis du PM' },
        'rev.ver.nota':      { en: 'Each time the PM comes back from the full calculator a version is kept. The one in use is what this window and the offer show; the calculator opens with it too.', es: 'Cada vez que el PM vuelve de la calculadora completa se guarda una versión. La que está en uso es la que enseña esta ventana y la que lleva la oferta; la calculadora también se abre con ella.', fr: 'Chaque retour du PM depuis la calculatrice complète garde une version. Celle en usage est celle de cette fenêtre et de l’offre ; la calculatrice s’ouvre aussi avec elle.' },
        'rev.ver.usar':      { en: 'Use this one', es: 'Usar esta', fr: 'Utiliser celle-ci' },
        'rev.ver.enUso':     { en: 'In use', es: 'En uso', fr: 'En usage' },
        'rev.ver.enCurso':   { en: 'being edited', es: 'en curso', fr: 'en cours' },
        'rev.ver.sistema':   { en: 'System costing', es: 'Cálculo del sistema', fr: 'Chiffrage du système' },
        'rev.ver.sistemaAyuda': { en: 'what Pohua costed from the email and the drawing', es: 'lo que Pohua costeó con el correo y el plano', fr: 'ce que Pohua a chiffré à partir du courriel et du plan' },
        'rev.ver.usando':    { en: 'Using version {n}. The calculator will open with it.', es: 'Usando la versión {n}. La calculadora se abrirá con ella.', fr: 'Version {n} utilisée. La calculatrice s’ouvrira avec elle.' },
        'rev.ver.usandoSistema': { en: 'Back to the system costing. The PM versions are kept.', es: 'De vuelta al cálculo del sistema. Las versiones del PM se conservan.', fr: 'Retour au chiffrage du système. Les versions du PM sont conservées.' },
        'rev.pm.ayuda':      { en: 'These numbers are the ones the PM left in the full calculator; they are what the offer will carry. Recalculating with new dimensions returns to the system costing.', es: 'Estos números son los que el PM dejó en la calculadora completa; son los que llevará la oferta. Recalcular con cotas nuevas vuelve al costeo del sistema.', fr: 'Ces chiffres sont ceux que le PM a laissés dans la calculatrice complète ; ce sont ceux de l’offre. Recalculer avec de nouvelles cotes revient au chiffrage du système.' },
        'rev.peso':          { en: 'Weight', es: 'Peso', fr: 'Poids' },
        'rev.base':          { en: 'Base', es: 'Base', fr: 'Base' },
        'rev.surcharge':     { en: 'Surcharge', es: 'Recargo', fr: 'Surcharge' },
        'rev.margen':        { en: 'margin', es: 'margen', fr: 'marge' },
        'rev.sell':          { en: 'Selling price', es: 'Precio de venta', fr: 'Prix de vente' },
        'rev.resultado':     { en: 'Result', es: 'Resultado', fr: 'Résultat' },
        'rev.objetivo':      { en: 'target', es: 'objetivo', fr: 'cible' },
        'rev.materialTramo': { en: 'Material this tier', es: 'Material en este tramo', fr: 'Matière pour ce palier' },
        'rev.materialPc':    { en: 'Material $/pc', es: 'Material $/pza', fr: 'Matière $/pc' },
        'rev.alambre':       { en: 'Wire to buy', es: 'Alambre a comprar', fr: 'Fil à acheter' },
        'rev.ruta':          { en: 'Route', es: 'Ruta', fr: 'Gamme' },
        'rev.setup':         { en: 'setup', es: 'preparación', fr: 'réglage' },
        'rev.maquina':      { en: 'Machine', es: 'Máquina', fr: 'Machine' },
        'rev.maquinaAyuda': { en: 'The coiler that makes this spring (first operation of the route).', es: 'La bobinadora que fabrica este resorte (primera operación de la ruta).', fr: 'La machine à ressorts qui fabrique cette pièce (première opération de la gamme).' },
        'rev.sinMaquina':   { en: 'none in the catalogue', es: 'ninguna en el catálogo', fr: 'aucune au catalogue' },
        'rev.sinMaquinaNoProducible': { en: 'none — cannot be produced', es: 'ninguna: no se puede producir', fr: 'aucune : non productible' },
        'rev.sinTramosNoProducible':  { en: 'Not priced: no machine in the shop can make this spring, so it cannot be produced.', es: 'Sin costeo: ninguna máquina del taller puede hacer este resorte, así que no se puede producir.', fr: 'Non chiffré : aucune machine de l’atelier ne peut faire ce ressort, il n’est donc pas productible.' },
        'rev.fam.coiler':   { en: 'Coiler', es: 'Bobinadora', fr: 'Enrouleuse' },
        'rev.fam.secundaria': { en: 'Secondary', es: 'Secundaria', fr: 'Secondaire' },
        'rev.sinRuta':       { en: 'No route: the catalogue has no machine for this spring yet.', es: 'Sin ruta: el catálogo aún no tiene máquina para este resorte.', fr: 'Pas de gamme : le catalogue n’a pas encore de machine pour ce ressort.' },
        'rev.totalesTramo':  { en: 'Tier totals', es: 'Totales del tramo', fr: 'Totaux du palier' },
        'rev.ingreso':       { en: 'Revenue', es: 'Ingreso', fr: 'Chiffre d’affaires' },
        'rev.horas':         { en: 'Machine hours', es: 'Horas máquina', fr: 'Heures machine' },
        'rev.porHora':       { en: 'per hour', es: 'por hora', fr: 'par heure' },
        'rev.notas':         { en: 'PM notes', es: 'Notas del PM', fr: 'Notes du PM' },
        'rev.sinTramos':     { en: 'Nothing priced yet for the requested quantities:', es: 'Todavía no hay costeo para las cantidades pedidas:', fr: 'Aucun chiffrage pour les quantités demandées :' },
        'rev.previewPdf':    { en: 'Preview PDF', es: 'Ver PDF', fr: 'Aperçu PDF' },
        'rev.devolver':      { en: 'Send back', es: 'Devolver', fr: 'Renvoyer' },
        'rev.aprobar':       { en: 'Approve', es: 'Aprobar', fr: 'Approuver' },
        'rev.sinDictamen':   { en: 'This is a calculator draft, not an RFQ: there is nothing to approve or decline.', es: 'Esto es un borrador de la calculadora, no una RFQ: no hay nada que aprobar ni declinar.', fr: 'Ceci est un brouillon de la calculatrice, pas une RFQ : il n’y a rien à approuver ni à refuser.' },
        'rev.declinar':      { en: 'Decline', es: 'Rechazar', fr: 'Refuser' },
        'rev.abrirCompleta': { en: 'Open full quote', es: 'Abrir cotización completa', fr: 'Ouvrir le devis complet' },
        'rev.abrirOferta':   { en: 'Open offer', es: 'Abrir la oferta', fr: 'Ouvrir l’offre' },
        'rev.pieNota':       { en: 'Approve and Send back wait on the approval flow; nothing reaches the customer from here except a decline.', es: 'Aprobar y Devolver siguen el flujo de aprobación; desde aquí al cliente sólo le llega un rechazo.', fr: 'Approuver et Renvoyer suivent le flux d’approbation ; seul un refus part au client depuis ici.' },
        'rev.pieCerrado':    { en: 'This RFQ already has a decision.', es: 'Este RFQ ya tiene dictamen.', fr: 'Cette RFQ a déjà une décision.' },
        'rev.pieSoloLectura':{ en: 'Read only: your role cannot decide on RFQs.', es: 'Sólo lectura: tu rol no dictamina RFQs.', fr: 'Lecture seule : votre rôle ne décide pas des RFQ.' },
        'rev.aviso.errorCosteo':      { en: 'Pricing failed:', es: 'El costeo falló:', fr: 'Le chiffrage a échoué :' },
        'rev.aviso.incompleto':       { en: 'Indicative price: the catalogue is missing data for this spring.', es: 'Precio orientativo: al catálogo le faltan datos para este resorte.', fr: 'Prix indicatif : il manque des données au catalogue pour ce ressort.' },
        'rev.aviso.bajoPiso':         { en: 'Selling price is below the floor price.', es: 'El precio de venta queda por debajo del precio piso.', fr: 'Le prix de vente est sous le prix plancher.' },
        'rev.aviso.bajoContribucion': { en: 'Result is below the contribution target.', es: 'El resultado queda por debajo del objetivo de contribución.', fr: 'Le résultat est sous la cible de contribution.' },
        'rev.aviso.scrap':            { en: 'Scrap allowance looks high for this spring.', es: 'El desperdicio previsto es alto para este resorte.', fr: 'Le taux de rebut semble élevé pour ce ressort.' },
        'rev.aviso.moq':              { en: 'Wire MOQ rules the material cost in this tier.', es: 'El mínimo de compra del alambre manda en el material de este tramo.', fr: 'Le minimum d’achat du fil dicte le coût matière de ce palier.' },
        'rev.aviso.campoFalta':       { en: 'Missing from the email: {campo}', es: 'Falta en el correo: {campo}', fr: 'Manque dans le courriel : {campo}' },
        'rev.aviso.devuelto':         { en: 'RFQ sent back with your note.', es: 'RFQ devuelta con tu nota.', fr: 'RFQ renvoyée avec votre note.' },
        'rev.dlg.devolver.titulo':  { en: 'Send back for correction', es: 'Devolver para corregir', fr: 'Renvoyer pour correction' },
        'rev.dlg.devolver.mensaje': { en: 'The RFQ stays in review and the quoting team gets your note. No email goes to the customer.', es: 'El RFQ se queda en revisión y quien cotiza recibe tu nota. No sale correo al cliente.', fr: 'La RFQ reste en revue et l’équipe de chiffrage reçoit votre note. Aucun courriel au client.' },
        'rev.dlg.devolver.nota':    { en: 'What needs to change', es: 'Qué hay que corregir', fr: 'Ce qu’il faut corriger' },
        'rev.dlg.devolver.ejemplo': { en: 'e.g. check the wire diameter against the drawing', es: 'p. ej. revisar el diámetro de alambre contra el plano', fr: 'ex. vérifier le diamètre de fil sur le plan' },
        'rev.tipo.compresion': { en: 'Compression spring', es: 'Resorte de compresión', fr: 'Ressort de compression' },
        'rev.tipo.extension':  { en: 'Extension spring', es: 'Resorte de extensión', fr: 'Ressort de traction' },
        'rev.tipo.torsion':    { en: 'Torsion spring', es: 'Resorte de torsión', fr: 'Ressort de torsion' },
        'rev.abrir':           { en: 'Review', es: 'Revisar', fr: 'Réviser' },

        // --- Los avisos en el teléfono (Web Push) ---------------------------
        'push.consultando':    { en: 'Checking this device…', es: 'Revisando este dispositivo…', fr: 'Vérification de cet appareil…' },
        'push.invitacion':     { en: 'Get these alerts on this device, even with Pohua closed.', es: 'Recibe estos avisos en este dispositivo, aun con Pohua cerrada.', fr: 'Recevez ces alertes sur cet appareil, même Pohua fermée.' },
        'push.activar':        { en: 'Turn on', es: 'Activar', fr: 'Activer' },
        'push.quitar':         { en: 'Turn off', es: 'Quitar', fr: 'Désactiver' },
        'push.enEste':         { en: 'Alerts are on for this device.', es: 'Los avisos están activos en este dispositivo.', fr: 'Les alertes sont actives sur cet appareil.' },
        'push.activado':       { en: 'Alerts on. A test notification is on its way.', es: 'Avisos activados. Va una notificación de prueba.', fr: 'Alertes activées. Une notification de test arrive.' },
        'push.desactivado':    { en: 'Alerts turned off for this device.', es: 'Avisos quitados en este dispositivo.', fr: 'Alertes désactivées sur cet appareil.' },
        'push.permisoNegado':  { en: 'The browser did not grant permission for notifications.', es: 'El navegador no dio permiso para las notificaciones.', fr: 'Le navigateur n’a pas accordé la permission.' },
        'push.bloqueado':      { en: 'Notifications are blocked for Pohua in this browser. Allow them in the site settings.', es: 'Las notificaciones están bloqueadas para Pohua en este navegador. Permítelas en los ajustes del sitio.', fr: 'Les notifications sont bloquées pour Pohua dans ce navigateur. Autorisez-les dans les réglages du site.' },
        'push.servidorApagado':{ en: 'Push alerts are not set up on the server yet (VAPID keys).', es: 'Los avisos push aún no están configurados en el servidor (claves VAPID).', fr: 'Les alertes push ne sont pas encore configurées sur le serveur (clés VAPID).' },
        'push.noSoportado':    { en: 'This browser cannot show push alerts.', es: 'Este navegador no puede mostrar avisos push.', fr: 'Ce navigateur ne peut pas afficher d’alertes push.' },
        'push.iosInstalar':    { en: 'On iPhone, add Pohua to the Home Screen (Share → Add to Home Screen) to get alerts.', es: 'En iPhone, añade Pohua a la pantalla de inicio (Compartir → Añadir a inicio) para recibir avisos.', fr: 'Sur iPhone, ajoutez Pohua à l’écran d’accueil (Partager → Sur l’écran d’accueil) pour recevoir les alertes.' },
        'push.sinSw':          { en: 'Alerts need the installed app (HTTPS): not available on localhost.', es: 'Los avisos necesitan la app publicada (HTTPS): no están disponibles en localhost.', fr: 'Les alertes nécessitent l’app publiée (HTTPS) : indisponibles sur localhost.' },
        // El sonido de los avisos (js/sonido.js), al pie de la campana.
        'sonido.activo':       { en: 'New alerts play a sound on this device.', es: 'Los avisos nuevos suenan en este equipo.', fr: 'Les nouvelles alertes émettent un son sur cet appareil.' },
        'sonido.apagado':      { en: 'Alerts are silent on this device.', es: 'Los avisos están en silencio en este equipo.', fr: 'Les alertes sont muettes sur cet appareil.' },
        'sonido.encender':     { en: 'Turn sound on', es: 'Activar sonido', fr: 'Activer le son' },
        'sonido.apagar':       { en: 'Mute', es: 'Silenciar', fr: 'Couper le son' },
        'sonido.probar':       { en: 'Test', es: 'Probar', fr: 'Tester' },
        'sonido.probarTitulo': { en: 'Play the alert sound now', es: 'Escuchar ahora el tono de los avisos', fr: 'Écouter le son des alertes' },

        'push.error':          { en: 'Could not set up alerts:', es: 'No se pudieron activar los avisos:', fr: 'Impossible d’activer les alertes :' },

        // --- La oferta al cliente (pantalla Quote) --------------------------
        'oferta.cargando':     { en: 'Preparing the offer…', es: 'Preparando la oferta…', fr: 'Préparation de l’offre…' },
        'oferta.volver':       { en: 'Back', es: 'Volver', fr: 'Retour' },
        'oferta.titulo':       { en: 'Offer', es: 'Oferta', fr: 'Offre' },
        'oferta.verPdf':       { en: 'View PDF', es: 'Ver PDF', fr: 'Voir le PDF' },
        'oferta.enviar':       { en: 'Send offer', es: 'Enviar oferta', fr: 'Envoyer l’offre' },
        'oferta.envioApagado': { en: 'Sending is off (ENVIO_MANUAL): the PDF is generated and the email is built and logged, but nothing reaches the customer.', es: 'El envío está apagado (ENVIO_MANUAL): el PDF se genera y el correo se construye y se registra, pero al cliente no le llega nada.', fr: 'L’envoi est désactivé (ENVIO_MANUAL) : le PDF est généré et le courriel construit et journalisé, mais rien ne part au client.' },
        'oferta.pendiente':    { en: 'Before sending', es: 'Antes de mandarla', fr: 'Avant l’envoi' },
        'oferta.yaEnviada':    { en: 'Offer already sent to', es: 'Oferta ya enviada a', fr: 'Offre déjà envoyée à' },
        'oferta.yaGenerada':   { en: 'Offer already generated (not sent) for', es: 'Oferta ya generada (sin enviar) para', fr: 'Offre déjà générée (non envoyée) pour' },
        'oferta.sinTramos':    { en: 'No priced tiers yet: the catalogue is missing data for this spring.', es: 'Todavía no hay tramos costeados: al catálogo le faltan datos para este resorte.', fr: 'Aucun palier chiffré : il manque des données au catalogue pour ce ressort.' },
        'oferta.pieza':        { en: 'piece', es: 'pieza', fr: 'pièce' },
        'oferta.lote':         { en: 'batch', es: 'lote', fr: 'lot' },
        'oferta.laPieza':      { en: 'The part', es: 'La pieza', fr: 'La pièce' },
        'oferta.correo':       { en: 'Email to the customer', es: 'Correo al cliente', fr: 'Courriel au client' },
        'oferta.para':         { en: 'To', es: 'Para', fr: 'À' },
        'oferta.asunto':       { en: 'Subject', es: 'Asunto', fr: 'Objet' },
        'oferta.proyecto':     { en: 'Project', es: 'Proyecto', fr: 'Projet' },
        'oferta.plazo':        { en: 'Lead time', es: 'Plazo de entrega', fr: 'Délai' },
        'oferta.validez':      { en: 'Offer validity', es: 'Validez de la oferta', fr: 'Validité de l’offre' },
        'oferta.validezDias':  { en: 'Validity (days)', es: 'Validez (días)', fr: 'Validité (jours)' },
        'oferta.terminos':     { en: 'Payment terms', es: 'Condiciones de pago', fr: 'Conditions de paiement' },
        'oferta.descripcion':  { en: 'Description', es: 'Descripción', fr: 'Description' },
        'oferta.material':     { en: 'Material', es: 'Material', fr: 'Matière' },
        'oferta.observaciones':{ en: 'Remarks', es: 'Observaciones', fr: 'Remarques' },
        'oferta.comentarios':  { en: 'Remarks for the PDF (optional)', es: 'Observaciones para el PDF (opcional)', fr: 'Remarques pour le PDF (facultatif)' },
        'oferta.comentariosEj':{ en: 'e.g. tooling included; first article on request', es: 'p. ej. herramental incluido; primera muestra bajo pedido', fr: 'ex. outillage inclus ; première pièce sur demande' },
        'oferta.nota':         { en: 'Prices are the tiers the Plant Manager approved, priced with the Neon catalogue at this moment. The PDF is the ISC quotation format.', es: 'Los precios son los tramos que aprobó el Plant Manager, costeados con el catálogo de Neon en este momento. El PDF es el formato de cotización de ISC.', fr: 'Les prix sont les paliers approuvés par le Plant Manager, chiffrés avec le catalogue Neon à cet instant. Le PDF est le format de devis ISC.' },
        'oferta.dlg.titulo':   { en: 'Send the offer to the customer', es: 'Mandar la oferta al cliente', fr: 'Envoyer l’offre au client' },
        'oferta.dlg.mensaje':  { en: 'The quotation PDF will be attached and the email sent right away.', es: 'Se adjunta el PDF de cotización y el correo sale ahora mismo.', fr: 'Le PDF du devis sera joint et le courriel envoyé immédiatement.' },
        'oferta.dlg.mensajeApagado': { en: 'Outgoing mail is off: the PDF and the email will be generated and logged, but not sent.', es: 'El envío está apagado: el PDF y el correo se generan y se registran, pero no salen.', fr: 'L’envoi est désactivé : le PDF et le courriel seront générés et journalisés, mais pas envoyés.' },
        'oferta.dlg.forzarTitulo':   { en: 'Send with an indicative price?', es: '¿Mandar con precio orientativo?', fr: 'Envoyer avec un prix indicatif ?' },
        'oferta.dlg.forzarMensaje':  { en: 'The catalogue is missing data, so the price is not fully backed. Send anyway?', es: 'Al catálogo le faltan datos, así que el precio no está del todo respaldado. ¿Mandarla igualmente?', fr: 'Il manque des données au catalogue : le prix n’est pas entièrement fondé. Envoyer quand même ?' },
        'oferta.dlg.forzarSi':       { en: 'Send anyway', es: 'Mandar igualmente', fr: 'Envoyer quand même' },
        'oferta.aviso.enviada':      { en: 'Offer sent to the customer.', es: 'Oferta enviada al cliente.', fr: 'Offre envoyée au client.' },
        'oferta.aviso.generada':     { en: 'Offer generated and logged (mail is off, nothing was sent).', es: 'Oferta generada y registrada (el envío está apagado: no salió nada).', fr: 'Offre générée et journalisée (envoi désactivé : rien n’est parti).' },

        'dlg.foto.titulo':  { en: 'Remove photo', es: 'Quitar foto', fr: 'Supprimer la photo' },
        'dlg.foto.mensaje': { en: 'Your initials will be shown instead.', es: 'En su lugar se mostrarán tus iniciales.', fr: 'Vos initiales seront affichées à la place.' },
        'dlg.foto.si':      { en: 'Remove', es: 'Quitar', fr: 'Supprimer' },

        'dlg.alta.titulo':  { en: 'Add user', es: 'Añadir usuario', fr: 'Ajouter un utilisateur' },
        'dlg.alta.mensaje': { en: 'The initial password is generated for you and shown once after creating the user. The person changes it on their first sign-in.', es: 'La contraseña inicial se genera sola y se enseña una vez al crear el usuario. La persona la cambia en su primer inicio de sesión.', fr: 'Le mot de passe initial est généré automatiquement et affiché une fois à la création. La personne le change à sa première connexion.' },
        'dlg.alta.pwTemp':  { en: 'Temporary password', es: 'Contraseña temporal', fr: 'Mot de passe temporaire' },
        'dlg.alta.nombre':  { en: 'First name', es: 'Nombre', fr: 'Prénom' },
        'dlg.alta.apellido': { en: 'Last name', es: 'Apellido', fr: 'Nom' },
        'dlg.alta.si':      { en: 'Create user', es: 'Crear usuario', fr: "Créer l'utilisateur" },

        'dlg.rol.titulo':  { en: 'Change role', es: 'Cambiar rol', fr: 'Changer de rôle' },
        'dlg.rol.mensaje': { en: '{nombre} will become "{rol}". This changes what they can do as soon as they sign in again.', es: '{nombre} pasará a "{rol}". Eso cambia lo que puede hacer en cuanto vuelva a entrar.', fr: '{nombre} deviendra « {rol} ». Cela change ses droits dès sa prochaine connexion.' },
        'dlg.rol.si':      { en: 'Change role', es: 'Cambiar rol', fr: 'Changer' },

        'dlg.baja.titulo':   { en: 'Disable user', es: 'Dar de baja', fr: "Désactiver l'utilisateur" },
        'dlg.baja.mensaje':  { en: '{nombre} will no longer be able to sign in. Their past RFQ decisions are kept.', es: '{nombre} ya no podrá entrar. Sus dictámenes anteriores se conservan.', fr: '{nombre} ne pourra plus se connecter. Ses décisions passées sont conservées.' },
        'dlg.alta2.titulo':  { en: 'Enable user', es: 'Dar de alta', fr: "Activer l'utilisateur" },
        'dlg.alta2.mensaje': { en: '{nombre} will be able to sign in again.', es: '{nombre} podrá volver a entrar.', fr: '{nombre} pourra se reconnecter.' },

        'dlg.reset.titulo':  { en: 'Reset password', es: 'Restablecer contraseña', fr: 'Réinitialiser le mot de passe' },
        'dlg.reset.mensaje': { en: 'A new temporary password will be generated for {nombre}; their current one stops working right away. You will see it once, to copy it or send it to their phone. They must change it when they sign in.', es: 'Se generará una contraseña temporal nueva para {nombre}; la actual deja de valer al momento. La verás una vez, para copiarla o mandársela al teléfono. Tendrá que cambiarla al entrar.', fr: 'Un nouveau mot de passe temporaire sera généré pour {nombre} ; l\'actuel cesse de fonctionner immédiatement. Vous le verrez une fois, pour le copier ou l\'envoyer sur son téléphone. La personne devra le changer à la connexion.' },
        'dlg.reset.si':      { en: 'Generate new password', es: 'Generar contraseña nueva', fr: 'Générer un nouveau mot de passe' },
        'dlg.reset.notificar': { en: "Also send it to {nombre}'s phone", es: 'Mandársela también al teléfono de {nombre}', fr: "L'envoyer aussi sur le téléphone de {nombre}" },
        'dlg.reset.notificarNota': { en: 'As a Pohua notification, only on devices where they turned notifications on. Encrypted end to end.', es: 'Como notificación de Pohua, sólo en los dispositivos donde activó los avisos. Cifrada de punta a punta.', fr: 'En notification Pohua, uniquement sur les appareils où elle a activé les alertes. Chiffrée de bout en bout.' },

        'dlg.temporal.titulo':  { en: 'Temporary password for {nombre}', es: 'Contraseña temporal de {nombre}', fr: 'Mot de passe temporaire de {nombre}' },
        'dlg.temporal.mensaje': { en: 'This is the only time it is shown: it is not stored anywhere readable. {nombre} signs in with it and is asked to set their own right away.', es: 'Es la única vez que se enseña: no se guarda en ningún sitio legible. {nombre} entra con ella y se le pide poner la suya al momento.', fr: "C'est la seule fois où il s'affiche : il n'est stocké nulle part en clair. {nombre} se connecte avec et doit aussitôt définir le sien." },
        'dlg.temporal.copiar':  { en: 'Copy', es: 'Copiar', fr: 'Copier' },
        'dlg.temporal.copiada': { en: 'Password copied.', es: 'Contraseña copiada.', fr: 'Mot de passe copié.' },
        'dlg.temporal.noCopiada': { en: 'Could not copy: select it and copy by hand.', es: 'No se pudo copiar: selecciónala y cópiala a mano.', fr: 'Impossible de copier : sélectionnez-le et copiez-le à la main.' },
        'dlg.temporal.notificar': { en: 'Send to their phone', es: 'Mandar a su teléfono', fr: 'Envoyer sur son téléphone' },
        'dlg.temporal.listo':   { en: 'Done', es: 'Listo', fr: 'Terminé' },
        'dlg.temporal.enPersona': { en: 'Give it to them in person, or send it to their phone if they already turned Pohua notifications on there.', es: 'Dásela en persona, o mándasela al teléfono si ya activó ahí los avisos de Pohua.', fr: "Remettez-le en personne, ou envoyez-le sur son téléphone si les alertes Pohua y sont déjà activées." },
        'dlg.temporal.sinDispositivos': { en: '{nombre} has no device with Pohua notifications turned on: give it to them in person.', es: '{nombre} no tiene ningún dispositivo con los avisos de Pohua activados: dásela en persona.', fr: "{nombre} n'a aucun appareil avec les alertes Pohua activées : remettez-le en personne." },
        'dlg.temporal.enviada': { en: 'Sent to {n} of {total} device(s).', es: 'Enviada a {n} de {total} dispositivo(s).', fr: 'Envoyé à {n} appareil(s) sur {total}.' },
        'dlg.temporal.noLlego': { en: 'Could not deliver it to any of their {total} device(s). Try again or give it in person.', es: 'No se pudo entregar en ninguno de sus {total} dispositivo(s). Vuelve a intentarlo o dásela en persona.', fr: "Impossible de la livrer sur ses {total} appareil(s). Réessayez ou remettez-le en personne." },

        // --- Avisos --------------------------------------------------------
        'aviso.bienvenida':     { en: 'Welcome, {nombre}.', es: 'Te damos la bienvenida, {nombre}.', fr: 'Bienvenue, {nombre}.' },
        'aviso.sesionCerrada':  { en: 'Signed out.', es: 'Sesión cerrada.', fr: 'Déconnecté.' },
        'aviso.sesionExpirada': { en: 'Your session expired. Please sign in again.', es: 'Tu sesión expiró. Entra de nuevo.', fr: 'Votre session a expiré. Reconnectez-vous.' },
        'aviso.cicloEnMarcha':  { en: 'Running detection cycle…', es: 'Ejecutando ciclo de detección…', fr: 'Cycle de détection en cours…' },
        'aviso.cicloHecho':     { en: 'Cycle complete. {correos} emails, {procesados} processed, {errores} errors.', es: 'Ciclo terminado. {correos} correos, {procesados} procesados, {errores} errores.', fr: 'Cycle terminé. {correos} courriels, {procesados} traités, {errores} erreurs.' },
        'aviso.cicloFallo':     { en: 'Could not run the cycle: {motivo}', es: 'No se pudo ejecutar el ciclo: {motivo}', fr: 'Impossible de lancer le cycle : {motivo}' },
        'aviso.servicioArrancado': { en: 'Service started in the background.', es: 'Servicio arrancado en segundo plano.', fr: 'Service démarré en arrière-plan.' },
        'aviso.servicioDetenido':  { en: 'Service stopped.', es: 'Servicio detenido.', fr: 'Service arrêté.' },
        'aviso.paginaFallo':    { en: 'Could not load the page.', es: 'No se pudo cargar la página.', fr: 'Impossible de charger la page.' },
        'aviso.estadoFallo':    { en: 'Could not load the status: {motivo}', es: 'No se pudo cargar el estado: {motivo}', fr: "Impossible de charger l'état : {motivo}" },
        'aviso.logFallo':       { en: 'Could not read the log: {motivo}', es: 'No se pudo leer el registro: {motivo}', fr: 'Impossible de lire le journal : {motivo}' },
        'aviso.csvHecho':       { en: 'CSV exported.', es: 'CSV exportado.', fr: 'CSV exporté.' },
        'aviso.csvFallo':       { en: 'Could not export: {motivo}', es: 'No se pudo exportar: {motivo}', fr: "Échec de l'export : {motivo}" },
        'aviso.usuariosFallo':  { en: 'Could not load users: {motivo}', es: 'No se pudieron cargar los usuarios: {motivo}', fr: 'Impossible de charger les utilisateurs : {motivo}' },
        'aviso.configFallo':    { en: 'Could not load the configuration: {motivo}', es: 'No se pudo cargar la configuración: {motivo}', fr: 'Impossible de charger la configuration : {motivo}' },
        'aviso.fotoPuesta':     { en: 'Photo updated.', es: 'Foto actualizada.', fr: 'Photo mise à jour.' },
        'aviso.fotoQuitada':    { en: 'Photo removed.', es: 'Foto quitada.', fr: 'Photo supprimée.' },
        'aviso.perfilGuardado': { en: 'Profile updated.', es: 'Perfil actualizado.', fr: 'Profil mis à jour.' },
        'aviso.pwCambiada':     { en: 'Password changed.', es: 'Contraseña cambiada.', fr: 'Mot de passe modifié.' },
        'aviso.pwReseteada':    { en: 'Password reset for {nombre}.', es: 'Contraseña restablecida para {nombre}.', fr: 'Mot de passe réinitialisé pour {nombre}.' },
        'aviso.rolCambiado':    { en: 'Role updated.', es: 'Rol actualizado.', fr: 'Rôle mis à jour.' },
        'aviso.usuarioAlta':    { en: '{nombre} can now sign in.', es: '{nombre} ya puede entrar.', fr: '{nombre} peut maintenant se connecter.' },
        'aviso.usuarioActivado': { en: 'User enabled.', es: 'Usuario dado de alta.', fr: 'Utilisateur activé.' },
        'aviso.usuarioDesactivado': { en: 'User disabled.', es: 'Usuario dado de baja.', fr: 'Utilisateur désactivé.' },
        'aviso.nombreVacio':    { en: 'The name cannot be empty.', es: 'El nombre no puede quedar vacío.', fr: 'Le nom ne peut pas être vide.' },
        'aviso.pwNoCoinciden':  { en: 'The two new passwords do not match.', es: 'Las dos contraseñas nuevas no coinciden.', fr: 'Les deux nouveaux mots de passe ne correspondent pas.' },
        'aviso.pwIgual':        { en: 'The new password is the same as the current one.', es: 'La contraseña nueva es igual que la actual.', fr: "Le nouveau mot de passe est identique à l'actuel." },
        'aviso.sinPermisoRfq':  { en: 'You do not have permission to review RFQs.', es: 'No tienes permiso para dictaminar RFQs.', fr: "Vous n'avez pas le droit de statuer sur les RFQ." },
        'aviso.rfqAprobada':    { en: 'RFQ approved.', es: 'RFQ aprobada.', fr: 'RFQ approuvée.' },
        'aviso.rfqRechazadaAviso':    { en: 'RFQ declined. The customer has been notified.', es: 'RFQ rechazada. Se avisó al cliente.', fr: 'RFQ refusée. Le client a été prévenu.' },
        'aviso.rfqRechazadaSinCorreo':{ en: 'RFQ declined, but the email did NOT go out — the customer has not been told.', es: 'RFQ rechazada, pero el correo NO salió: el cliente no se ha enterado.', fr: 'RFQ refusée, mais le courriel n’est PAS parti : le client n’est pas au courant.' },
        'aviso.rfqDevuelta':          { en: 'RFQ sent back for review.', es: 'RFQ devuelta a revisión.', fr: 'RFQ renvoyée pour révision.' },
        'aviso.motivoHace':           { en: 'Write the reason first: it is saved with the RFQ.', es: 'Escribe antes el motivo: se guarda con la RFQ.', fr: 'Écrivez d’abord le motif : il est conservé avec la RFQ.' },
        'aviso.rfqRechazada':   { en: 'RFQ declined.', es: 'RFQ rechazada.', fr: 'RFQ refusée.' },
        'aviso.rfqListaFallo':  { en: 'Could not load the RFQ list: {motivo}', es: 'No se pudo cargar la lista de RFQs: {motivo}', fr: 'Impossible de charger la liste des RFQ : {motivo}' },
        'aviso.pdfEnObras':     { en: 'PDF generation is under construction.', es: 'La generación de PDF está en construcción.', fr: 'La génération de PDF est en cours de développement.' },

        // --- Imagen no válida / foto ---------------------------------------
        'foto.noEsImagen':  { en: 'That file is not an image.', es: 'Ese fichero no es una imagen.', fr: "Ce fichier n'est pas une image." },
        'foto.demasiado':   { en: 'The image is too large (max 12 MB).', es: 'La imagen pesa demasiado (máximo 12 MB).', fr: "L'image est trop lourde (12 Mo max)." },
        'foto.noSeLee':     { en: 'Could not read the file.', es: 'No se pudo leer el fichero.', fr: 'Impossible de lire le fichier.' },
        'foto.noSeDecodifica': { en: 'That image could not be decoded.', es: 'No se pudo decodificar la imagen.', fr: "L'image n'a pas pu être décodée." },
        'foto.noSeProcesa': { en: 'Could not process the image.', es: 'No se pudo procesar la imagen.', fr: "Impossible de traiter l'image." },

        'aviso.sinPermiso': { en: 'Your role does not have access to that screen.', es: 'Tu rol no tiene acceso a esa pantalla.', fr: "Votre rôle n'a pas accès à cet écran." },

        // --- Usuarios: la marca de externo ----------------------------------
        'usuarios.externo':        { en: 'External', es: 'Externo', fr: 'Externe' },
        'usuarios.externoCasilla': { en: 'External to ISC', es: 'Externo a ISC', fr: 'Externe à ISC' },
        'usuarios.externoAyuda':   { en: 'Marks people from outside ISC. It does not grant or remove any permission: what they can do is decided by their role.', es: 'Marca a quien no es de ISC. No concede ni quita permisos: lo que puede hacer lo decide su rol.', fr: "Marque les personnes extérieures à ISC. N'accorde ni ne retire aucune permission : le rôle décide." },
        'usuarios.marcarExterno':  { en: 'Mark external', es: 'Marcar externo', fr: 'Marquer externe' },
        'usuarios.quitarExterno':  { en: 'Unmark external', es: 'Quitar externo', fr: 'Retirer externe' },
        'aviso.marcadoExterno':    { en: '{nombre} is now marked as external.', es: '{nombre} queda marcado como externo.', fr: '{nombre} est marqué comme externe.' },
        'aviso.desmarcadoExterno': { en: '{nombre} is no longer marked as external.', es: '{nombre} ya no está marcado como externo.', fr: "{nombre} n'est plus marqué comme externe." },

        // --- Resumen --------------------------------------------------------
        'resumen.total':      { en: 'Total RFQs', es: 'RFQs totales', fr: 'RFQ au total' },
        'resumen.semana':     { en: 'Last 7 days', es: 'Últimos 7 días', fr: '7 derniers jours' },
        'resumen.clientes':   { en: 'Customers', es: 'Clientes', fr: 'Clients' },
        'resumen.decididas':     { en: 'Decided RFQs', es: 'RFQ ya dictaminadas', fr: 'RFQ déjà tranchées' },
        'resumen.decididasNota': { en: 'Opens read-only: your working draft is kept and restored', es: 'Se abren en consulta: tu borrador se guarda y se devuelve', fr: 'Ouverture en consultation : votre brouillon est conservé et restauré' },
        'resumen.sinDecididas':  { en: 'Nothing has been approved or declined yet.', es: 'Todavía no se ha aprobado ni declinado nada.', fr: 'Rien n’a encore été approuvé ni refusé.' },
        'resumen.verHoja':       { en: 'Open in the sheet', es: 'Ver en la hoja', fr: 'Ouvrir dans la feuille' },
        'resumen.col.parte':     { en: 'Part number', es: 'Número de parte', fr: 'Référence' },
        'resumen.col.fecha':     { en: 'Date', es: 'Fecha', fr: 'Date' },
        'resumen.col.estado':    { en: 'Outcome', es: 'Resultado', fr: 'Résultat' },
        'quoting.consulta':      { en: 'Viewing {rfq} — already decided. Your working draft is safe and comes back when you leave.', es: 'Estás viendo {rfq}, ya dictaminada. Tu borrador está guardado y vuelve al salir.', fr: 'Vous consultez {rfq}, déjà tranchée. Votre brouillon est conservé et revient à la sortie.' },
        'quoting.volverCalculo': { en: 'Back to my calculation', es: 'Volver a mi cálculo', fr: 'Revenir à mon calcul' },
        'resumen.esperando':  { en: 'Waiting for you', es: 'Esperando revisión', fr: 'En attente' },
        'resumen.espera':     { en: 'Waiting for a decision', es: 'Esperan dictamen', fr: 'En attente de décision' },
        'resumen.nadaEspera': { en: 'Nothing is waiting: every RFQ has a decision.', es: 'No hay nada esperando: todas las RFQ tienen dictamen.', fr: 'Rien en attente : toutes les RFQ ont une décision.' },
        'resumen.criticas':   { en: '{n} critical', es: '{n} críticas', fr: '{n} critiques' },
        'resumen.col.rfq':     { en: 'RFQ', es: 'RFQ', fr: 'RFQ' },
        'resumen.col.cliente': { en: 'Customer', es: 'Cliente', fr: 'Client' },
        'resumen.col.espera':  { en: 'Waiting', es: 'Esperando', fr: 'En attente' },
        'resumen.col.motivo':  { en: 'Reason', es: 'Motivo', fr: 'Motif' },
        'resumen.porEstado':   { en: 'By status', es: 'Por estado', fr: 'Par statut' },
        'resumen.materiales':  { en: 'Most requested materials', es: 'Materiales más pedidos', fr: 'Matériaux les plus demandés' },
        'resumen.sinDatos':    { en: 'No data yet.', es: 'Todavía no hay datos.', fr: 'Pas encore de données.' },
        'resumen.ultima':      { en: 'Last RFQ received:', es: 'Última RFQ recibida:', fr: 'Dernière RFQ reçue :' },
        // Clientes estrella (COT-71): el Top 12 marcado en la base.
        'resumen.estrella':    { en: 'Key accounts', es: 'Clientes estrella', fr: 'Comptes clés' },
        'resumen.estrellaNota':{ en: '{n} marked in the database',
                                 es: '{n} marcados en la base de datos',
                                 fr: '{n} marqués dans la base' },
        'resumen.sinEstrella': { en: 'No customer is marked as a key account yet.',
                                 es: 'Todavía no hay ningún cliente marcado como estrella.',
                                 fr: 'Aucun client marqué comme compte clé.' },
        'resumen.rfqsDe':      { en: '{n} RFQs', es: '{n} RFQs', fr: '{n} RFQ' },
        'resumen.unRfq':       { en: '1 RFQ', es: '1 RFQ', fr: '1 RFQ' },
        'resumen.sinRfq':      { en: 'never', es: 'nunca', fr: 'jamais' },
        'resumen.hoy':         { en: 'today', es: 'hoy', fr: "aujourd'hui" },
        'resumen.haceDias':    { en: '{n}d ago', es: 'hace {n} d', fr: 'il y a {n} j' },
        'resumen.ultimoPedido':{ en: 'Last RFQ', es: 'Última RFQ', fr: 'Dernière RFQ' },
        'resumen.cuota':       { en: '{n} of {t} RFQs', es: '{n} de {t} RFQs', fr: '{n} sur {t} RFQ' },
        'resumen.cuotaVacia':  { en: 'no RFQs yet', es: 'sin RFQs todavía', fr: 'aucune RFQ' },
        'aviso.resumenFallo':  { en: 'Could not load the overview: {motivo}', es: 'No se pudo cargar el resumen: {motivo}', fr: "Impossible de charger l'aperçu : {motivo}" },

        // --- Sistema: estado del esquema ------------------------------------
        'sistema.esquemaAlDia':   { en: 'Database schema up to date ({n} files applied).', es: 'Esquema de la base al día ({n} archivos aplicados).', fr: 'Schéma de la base à jour ({n} fichiers appliqués).' },
        'sistema.esquemaAtrasado': { en: 'The database is behind the code: {n} pending ({archivos}). Screens that need them will fail until the server applies them on its next start.', es: 'La base va por detrás del código: faltan {n} ({archivos}). Las pantallas que dependan de ellos fallarán hasta que el servidor los aplique al arrancar.', fr: "La base est en retard sur le code : {n} en attente ({archivos}). Les écrans concernés échoueront jusqu'à leur application au prochain démarrage." },
        'sistema.esquemaSinLeer': { en: 'Could not read the schema state: {motivo}', es: 'No se pudo leer el estado del esquema: {motivo}', fr: "Impossible de lire l'état du schéma : {motivo}" },

        // --- Notificaciones -------------------------------------------------
        'notif.titulo':     { en: 'Waiting for you', es: 'Esperando tu revisión', fr: 'En attente de vous' },
        'notif.vacio':      { en: 'Nothing waiting for review', es: 'Nada pendiente de revisión', fr: 'Rien en attente' },
        'notif.cargando':   { en: 'Loading...', es: 'Cargando...', fr: 'Chargement...' },
        'notif.pendientes': { en: '{n} waiting', es: '{n} pendientes', fr: '{n} en attente' },
        'notif.dias':       { en: '{n}d waiting', es: '{n} d esperando', fr: '{n} j en attente' },
        // Avisos (COT-77): hechos con fecha, distintos de la cola de espera.
        'notif.avisos':     { en: 'New alerts', es: 'Avisos nuevos', fr: 'Nouvelles alertes' },
        'notif.cola':       { en: 'Still waiting', es: 'Sigue esperando', fr: 'Toujours en attente' },
        'notif.leerTodo':   { en: 'Mark all read', es: 'Marcar todo leído', fr: 'Tout marquer lu' },

        // --- Aviso de instalación (sólo en el móvil) ------------------------
        'instalar.mensaje': { en: 'Add Pohua to your home screen', es: 'Añade Pohua a tu pantalla de inicio', fr: "Ajoutez Pohua à votre écran d'accueil" },
        'instalar.boton':   { en: 'Install', es: 'Instalar', fr: 'Installer' },
        'instalar.como':    { en: 'How?', es: '¿Cómo?', fr: 'Comment ?' },
        'instalar.ios':     { en: 'Tap Share, then "Add to Home Screen".', es: 'Pulsa Compartir y luego "Añadir a pantalla de inicio".', fr: 'Appuyez sur Partager, puis « Sur l\'écran d\'accueil ».' },
        'instalar.hecho':   { en: 'Pohua is now on your home screen.', es: 'Pohua ya está en tu pantalla de inicio.', fr: "Pohua est maintenant sur votre écran d'accueil." },
        'instalar.cerrar':  { en: 'Dismiss', es: 'Cerrar', fr: 'Fermer' },

        // --- Selector de idioma ---------------------------------------------
        'idioma.boton': { en: 'Language', es: 'Idioma', fr: 'Langue' },

        // --- Reloj de las tres casas -----------------------------------------
        'reloj.boton': { en: 'Local time — click to switch city',
                         es: 'Hora local — haz clic para cambiar de ciudad',
                         fr: 'Heure locale — cliquez pour changer de ville' },

        // --- Menú de perfil ---------------------------------------------------
        'menu.abrir':       { en: 'Your account', es: 'Tu cuenta', fr: 'Votre compte' },
        'menu.editar':      { en: 'Edit profile', es: 'Editar perfil', fr: 'Modifier le profil' },
        'menu.password':    { en: 'Change password', es: 'Cambiar contraseña', fr: 'Changer le mot de passe' },
        'menu.usuarios':    { en: 'Users', es: 'Usuarios', fr: 'Utilisateurs' },
        'menu.sistema':     { en: 'System', es: 'Sistema', fr: 'Système' },
        'menu.salir':       { en: 'Sign out', es: 'Cerrar sesión', fr: 'Se déconnecter' },
        'menu.sinSesion':   { en: 'Not signed in', es: 'Sin sesión', fr: 'Non connecté' },
    };

    let actual = POR_DEFECTO;
    const oyentes = [];

    function leerGuardado() {
        try {
            const v = localStorage.getItem(CLAVE);
            return IDIOMAS.some(i => i.codigo === v) ? v : null;
        } catch (err) {
            return null;
        }
    }

    function guardar(codigo) {
        try { localStorage.setItem(CLAVE, codigo); } catch (err) { /* modo privado */ }
    }

    /** El del navegador si lo hablamos; si no, inglés. */
    function delNavegador() {
        const lista = navigator.languages || [navigator.language || ''];
        for (const etiqueta of lista) {
            const base = String(etiqueta).slice(0, 2).toLowerCase();
            if (IDIOMAS.some(i => i.codigo === base)) return base;
        }
        return POR_DEFECTO;
    }

    /**
     * Texto de una clave, con sustitución de {marcadores}.
     *
     * Cae al inglés si falta la traducción, y a la propia clave si falta la
     * entrada entera: un hueco en blanco pasa desapercibido, un 'perfil.foto'
     * en mitad de la pantalla no.
     */
    /** Un estado del RFQ, en el idioma puesto. Lo desconocido, tal cual. */
    function estado(valor) {
        if (valor === null || valor === undefined || valor === '') return '';
        const clave = 'rfqEstado.' + valor;
        return TEXTOS[clave] ? t(clave) : String(valor);
    }

    /** El tipo de resorte ('Compresion', 'compression', 'torsión'…) traducido. */
    /**
     * Por qué espera un RFQ de «Requiere atención» (campana, Resumen, panel).
     * Un aprobado sin oferta dice eso aunque traiga banderas: lo que falta ya
     * no es revisar, es mandar la oferta.
     */
    function motivoPendiente(p) {
        if (!p) return '';
        if (p.motivo === 'oferta') return t('motivo.oferta');
        return p.bandera || t('motivo.' + (p.motivo === 'validacion' ? 'validacion' : 'revision'));
    }

    function tipoResorte(valor) {
        if (!valor) return '';
        const base = String(valor).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
        const mapa = { compression: 'compresion', compresion: 'compresion',
                       extension: 'extension', tension: 'extension', traccion: 'extension',
                       torsion: 'torsion' };
        const codigo = mapa[base] || base;
        const clave = 'rev.tipo.' + codigo;
        return TEXTOS[clave] ? t(clave) : String(valor);
    }

    /** El `locale` de fechas y números del idioma puesto. */
    function locale() {
        return { es: 'es-MX', fr: 'fr-FR', en: 'en-US' }[actual] || 'en-US';
    }

    function t(clave, vars) {
        const entrada = TEXTOS[clave];
        if (!entrada) return clave;
        let texto = entrada[actual] || entrada[POR_DEFECTO] || clave;
        if (vars) {
            for (const k of Object.keys(vars)) {
                texto = texto.split('{' + k + '}').join(String(vars[k]));
            }
        }
        return texto;
    }

    /**
     * Traduce el HTML estático.
     *
     *   data-i18n            → textContent
     *   data-i18n-ph         → placeholder
     *   data-i18n-titulo     → title y aria-label
     */
    function aplicar(raiz = document) {
        raiz.querySelectorAll('[data-i18n]').forEach(el => {
            el.textContent = t(el.dataset.i18n);
        });
        raiz.querySelectorAll('[data-i18n-ph]').forEach(el => {
            el.setAttribute('placeholder', t(el.dataset.i18nPh));
        });
        raiz.querySelectorAll('[data-i18n-titulo]').forEach(el => {
            const texto = t(el.dataset.i18nTitulo);
            el.setAttribute('title', texto);
            el.setAttribute('aria-label', texto);
        });
    }

    function fijar(codigo, { guardarlo = true } = {}) {
        if (!IDIOMAS.some(i => i.codigo === codigo)) return;
        actual = codigo;
        // lang en <html>: no es decorativo. De él dependen la separación
        // silábica, las comillas tipográficas y qué voz usa un lector de
        // pantalla al leer la página.
        document.documentElement.setAttribute('lang', codigo);
        if (guardarlo) guardar(codigo);
        aplicar();
        oyentes.forEach(fn => {
            try { fn(codigo); } catch (err) { console.error('Oyente de idioma:', err); }
        });
    }

    /** Registra algo que hay que repintar al cambiar de idioma. */
    function alCambiar(fn) {
        if (typeof fn === 'function') oyentes.push(fn);
    }

    /**
     * Arranque.
     *
     * La primera vez no hay nada guardado y se mira el idioma del navegador;
     * pero ese idioma se GUARDA en el momento, y a partir de ahí manda lo
     * guardado. Es decir: el idioma que se ve en la portada es el que se queda,
     * y sólo cambia si alguien lo cambia con el selector.
     *
     * Antes el idioma del navegador se usaba sin guardarlo, así que no había
     * ninguna elección fijada: bastaba con que cambiara el idioma del teléfono
     * —o abrir la aplicación desde otro navegador— para que el cotizador
     * apareciera en otro idioma sin que nadie hubiera tocado nada.
     */
    function init() {
        const guardado = leerGuardado();
        fijar(guardado || delNavegador(), { guardarlo: !guardado });
    }

    /**
     * Un motivo que llegó del servidor, dicho en el idioma puesto.
     *
     * El servidor manda `{codigo, datos, texto|titulo}`: él no sabe en qué
     * idioma está Pohua —y el mismo RFQ lo abren personas distintas—, así que
     * la frase se arma aquí. Si el código no se conoce (una bandera guardada
     * antes de que esto existiera, o una versión más nueva del servidor), se
     * usa la frase que vino: mejor en español que un hueco.
     *
     * `campo` se traduce también, en dos formas: {campo} en minúscula, para
     * meterlo en medio de una frase, y {Campo} para empezarla.
     */
    /** Las piezas de un motivo que viene plano, como lo emite el motor. */
    function _piezasPlanas(m) {
        const fuera = {};
        ['campo', 'valor', 'limite', 'unidad'].forEach((clave) => {
            if (m[clave] !== null && m[clave] !== undefined) fuera[clave] = m[clave];
        });
        return fuera;
    }

    function motivo(prefijo, m) {
        if (!m) return '';
        if (typeof m === 'string') return m;
        const respaldo = m.texto || m.titulo || '';
        if (!m.codigo) return respaldo;

        const clave = prefijo + m.codigo;
        // El mismo motivo llega en DOS formas y las dos pasan por aquí:
        //
        //   * El de `rfq_banderas`, con sus piezas dentro de `datos` (así lo
        //     guarda repository._datos_de_motivo).
        //   * El del motor de factibilidad tal cual, PLANO: `campo`, `valor`
        //     y `limite` colgando del propio motivo.
        //
        // Leer sólo `m.datos` dejaba los segundos sin sustituir, y en la
        // pantalla salía literalmente "{Campo} is missing and is needed to
        // decide" — un hueco donde tenía que ir el nombre de la cota.
        const datos = Object.assign({}, m.datos || _piezasPlanas(m));
        if (datos.campo) {
            const etiqueta = t('campo.' + datos.campo);
            const nombre = etiqueta === 'campo.' + datos.campo
                ? String(datos.campo).replace(/_/g, ' ') : etiqueta;
            datos.campo = nombre;
            datos.Campo = nombre.charAt(0).toUpperCase() + nombre.slice(1);
        }
        if (Array.isArray(datos.limite)) datos.limite = datos.limite.join(', ');
        // Una bandera guardada antes de que la unidad viajara no la trae: se
        // pone vacía para que no salga el hueco "{unidad}" en la frase.
        if (datos.unidad === undefined) datos.unidad = '';
        const texto = t(clave, datos);
        return texto === clave ? respaldo : texto;
    }

    return { t, motivo, aplicar, fijar, alCambiar, init, IDIOMAS, estado, tipoResorte, motivoPendiente,
             get locale() { return locale(); },
             get idioma() { return actual; } };
})();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', I18N.init);
} else {
    I18N.init();
}
