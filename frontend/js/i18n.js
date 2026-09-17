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
 *   - Los datos NO se traducen: nombres de clientes, materiales, estados que
 *     vienen de la base de datos y mensajes del registro se enseñan tal cual.
 *     Traducir un 'RequiresReview' que la base guarda así sólo confundiría al
 *     compararlo con la propia base.
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
        'home.subtitulo': { en: 'Automatic quoting for industrial springs', es: 'Cotización automática de resortes industriales', fr: 'Chiffrage automatique de ressorts industriels' },
        'home.entrar':    { en: 'Sign In', es: 'Entrar', fr: 'Se connecter' },

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

        // --- Monitor -----------------------------------------------------
        'monitor.titulo':    { en: 'Service log', es: 'Registro del servicio', fr: 'Journal du service' },
        'monitor.lineas':    { en: '{n} lines', es: '{n} líneas', fr: '{n} lignes' },
        'monitor.refrescar': { en: 'Refresh now', es: 'Actualizar ahora', fr: 'Actualiser' },
        'monitor.cargando':  { en: 'Loading the log…', es: 'Cargando el registro…', fr: 'Chargement du journal…' },
        'monitor.vacio':     { en: 'The log is empty.', es: 'El registro está vacío.', fr: 'Le journal est vide.' },
        'monitor.sinFichero': { en: 'No log file yet.', es: 'Todavía no hay fichero de registro.', fr: 'Pas encore de fichier journal.' },

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
        'asis.exportar':  { en: 'Export CSV', es: 'Exportar CSV', fr: 'Exporter en CSV' },
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
        'asis.nadaPendiente': { en: 'Nothing waiting. No RFQ is flagged or stuck in review.', es: 'Nada pendiente. Ninguna RFQ marcada ni parada en revisión.', fr: 'Rien en attente. Aucune RFQ signalée ou bloquée.' },
        'asis.esperando': { en: '{n} waiting · {c} with critical flags', es: '{n} pendientes · {c} con banderas críticas', fr: '{n} en attente · {c} avec alertes critiques' },
        'asis.tokens':    { en: '{entrada} in / {salida} out tokens', es: '{entrada} tokens de entrada / {salida} de salida', fr: '{entrada} jetons entrants / {salida} sortants' },
        'asis.col.rfq':      { en: 'RFQ', es: 'RFQ', fr: 'RFQ' },
        'asis.col.cliente':  { en: 'Customer', es: 'Cliente', fr: 'Client' },
        'asis.col.pieza':    { en: 'Part', es: 'Pieza', fr: 'Pièce' },
        'asis.col.estado':   { en: 'State', es: 'Estado', fr: 'État' },
        'asis.col.espera':   { en: 'Waiting', es: 'Esperando', fr: 'En attente' },
        'asis.col.bandera':  { en: 'Flag', es: 'Bandera', fr: 'Alerte' },
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
        'dlg.rechazar.mensaje': { en: 'A decline email will be sent to the customer. This cannot be undone.', es: 'Se enviará un correo de rechazo al cliente. No se puede deshacer.', fr: 'Un courriel de refus sera envoyé au client. Action irréversible.' },
        'dlg.rechazar.motivo':  { en: 'Reason for declining (saved in the notes)', es: 'Motivo del rechazo (se guarda en las notas)', fr: 'Motif du refus (conservé dans les notes)' },
        'dlg.rechazar.ejemplo': { en: 'e.g. wire diameter outside our range', es: 'p. ej. diámetro de alambre fuera de nuestro rango', fr: 'ex. diamètre de fil hors de notre plage' },
        'dlg.rechazar.si':      { en: 'Decline and notify', es: 'Rechazar y avisar', fr: 'Refuser et notifier' },

        // --- La ventana de revisión del PM --------------------------------
        'rev.cargando':      { en: 'Loading review…', es: 'Cargando la revisión…', fr: 'Chargement de la revue…' },
        'rev.cerrar':        { en: 'Close', es: 'Cerrar', fr: 'Fermer' },
        'rev.todosTramos':   { en: 'All tiers', es: 'Todos los tramos', fr: 'Tous les paliers' },
        'rev.tramos':        { en: 'Quantity tiers', es: 'Tramos de cantidad', fr: 'Paliers de quantité' },
        'rev.material':      { en: 'Material', es: 'Material', fr: 'Matière' },
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
        'rev.sinRuta':       { en: 'No route: the catalogue has no machine for this spring yet.', es: 'Sin ruta: el catálogo aún no tiene máquina para este resorte.', fr: 'Pas de gamme : le catalogue n’a pas encore de machine pour ce ressort.' },
        'rev.totalesTramo':  { en: 'Tier totals', es: 'Totales del tramo', fr: 'Totaux du palier' },
        'rev.ingreso':       { en: 'Revenue', es: 'Ingreso', fr: 'Chiffre d’affaires' },
        'rev.horas':         { en: 'Machine hours', es: 'Horas máquina', fr: 'Heures machine' },
        'rev.porHora':       { en: 'per hour', es: 'por hora', fr: 'par heure' },
        'rev.notas':         { en: 'PM notes', es: 'Notas del PM', fr: 'Notes du PM' },
        'rev.sinTramos':     { en: 'Nothing priced yet for the requested quantities:', es: 'Todavía no hay costeo para las cantidades pedidas:', fr: 'Aucun chiffrage pour les quantités demandées :' },
        'rev.devolver':      { en: 'Send back', es: 'Devolver', fr: 'Renvoyer' },
        'rev.aprobar':       { en: 'Approve', es: 'Aprobar', fr: 'Approuver' },
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
        'rev.previewPdf':      { en: 'Preview PDF', es: 'Vista previa PDF', fr: 'Aperçu PDF' },

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
        'push.error':          { en: 'Could not set up alerts:', es: 'No se pudieron activar los avisos:', fr: 'Impossible d’activer les alertes :' },

        // --- La oferta al cliente (pantalla Quote) --------------------------
        'oferta.cargando':     { en: 'Preparing the offer…', es: 'Preparando la oferta…', fr: 'Préparation de l’offre…' },
        'oferta.volver':       { en: 'Back', es: 'Volver', fr: 'Retour' },
        'oferta.titulo':       { en: 'Offer', es: 'Oferta', fr: 'Offre' },
        'oferta.verPdf':       { en: 'View PDF', es: 'Ver PDF', fr: 'Voir le PDF' },
        'oferta.enviar':       { en: 'Send offer', es: 'Enviar oferta', fr: 'Envoyer l’offre' },
        'oferta.envioApagado': { en: 'Outgoing mail is off (ENVIO_AUTOMATICO): the PDF is generated and the email is built and logged, but nothing reaches the customer.', es: 'El envío de correo está apagado (ENVIO_AUTOMATICO): el PDF se genera y el correo se construye y se registra, pero al cliente no le llega nada.', fr: 'L’envoi de courriel est désactivé (ENVIO_AUTOMATICO) : le PDF est généré et le courriel construit et journalisé, mais rien ne part au client.' },
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
        'dlg.alta.mensaje': { en: 'The password is temporary: the person changes it from their own profile.', es: 'La contraseña es temporal: la persona la cambia desde su perfil.', fr: 'Le mot de passe est temporaire : la personne le change depuis son profil.' },
        'dlg.alta.pwTemp':  { en: 'Temporary password', es: 'Contraseña temporal', fr: 'Mot de passe temporaire' },
        'dlg.alta.si':      { en: 'Create user', es: 'Crear usuario', fr: "Créer l'utilisateur" },

        'dlg.rol.titulo':  { en: 'Change role', es: 'Cambiar rol', fr: 'Changer de rôle' },
        'dlg.rol.mensaje': { en: '{nombre} will become "{rol}". This changes what they can do as soon as they sign in again.', es: '{nombre} pasará a "{rol}". Eso cambia lo que puede hacer en cuanto vuelva a entrar.', fr: '{nombre} deviendra « {rol} ». Cela change ses droits dès sa prochaine connexion.' },
        'dlg.rol.si':      { en: 'Change role', es: 'Cambiar rol', fr: 'Changer' },

        'dlg.baja.titulo':   { en: 'Disable user', es: 'Dar de baja', fr: "Désactiver l'utilisateur" },
        'dlg.baja.mensaje':  { en: '{nombre} will no longer be able to sign in. Their past RFQ decisions are kept.', es: '{nombre} ya no podrá entrar. Sus dictámenes anteriores se conservan.', fr: '{nombre} ne pourra plus se connecter. Ses décisions passées sont conservées.' },
        'dlg.alta2.titulo':  { en: 'Enable user', es: 'Dar de alta', fr: "Activer l'utilisateur" },
        'dlg.alta2.mensaje': { en: '{nombre} will be able to sign in again.', es: '{nombre} podrá volver a entrar.', fr: '{nombre} pourra se reconnecter.' },

        'dlg.reset.titulo':  { en: 'Reset password', es: 'Restablecer contraseña', fr: 'Réinitialiser le mot de passe' },
        'dlg.reset.mensaje': { en: 'Set a temporary password for {nombre}. You cannot see their current one — this replaces it. Give it to them in person; they change it from their profile.', es: 'Pon una contraseña temporal para {nombre}. No puedes ver la actual: esta la sustituye. Dásela en persona; la cambiará desde su perfil.', fr: 'Définissez un mot de passe temporaire pour {nombre}. Vous ne voyez pas l\'actuel : celui-ci le remplace. Remettez-le en personne ; la personne le changera depuis son profil.' },
        'dlg.reset.campo':   { en: 'Temporary password (at least 12 characters)', es: 'Contraseña temporal (al menos 12 caracteres)', fr: 'Mot de passe temporaire (au moins 12 caractères)' },
        'dlg.reset.ejemplo': { en: 'e.g. Muelle-Otono-2026', es: 'p. ej. Muelle-Otono-2026', fr: 'ex. Muelle-Otono-2026' },

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
        'resumen.esperando':  { en: 'Waiting for you', es: 'Esperando revisión', fr: 'En attente' },
        'resumen.espera':     { en: 'Waiting for review', es: 'Esperando revisión', fr: 'En attente de revue' },
        'resumen.nadaEspera': { en: 'Nothing is waiting for review.', es: 'No hay nada esperando revisión.', fr: 'Rien en attente de revue.' },
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

        // --- Ventana de aprobación (Revision) --------------------------------
        'rev.cerrar':           { en: 'Close', es: 'Cerrar', fr: 'Fermer' },
        'rev.cargando':         { en: 'Loading...', es: 'Cargando...', fr: 'Chargement...' },
        'rev.todosTramos':      { en: 'All tiers', es: 'Todos los tramos', fr: 'Tous les paliers' },
        'rev.tramos':           { en: 'Tiers', es: 'Tramos', fr: 'Paliers' },
        'rev.sinTramos':        { en: 'No costed tiers yet for quantities', es: 'Sin tramos costeados para las cantidades', fr: 'Aucun palier coûté pour les quantités' },
        'rev.sinRuta':          { en: 'No route defined.', es: 'Sin ruta definida.', fr: 'Aucun itinéraire défini.' },
        'rev.notas':            { en: 'Notes', es: 'Notas', fr: 'Notes' },
        'rev.previewPdf':       { en: 'Preview PDF', es: 'Ver PDF', fr: 'Aperçu PDF' },
        'rev.aprobar':          { en: 'Approve', es: 'Aprobar', fr: 'Approuver' },
        'rev.devolver':         { en: 'Send back', es: 'Devolver', fr: 'Renvoyer' },
        'rev.declinar':         { en: 'Decline', es: 'Declinar', fr: 'Décliner' },
        'rev.abrirCompleta':    { en: 'Open full quote', es: 'Abrir cotización', fr: 'Ouvrir le devis' },
        'rev.abrirOferta':      { en: 'View offer', es: 'Ver oferta', fr: 'Voir l\'offre' },
        'rev.pieNota':          { en: 'Review all tiers before deciding.', es: 'Revisa todos los tramos antes de decidir.', fr: 'Vérifiez tous les paliers avant de décider.' },
        'rev.pieCerrado':       { en: 'This RFQ is already closed.', es: 'Este RFQ ya está cerrado.', fr: 'Cette RFQ est déjà clôturée.' },
        'rev.pieSoloLectura':   { en: 'Read-only view.', es: 'Vista de solo lectura.', fr: 'Vue en lecture seule.' },
        'rev.aviso.errorCosteo':      { en: 'Costing error:', es: 'Error de costeo:', fr: 'Erreur de calcul :' },
        'rev.aviso.incompleto':       { en: 'Costing incomplete — some catalog prices are missing.', es: 'Costeo incompleto — faltan precios en el catálogo.', fr: 'Calcul incomplet — certains prix du catalogue manquent.' },
        'rev.aviso.bajoPiso':         { en: 'Price below floor.', es: 'Precio por debajo del piso.', fr: 'Prix inférieur au plancher.' },
        'rev.aviso.bajoContribucion': { en: 'Margin below target.', es: 'Margen por debajo del objetivo.', fr: 'Marge inférieure à la cible.' },
        'rev.aviso.scrap':            { en: 'High scrap rate.', es: 'Tasa de scrap elevada.', fr: 'Taux de rebut élevé.' },
        'rev.aviso.moq':              { en: 'MOQ applies — buying more wire than needed.', es: 'Aplica MOQ — se compra más alambre del necesario.', fr: 'MOQ appliqué — fil acheté en excès.' },
        'rev.aviso.campoFalta':       { en: 'Missing field: {campo}', es: 'Campo faltante: {campo}', fr: 'Champ manquant : {campo}' },
        'rev.tipo.Compression':       { en: 'Compression spring', es: 'Resorte de compresión', fr: 'Ressort de compression' },
        'rev.tipo.Extension':         { en: 'Extension spring', es: 'Resorte de extensión', fr: 'Ressort de traction' },
        'rev.tipo.Torsion':           { en: 'Torsion spring', es: 'Resorte de torsión', fr: 'Ressort de torsion' },
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

    return { t, aplicar, fijar, alCambiar, init, IDIOMAS,
             get idioma() { return actual; } };
})();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', I18N.init);
} else {
    I18N.init();
}
