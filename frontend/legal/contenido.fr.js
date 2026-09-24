/**
 * Textes juridiques de Pohua, en français (traduction de la version espagnole de référence).
 *
 * Chaque document est une liste de sections ; chaque section, un titre et des blocs :
 * un texte est un paragraphe et une liste est une liste à puces. Les textes
 * peuvent contenir <b> et des liens ; ils sont rédigés par l’équipe, non par les utilisateurs.
 *
 * Marqueurs que la page remplit avec `responsable.js` :
 *   {{responsables}}  la liste des sociétés avec leur adresse
 *   {{correo}}        la boîte de réception dédiée à la protection des données
 *   {{departamento}}  la personne ou le service chargé des données personnelles
 *   {{dpo}}           le délégué à la protection des données (RGPD)
 *   {{jurisdiccion}}  loi applicable et juridiction compétente des conditions d’utilisation
 *   {{version}}       la version des documents
 *
 * CE TEXTE DOIT ÊTRE RELU PAR UN AVOCAT de chaque pays où la société exerce
 * ses activités (Mexique, États-Unis et France) avant d’être considéré comme définitif.
 */
window.POHUA_LEGAL_TEXTOS = window.POHUA_LEGAL_TEXTOS || {};
window.POHUA_LEGAL_TEXTOS.fr = {
    ui: {
        titulo: 'Informations légales',
        privacidad: 'Politique de confidentialité',
        cookies: 'Cookies et stockage',
        terminos: 'Conditions d’utilisation',
        version: 'Version',
        imprimir: 'Imprimer',
        volver: 'Retour à Pohua',
        pendiente: 'à compléter',
        avisoPendiente: 'Ce document contient des informations sur le responsable du traitement qui ne sont pas encore complétées. Il ne sera définitif qu’une fois ces informations renseignées et le document relu par le service juridique.',
        borrarPreferencias: 'Effacer les préférences enregistrées dans ce navigateur',
        borradas: 'C’est fait : les préférences de ce navigateur ont été effacées.',
        tablaNombre: 'Nom',
        tablaTipo: 'Type',
        tablaPara: 'Finalité',
        tablaDura: 'Durée',
    },

    privacidad: {
        titulo: 'Politique de confidentialité',
        intro: 'La présente politique explique quelles données à caractère personnel Pohua (l’outil de chiffrage des demandes de devis, ou RFQ) traite, dans quel but, avec qui elles sont partagées et comment vous pouvez exercer vos droits. Elle est établie conformément à la Ley Federal de Protección de Datos Personales en Posesión de los Particulares (loi fédérale mexicaine sur la protection des données personnelles détenues par les particuliers, LFPDPPP), au Règlement général sur la protection des données de l’Union européenne (RGPD), à la loi française Informatique et Libertés, ainsi qu’aux lois des États-Unis qui seraient applicables.',
        secciones: [
            { t: '1. Responsable du traitement', b: [
                'Les responsables du traitement de vos données personnelles sont les sociétés du groupe suivantes, chacune pour les données qu’elle traite sur son site :',
                '{{responsables}}',
                'Pour toute question relative à la protection des données : {{correo}}. Personne ou service chargé des données personnelles : {{departamento}}. Délégué à la protection des données (UE) : {{dpo}}.',
            ]},
            { t: '2. Personnes concernées', b: [[
                '<b>Utilisateurs de Pohua</b> : membres du personnel de la société et collaborateurs auxquels un compte a été attribué.',
                '<b>Contacts des clients et des fournisseurs</b> : les personnes qui nous adressent une demande de devis par courriel ou dont les coordonnées y figurent, ainsi que celles qui reçoivent nos offres.',
            ]]},
            { t: '3. Données personnelles traitées', b: [
                '<b>Concernant les utilisateurs :</b>',
                [
                    'Identification et coordonnées : nom, adresse électronique professionnelle, fonction ou rôle dans l’application.',
                    'Authentification : le mot de passe, conservé uniquement sous forme d’empreinte chiffrée (PBKDF2) ; il n’est jamais conservé ni visible en clair.',
                    'Photo de profil, uniquement si l’utilisateur choisit de la télécharger.',
                    'Activité : date de la dernière connexion et journal des actions effectuées dans l’application (par exemple, qui a approuvé, refusé ou modifié un devis, et quand).',
                    'Préférences d’affichage (thème, langue, son, horloge) et, si l’utilisateur les active, l’abonnement aux notifications de l’appareil.',
                ],
                '<b>Concernant les contacts des clients et des fournisseurs :</b>',
                [
                    'Nom, fonction, adresse électronique, téléphone, société et adresse de la société.',
                    'Le contenu des courriels de demande et de leurs pièces jointes (plans techniques), les devis et offres émis ainsi que les conditions commerciales convenues.',
                ],
                '<b>Données techniques :</b> les serveurs peuvent enregistrer la date, le chemin demandé et l’adresse IP de chaque accès, à des fins de sécurité et de diagnostic.',
                '<b>Nous ne traitons pas de données sensibles</b> (santé, origine ethnique, convictions, etc.). Nous vous demandons de ne pas en inclure dans les courriels ni dans les plans ; si nous en recevions, elles seraient supprimées.',
            ]},
            { t: '4. Finalités du traitement', b: [
                'Finalités nécessaires à notre relation avec vous :',
                [
                    'Recevoir, enregistrer et traiter les demandes de devis.',
                    'Évaluer la faisabilité technique, calculer les coûts, puis préparer et envoyer les offres.',
                    'Communiquer avec vous au sujet de votre demande, de votre offre et de la commande qui en découle.',
                    'Créer et gérer les comptes utilisateurs, leurs autorisations et leur accès.',
                    'Assurer la sécurité de l’application et tenir un journal indiquant qui a fait quoi, afin de pouvoir auditer les décisions commerciales.',
                    'Respecter les obligations légales, fiscales et commerciales.',
                ],
                '<b>Il n’existe aucune finalité secondaire.</b> Pohua n’utilise pas vos données à des fins de marketing, de publicité, de vente de données ni de profilage.',
            ]},
            { t: '5. Base légale', b: [[
                '<b>Mexique (LFPDPPP) :</b> les traitements ci-dessus sont nécessaires à l’exécution de la relation juridique ou commerciale que vous engagez en demandant un devis ou que vous entretenez avec la société en tant qu’utilisateur ; ils ne requièrent donc pas de consentement (art. 9). Pour le reste, le consentement est tacite si, la présente politique ayant été mise à votre disposition, vous ne manifestez pas d’opposition (art. 7).',
                '<b>Union européenne (RGPD) :</b> exécution d’un contrat ou de mesures précontractuelles prises à la demande de la personne concernée (art. 6.1.b) ; intérêt légitime à gérer la relation commerciale avec les entreprises, à assurer la sécurité et à permettre l’audit (art. 6.1.f) ; respect d’une obligation légale (art. 6.1.c). Pour le personnel, la relation de travail.',
            ]]},
            { t: '6. Recours à l’intelligence artificielle', b: [
                'Pour lire les courriels et les plans techniques et en extraire les caractéristiques de la pièce (matériau, dimensions, quantités), Pohua transmet leur contenu à un modèle d’intelligence artificielle d’un prestataire externe (Anthropic, PBC, États-Unis), qui agit en qualité de sous-traitant et ne traite les données que pour nous fournir ce service, conformément au contrat conclu avec lui.',
                '<b>Aucune décision n’est fondée exclusivement sur un traitement automatisé.</b> La faisabilité, le prix et l’envoi de chaque offre sont examinés et décidés par une personne. Vous pouvez demander que votre demande soit traitée sans recours à ce traitement en écrivant à {{correo}}.',
            ]},
            { t: '7. Destinataires des données', b: [
                'Des <b>prestataires agissant pour notre compte</b> (sous-traitants), uniquement pour nous fournir leur service et sous obligation de confidentialité :',
                [
                    'Hébergement de l’application (Render) et base de données (Neon).',
                    'Messagerie électronique (le fournisseur de la messagerie professionnelle, par ex. Microsoft 365).',
                    'Stockage des plans dans le cloud (Microsoft Azure), lorsqu’il est activé.',
                    'Lecture des courriels et des plans par intelligence artificielle (Anthropic).',
                    'Acheminement des notifications vers le téléphone ou le navigateur (le service de notifications du navigateur lui-même : Google, Apple, Mozilla ou Microsoft), uniquement si l’utilisateur les active.',
                ],
                'Les <b>sociétés du même groupe</b> au Mexique, aux États-Unis et en France, qui appliquent les mêmes procédures et politiques (art. 36, fraction III, de la LFPDPPP).',
                'Les <b>autorités</b>, lorsqu’une loi ou une décision de justice l’exige.',
                '<b>Nous ne vendons ni ne cédons vos données</b> à des tiers pour leurs propres finalités.',
            ]},
            { t: '8. Transferts internationaux', b: [
                'Les serveurs des prestataires ci-dessus sont principalement situés aux États-Unis, et les données circulent entre les sites du Mexique, des États-Unis et de France. Lorsqu’elles sont transférées hors de l’Union européenne, elles sont protégées, selon le cas, par les clauses contractuelles types adoptées par la Commission européenne ou par l’adhésion du prestataire au Data Privacy Framework UE–États-Unis. Vous pouvez obtenir une copie de ces garanties en écrivant à {{correo}}.',
            ]},
            { t: '9. Durée de conservation', b: [[
                'Comptes utilisateurs : tant que le compte est actif ; ensuite, il est désactivé et le journal d’activité est conservé pendant la durée exigée par la loi ou nécessaire à la défense de droits en justice.',
                'Demandes, plans, devis et offres : pendant toute la durée de la relation commerciale puis pendant les durées de conservation imposées par la législation fiscale et commerciale (au Mexique, en général cinq ans).',
                'Journaux techniques du serveur : pendant la durée de conservation appliquée par l’hébergeur à des fins de sécurité et de diagnostic.',
                'À l’issue de cette durée, les données sont verrouillées puis supprimées de manière sécurisée.',
            ]]},
            { t: '10. Vos droits', b: [
                'Vous pouvez, à tout moment et gratuitement :',
                [
                    '<b>Accéder</b> à vos données, les <b>rectifier</b> si elles sont inexactes, en demander l’<b>annulation</b> ou vous <b>opposer</b> à leur traitement (droits « ARCO », Mexique).',
                    'Dans l’Union européenne, en outre : demander l’<b>effacement</b> de vos données, la <b>limitation</b> du traitement et la <b>portabilité</b> de vos données, et définir des directives relatives au sort de vos données après votre décès (France).',
                    '<b>Retirer</b> le consentement que vous avez donné, sans effet rétroactif, et <b>limiter</b> l’utilisation ou la divulgation de vos données.',
                ],
                '<b>Comment :</b> adressez un courriel à {{correo}} en indiquant votre nom, un moyen de vous répondre, un document justifiant de votre identité (ou de celle de votre représentant), une description claire de votre demande et, s’il s’agit d’une rectification, la donnée correcte.',
                '<b>Délais :</b> au Mexique, nous vous communiquerons notre réponse dans un délai maximal de 20 jours et, si la demande est fondée, nous y donnerons suite dans les 15 jours suivants (art. 31 de la LFPDPPP). Dans l’Union européenne, dans un délai d’un mois, prolongeable de deux mois pour les demandes complexes (art. 12 du RGPD).',
                '<b>Si vous n’êtes pas satisfait</b>, vous pouvez saisir l’autorité compétente : au Mexique, la Secretaría Anticorrupción y Buen Gobierno (ministère mexicain de la Lutte contre la corruption et de la Bonne gouvernance) ; en France, introduire une réclamation auprès de la CNIL (cnil.fr) ; ou vous adresser à l’autorité de protection des données de votre pays de résidence dans l’UE. Si vous résidez dans un État des États-Unis doté d’une loi applicable en matière de protection de la vie privée, vous bénéficiez des droits que cette loi vous confère.',
            ]},
            { t: '11. Sécurité', b: [
                'Nous mettons en œuvre des mesures administratives, techniques et physiques pour protéger vos données : connexion chiffrée (HTTPS), mots de passe conservés uniquement sous forme d’empreinte chiffrée, sessions à expiration automatique, accès fondé sur les rôles et les autorisations, et journalisation des actions. En cas de violation de données susceptible d’affecter de manière significative vos droits, nous vous en informerons dans les meilleurs délais et le notifierons à l’autorité lorsque la loi l’exige.',
            ]},
            { t: '12. Cookies et stockage dans le navigateur', b: [
                'Pohua utilise uniquement un cookie technique et un stockage local nécessaires à son fonctionnement et à la mémorisation des préférences choisies par l’utilisateur lui-même. Il n’utilise aucun cookie publicitaire, de mesure d’audience ou tiers. Le détail, et la manière de les supprimer, figurent dans la <a href="?doc=cookies">politique relative aux cookies et au stockage</a>.',
            ]},
            { t: '13. Mineurs', b: [
                'Pohua est un outil à usage professionnel et ne s’adresse pas aux mineurs. Nous ne traitons pas sciemment de données concernant des mineurs.',
            ]},
            { t: '14. Modifications de la présente politique', b: [
                'Toute modification sera publiée sur cette même page, avec une nouvelle version et une nouvelle date. Si la modification porte sur les données traitées ou sur leurs finalités, Pohua demandera à chaque utilisateur de la lire et de l’accepter à nouveau lors de sa connexion.',
                'Version {{version}}.',
            ]},
        ],
    },

    cookies: {
        titulo: 'Politique relative aux cookies et au stockage local',
        intro: 'La présente politique explique ce que Pohua enregistre dans votre navigateur, dans quel but et comment vous pouvez le supprimer. Cette information vous est délivrée lors de votre premier accès, conformément à l’article 14 du Reglamento de la LFPDPPP (règlement d’application de la loi mexicaine) et à l’article 82 de la loi Informatique et Libertés (France).',
        secciones: [
            { t: '1. En résumé', b: [[
                '<b>Uniquement ce qui est strictement nécessaire</b> au fonctionnement de l’application (connexion, ouverture des calculateurs) et à la mémorisation des <b>préférences que vous choisissez vous-même</b> (thème, langue, son, horloge).',
                '<b>Aucun</b> cookie publicitaire, de mesure d’audience, de réseaux sociaux ou tiers. Aucun pistage entre sites.',
                'La police de caractères est servie par Pohua lui-même : votre navigateur ne se connecte ni à Google ni à aucun autre tiers lorsque vous ouvrez l’application.',
            ]]},
            { t: '2. Pourquoi nous ne vous demandons pas votre consentement', b: [
                'Les cookies et le stockage strictement nécessaires à la fourniture d’un service expressément demandé par l’utilisateur, ou à la mémorisation d’une préférence qu’il a lui-même définie, sont exemptés de consentement préalable (article 82 de la loi Informatique et Libertés et lignes directrices de la CNIL ; art. 5.3 de la directive 2002/58/CE). C’est pourquoi nous nous bornons à vous en informer. Si Pohua devait un jour recourir à une autre technologie, celle-ci ne serait pas activée avant que vous l’ayez expressément acceptée, et vous pourriez retirer cette acceptation depuis cette page.',
            ]},
            { t: '3. Le détail', b: ['{{tabla}}'] },
            { t: '4. Comment les supprimer ou les bloquer', b: [
                'Vous pouvez effacer les préférences enregistrées par Pohua à l’aide du bouton ci-dessous, ou tout supprimer depuis les paramètres de votre navigateur (rubrique confidentialité, « cookies et données de site »). Vous pouvez également les y bloquer.',
                'Veuillez noter que sans le cookie technique et le stockage de session, <b>il est impossible de se connecter ou d’ouvrir les calculateurs</b>, et que la suppression de la copie locale du calculateur efface le travail qui n’a pas encore été enregistré dans Pohua.',
                '{{botonBorrar}}',
            ]},
            { t: '5. Pour en savoir plus', b: [
                'L’utilisation que nous faisons des données personnelles est décrite dans la <a href="?doc=privacidad">politique de confidentialité</a>. Questions : {{correo}}. Version {{version}}.',
            ]},
        ],
        tabla: [
            ['cgr_lector', 'Cookie technique (HttpOnly)', 'Donne accès aux calculateurs et au lecteur de plans une fois la session ouverte.', 'Jusqu’à la fermeture du navigateur'],
            ['cgr_token, cgr_token_caduca, cgr_usuario', 'Stockage de session', 'Maintient la session ouverte dans cet onglet.', 'Jusqu’à la fermeture de l’onglet ou 8 heures'],
            ['cgr_correo', 'Stockage local', 'Mémorise l’adresse électronique de la dernière connexion pour éviter de la saisir à nouveau.', 'Jusqu’à sa suppression'],
            ['cgr-tema, cgr-idioma, cgr-sonido, cgr-reloj, cgr-instalar-oculto', 'Stockage local', 'Préférences choisies par l’utilisateur : thème clair ou sombre, langue, son des notifications, fuseau horaire de l’horloge et masquage éventuel de la suggestion d’installer l’application.', 'Jusqu’à sa suppression'],
            ['cgr-legal', 'Stockage local', 'Mémorise que vous avez déjà été informé de la présente politique, afin de ne pas réafficher l’avis.', 'Jusqu’à sa suppression ou un changement de version'],
            ['iscv4_local, iscv4_sharedlocal', 'Stockage local', 'Le calculateur y enregistre le brouillon en cours et une copie de travail, afin de ne pas perdre la saisie en cas de coupure de connexion. Peut contenir des données du devis.', 'Jusqu’à sa suppression'],
            ['Cache de l’application', 'Service worker', 'Enregistre les fichiers de l’application (et non les données des devis) pour qu’elle s’ouvre plus rapidement et fonctionne hors connexion.', 'Jusqu’à la version suivante'],
            ['Notifications', 'Autorisation du navigateur', 'Uniquement si l’utilisateur les active : permet de recevoir les notifications de Pohua sur le téléphone ou l’ordinateur.', 'Jusqu’à leur désactivation'],
        ],
    },

    terminos: {
        titulo: 'Conditions d’utilisation de Pohua',
        intro: 'Pohua est un outil interne de la société permettant de recevoir, d’évaluer et de chiffrer les demandes des clients. En vous connectant avec votre compte, vous acceptez les présentes conditions.',
        secciones: [
            { t: '1. Utilisateurs autorisés', b: [
                'Seuls les membres du personnel et les collaborateurs auxquels la société a attribué un compte. Les identifiants sont personnels et incessibles : ne les communiquez pas et ne laissez pas votre session ouverte sur des postes appartenant à des tiers. Si vous soupçonnez qu’une autre personne en a connaissance, changez votre mot de passe et prévenez l’administrateur.',
            ]},
            { t: '2. Confidentialité', b: [
                'Les informations contenues dans Pohua — données des clients, plans, prix, coûts, marges, fournisseurs et conditions commerciales — sont confidentielles et peuvent relever du secret des affaires. Utilisez-les uniquement dans le cadre de votre travail, ne les copiez pas en dehors des systèmes de la société et ne les communiquez pas à des tiers sans autorisation. Cette obligation perdure après la fin de votre relation avec la société.',
            ]},
            { t: '3. Utilisation acceptable', b: [[
                'N’essayez pas d’accéder à des fonctions ou à des données pour lesquelles votre rôle ne dispose pas d’autorisation.',
                'N’extrayez pas de données de manière massive ou automatisée et ne perturbez pas le fonctionnement de l’application.',
                'Ne téléchargez pas de données sensibles ni d’informations étrangères au devis.',
                'Respectez les droits des clients sur leurs plans et documents.',
            ]]},
            { t: '4. Résultats automatiques', b: [
                'Les données que l’intelligence artificielle extrait des courriels et des plans, ainsi que les prix calculés par le moteur de coûts, constituent une aide : ils peuvent comporter des erreurs. <b>Avant l’envoi d’une offre, une personne habilitée doit vérifier</b> les cotes, le matériau, les quantités et le prix. La responsabilité de ce qui est envoyé au client incombe à la personne qui l’approuve.',
            ]},
            { t: '5. Journal d’activité', b: [
                'Pohua enregistre qui effectue chaque action significative (approuver, refuser, modifier, envoyer) et quand, à des fins de traçabilité des décisions commerciales et de sécurité. Ce journal peut être consulté par les administrateurs. Les données traitées et leur durée de conservation sont décrites dans la <a href="?doc=privacidad">politique de confidentialité</a>.',
            ]},
            { t: '6. Disponibilité', b: [
                'La société s’efforce d’assurer un fonctionnement continu de Pohua, mais peut l’interrompre pour maintenance ou pour des causes indépendantes de sa volonté. Enregistrez votre travail dans l’application ; ne vous fiez pas aux copies locales.',
            ]},
            { t: '7. Propriété', b: [
                'Pohua, ses calculateurs, le moteur de coûts et leur contenu sont la propriété de la société ou de ses concédants de licence. Votre compte vous confère un droit d’utilisation pour les besoins de votre travail, à l’exclusion de tout autre droit.',
            ]},
            { t: '8. Suspension', b: [
                'La société peut suspendre ou supprimer un compte en cas de manquement aux présentes conditions, à la fin de la relation de travail ou de collaboration, ou pour des raisons de sécurité.',
            ]},
            { t: '9. Modifications, droit applicable', b: [
                'Les présentes conditions peuvent être modifiées ; la nouvelle version sera publiée ici et Pohua vous demandera de l’accepter lors de votre connexion. Loi applicable et juridiction compétente : {{jurisdiccion}}, sans préjudice des droits que la législation du travail et la législation relative à la protection des données du pays de chaque utilisateur lui reconnaissent. Version {{version}}.',
            ]},
        ],
    },
};
