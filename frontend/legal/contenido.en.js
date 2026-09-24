/**
 * Pohua legal texts, in English (translation of the Spanish reference version).
 *
 * Each document is a list of sections; each section has a title and blocks:
 * a string is a paragraph and an array is a bulleted list. Texts may contain
 * <b> and links; they are written by the team, not by users.
 *
 * Placeholders filled in by the page using `responsable.js`:
 *   {{responsables}}  the list of companies with their registered addresses
 *   {{correo}}        the privacy mailbox
 *   {{departamento}}  the personal data officer or department
 *   {{dpo}}           the data protection officer (GDPR)
 *   {{jurisdiccion}}  governing law and courts for the terms of use
 *   {{version}}       the version of the documents
 *
 * THIS TEXT MUST BE REVIEWED BY A LAWYER in each country where the company
 * operates (Mexico, the United States and France) before it is considered final.
 */
window.POHUA_LEGAL_TEXTOS = window.POHUA_LEGAL_TEXTOS || {};
window.POHUA_LEGAL_TEXTOS.en = {
    ui: {
        titulo: 'Legal information',
        privacidad: 'Privacy notice',
        cookies: 'Cookies and storage',
        terminos: 'Terms of use',
        version: 'Version',
        imprimir: 'Print',
        volver: 'Back to Pohua',
        pendiente: 'to be completed',
        avisoPendiente: 'This document contains data controller information that has not yet been completed. It is not final until the legal department fills it in and reviews it.',
        borrarPreferencias: 'Clear the preferences stored in this browser',
        borradas: 'Done: the preferences stored in this browser have been cleared.',
        tablaNombre: 'Name',
        tablaTipo: 'Type',
        tablaPara: 'Purpose',
        tablaDura: 'Duration',
    },

    privacidad: {
        titulo: 'Comprehensive privacy notice',
        intro: 'This notice explains what personal data Pohua (the request-for-quotation, or RFQ, quoting tool) processes, for what purposes, with whom it is shared, and how you can exercise your rights. It is issued in accordance with Mexico\'s Ley Federal de Protección de Datos Personales en Posesión de los Particulares (Federal Law on the Protection of Personal Data Held by Private Parties, LFPDPPP), the European Union\'s General Data Protection Regulation (GDPR), the French loi Informatique et Libertés (Data Protection Act), and any applicable laws of the United States.',
        secciones: [
            { t: '1. Data controller', b: [
                'The following group companies are the controllers of your personal data, each with respect to the data it processes at its own site:',
                '{{responsables}}',
                'For any privacy matter: {{correo}}. Personal data officer or department: {{departamento}}. Data protection officer (EU): {{dpo}}.',
            ]},
            { t: '2. Who this notice applies to', b: [[
                '<b>Pohua users</b>: company personnel and contractors who have been issued an account.',
                '<b>Customer and supplier contacts</b>: individuals who send us a request for quotation by email or whose contact information appears in one, and individuals who receive our quotations.',
            ]]},
            { t: '3. Personal data we process', b: [
                '<b>Regarding users:</b>',
                [
                    'Identification and contact data: name, corporate email address, and job title or role in the application.',
                    'Authentication data: the password, stored only as a cryptographic hash (PBKDF2); it is never stored or viewable in plain text.',
                    'Profile photo, only if the user chooses to upload one.',
                    'Activity data: date of last login and a log of the actions taken in the application (for example, who approved, declined or modified a quotation, and when).',
                    'Display preferences (theme, language, sound, clock) and, if the user enables them, the subscription to device notifications.',
                ],
                '<b>Regarding customer and supplier contacts:</b>',
                [
                    'Name, job title, email address, telephone number, company, and company address.',
                    'The content of request emails and their attachments (technical drawings), the quotations and offers issued, and the commercial terms agreed upon.',
                ],
                '<b>Technical data:</b> the servers may log the date, the requested path and the IP address of each access, for security and troubleshooting purposes.',
                '<b>We do not process sensitive personal data</b> (health, ethnic origin, beliefs, etc.). Please do not include such data in emails or drawings; if any is received, it will be deleted.',
            ]},
            { t: '4. How we use your data', b: [
                'Purposes necessary for our relationship with you:',
                [
                    'Receiving, recording and responding to requests for quotation.',
                    'Assessing technical feasibility, calculating costs, and preparing and sending quotations.',
                    'Communicating with you about your request, your quotation and any resulting order.',
                    'Creating and managing user accounts, their permissions and their access.',
                    'Maintaining the security of the application and a record of who did what, so that commercial decisions can be audited.',
                    'Complying with legal, tax and commercial obligations.',
                ],
                '<b>There are no secondary purposes.</b> Pohua does not use your data for marketing, advertising, sale of data or profiling.',
            ]},
            { t: '5. Legal basis', b: [[
                '<b>Mexico (LFPDPPP):</b> the processing described above is necessary to perform the legal or commercial relationship that you initiate by requesting a quotation, or that you have with the company as a user, and therefore does not require consent (art. 9). In all other respects, consent is deemed given tacitly if, once this notice has been made available to you, you do not object (art. 7).',
                '<b>European Union (GDPR):</b> performance of a contract or of pre-contractual measures taken at the data subject\'s request (art. 6(1)(b)); legitimate interest in managing business relationships with companies, security and auditing (art. 6(1)(f)); compliance with legal obligations (art. 6(1)(c)). For personnel, the employment relationship.',
            ]]},
            { t: '6. Use of artificial intelligence', b: [
                'To read emails and technical drawings and extract part data (material, dimensions, quantities), Pohua sends their content to an artificial intelligence model operated by a third-party provider (Anthropic, PBC, United States), which acts as a processor and processes the data solely to provide that service to us, in accordance with our contract with it.',
                '<b>No decision is made solely by automated means.</b> The feasibility, price and sending of each quotation are reviewed and decided by a person. You may request that your inquiry be handled without this processing by writing to {{correo}}.',
            ]},
            { t: '7. Who we share your data with', b: [
                'With <b>providers acting on our behalf</b> (processors), solely to provide their services to us and subject to confidentiality obligations:',
                [
                    'Application hosting (Render) and database (Neon).',
                    'Email (the corporate mailbox provider, e.g., Microsoft 365).',
                    'Cloud storage of drawings (Microsoft Azure), when enabled.',
                    'Reading of emails and drawings using artificial intelligence (Anthropic).',
                    'Delivery of notifications to the phone or browser (the browser\'s own push service: Google, Apple, Mozilla or Microsoft), only if the user enables them.',
                ],
                'Among the <b>companies of the same group</b> in Mexico, the United States and France, which operate under the same processes and policies (art. 36, sec. III, LFPDPPP).',
                'With <b>authorities</b>, when required by law or court order.',
                '<b>We do not sell or transfer your data</b> to third parties for their own purposes.',
            ]},
            { t: '8. International transfers', b: [
                'The servers of the providers listed above are located primarily in the United States, and data flows between the sites in Mexico, the United States and France. When data is transferred outside the European Union, it is protected by the standard contractual clauses approved by the European Commission or by the provider\'s participation in the EU-U.S. Data Privacy Framework, as applicable. You may request a copy of these safeguards at {{correo}}.',
            ]},
            { t: '9. How long we keep your data', b: [[
                'User accounts: for as long as the account is active; thereafter, the account is deactivated and the activity log is retained for the period required by law or for the establishment or defense of legal claims.',
                'Requests, drawings, quotations and offers: for the duration of the business relationship and, thereafter, for the retention periods imposed by tax and commercial laws (in Mexico, generally five years).',
                'Technical server logs: for as long as the hosting provider retains them for security and troubleshooting purposes.',
                'At the end of the retention period, the data is blocked and securely deleted.',
            ]]},
            { t: '10. Your rights', b: [
                'You may, at any time and free of charge:',
                [
                    '<b>Access</b> your data, <b>rectify</b> it if it is inaccurate, <b>cancel</b> it, or <b>object</b> to its processing; in Mexico, these are your ARCO rights (Access, Rectification, Cancellation, Opposition).',
                    'In the European Union, you may also request <b>erasure</b>, <b>restriction</b> of processing and <b>portability</b> of your data, and give instructions regarding the handling of your data after your death (France).',
                    '<b>Withdraw</b> any consent you have given, without retroactive effect, and <b>limit</b> the use or disclosure of your data.',
                ],
                '<b>How:</b> send an email to {{correo}} stating your name, a means for us to reply to you, a document evidencing your identity (or that of your representative), a clear description of your request and, if you are requesting a rectification, the correct information.',
                '<b>Timeframes:</b> in Mexico, we will notify you of our response within no more than 20 days and, if your request is granted, will give effect to it within the following 15 days (art. 31 LFPDPPP). In the European Union, within one month, which may be extended by two further months in complex cases (art. 12 GDPR).',
                '<b>If you are not satisfied</b>, you may contact the competent authority: in Mexico, the Secretaría Anticorrupción y Buen Gobierno (Ministry of Anti-Corruption and Good Governance); in France, the CNIL (cnil.fr); or the data protection authority of your country of residence in the EU. If you reside in a U.S. state with an applicable privacy law, you have the rights granted to you by that law.',
            ]},
            { t: '11. Security', b: [
                'We implement administrative, technical and physical measures to protect your data: encrypted connections (HTTPS), passwords stored only as cryptographic hashes, sessions that expire, role- and permission-based access, and logging of actions. In the event of a security breach that significantly affects your rights, we will inform you without undue delay and will notify the authority where required by law.',
            ]},
            { t: '12. Cookies and browser storage', b: [
                'Pohua uses only one technical cookie and local storage that are necessary for it to function and to remember the preferences chosen by the user. It does not use advertising, analytics or third-party cookies. Details, and how to delete them, are provided in the <a href="?doc=cookies">cookies and storage policy</a>.',
            ]},
            { t: '13. Minors', b: [
                'Pohua is a tool for professional use and is not directed at minors. We do not knowingly process data of minors.',
            ]},
            { t: '14. Changes to this notice', b: [
                'Any changes will be published on this page, with a new version number and date. If a change affects what data we process or for what purposes, Pohua will ask each user to read and accept it again upon logging in.',
                'Version {{version}}.',
            ]},
        ],
    },

    cookies: {
        titulo: 'Cookies and local storage policy',
        intro: 'This policy explains what Pohua stores in your browser, for what purposes, and how you can delete it. This information is provided upon first access, as required by article 14 of the Regulations of the LFPDPPP (Mexico) and article 82 of the loi Informatique et Libertés (France).',
        secciones: [
            { t: '1. What we use, in summary', b: [[
                '<b>Only what is strictly necessary</b> for the application to function (logging in, opening the calculators) and to remember the <b>preferences you choose yourself</b> (theme, language, sound, clock).',
                '<b>No</b> advertising, analytics, social media or third-party cookies. There is no cross-site tracking.',
                'The font is served by Pohua itself: your browser does not connect to Google or any other third party when you open the application.',
            ]]},
            { t: '2. Why we do not ask for your consent', b: [
                'Cookies and storage that are strictly necessary to provide a service requested by the user, or to remember a preference set by the user, are exempt from prior consent (art. 82 of the loi Informatique et Libertés and CNIL guidelines; art. 5(3) of Directive 2002/58/EC). That is why we only inform you. If Pohua ever incorporates any other technology, it will not be activated until you expressly accept it, and you will be able to withdraw that acceptance from this page.',
            ]},
            { t: '3. Details', b: ['{{tabla}}'] },
            { t: '4. How to delete or block them', b: [
                'You can delete the preferences stored by Pohua using the button below, or delete everything from your browser settings (privacy section, "cookies and site data"). You can also block them there.',
                'Please note that without the technical cookie and session storage <b>you will not be able to log in or open the calculators</b>, and that deleting the calculator\'s local copy will erase any work that has not yet been saved in Pohua.',
                '{{botonBorrar}}',
            ]},
            { t: '5. More information', b: [
                'What we do with personal data is described in the <a href="?doc=privacidad">privacy notice</a>. Questions: {{correo}}. Version {{version}}.',
            ]},
        ],
        tabla: [
            ['cgr_lector', 'Technical cookie (HttpOnly)', 'Provides access to the calculators and the drawing reader with the session already logged in.', 'Until the browser is closed'],
            ['cgr_token, cgr_token_caduca, cgr_usuario', 'Session storage', 'Keeps the session logged in on that tab.', 'Until the tab is closed or 8 hours'],
            ['cgr_correo', 'Local storage', 'Remembers the email address used at the last login so it does not have to be typed again.', 'Until deleted'],
            ['cgr-tema, cgr-idioma, cgr-sonido, cgr-reloj, cgr-instalar-oculto', 'Local storage', 'Preferences chosen by the user: light or dark theme, language, notification sound, clock time zone, and whether the suggestion to install the application was dismissed.', 'Until deleted'],
            ['cgr-legal', 'Local storage', 'Remembers that you have already been informed of this policy, so the notice is not shown again.', 'Until deleted or the version changes'],
            ['iscv4_local, iscv4_sharedlocal', 'Local storage', 'The calculator stores the draft in progress and a working copy here, so that what has been entered is not lost if the connection drops. It may contain quotation data.', 'Until deleted'],
            ['Application cache', 'Service worker', 'Stores the application files (not quotation data) so that it opens faster and works offline.', 'Until the next version'],
            ['Notifications', 'Browser permission', 'Only if the user enables them: allows Pohua notifications to be received on the phone or desktop.', 'Until disabled'],
        ],
    },

    terminos: {
        titulo: 'Pohua terms of use',
        intro: 'Pohua is an internal company tool for receiving, evaluating and quoting customer requests. By logging in with your account, you accept these terms.',
        secciones: [
            { t: '1. Who may use it', b: [
                'Only personnel and contractors who have been issued an account by the company. Credentials are personal and non-transferable: do not share them or leave your session open on devices that are not yours. If you suspect that someone else knows your credentials, change your password and notify the administrator.',
            ]},
            { t: '2. Confidentiality', b: [
                'The information in Pohua (customer data, drawings, prices, costs, margins, suppliers and commercial terms) is confidential and may constitute an industrial or trade secret. Use it only for your work, do not copy it outside the company\'s systems, and do not share it with third parties without authorization. This obligation continues after your relationship with the company ends.',
            ]},
            { t: '3. Acceptable use', b: [[
                'Do not attempt to access functions or data that your role is not authorized to access.',
                'Do not extract data in bulk or by automated means, or interfere with the operation of the application.',
                'Do not upload sensitive personal data or information unrelated to the quotation.',
                'Respect customers\' rights in their drawings and documents.',
            ]]},
            { t: '4. Automated results', b: [
                'The data that artificial intelligence extracts from emails and drawings, and the prices calculated by the costing engine, are an aid: they may contain errors. <b>Before a quotation is sent, an authorized person must review</b> the dimensions, material, quantities and price. The person who approves what is sent to the customer is responsible for it.',
            ]},
            { t: '5. Activity log', b: [
                'Pohua records who performs each relevant action (approve, decline, modify, send) and when, for the traceability of commercial decisions and for security purposes. This log may be consulted by administrators. What is processed and for how long is set out in the <a href="?doc=privacidad">privacy notice</a>.',
            ]},
            { t: '6. Availability', b: [
                'The company endeavors to keep Pohua running continuously, but may interrupt it for maintenance or for reasons beyond its control. Save your work in the application; do not rely on local copies.',
            ]},
            { t: '7. Ownership', b: [
                'Pohua, its calculators, the costing engine and its content are the property of the company or its licensors. Your account grants you permission to use it for your work and no other rights.',
            ]},
            { t: '8. Suspension', b: [
                'The company may suspend or terminate an account if these terms are breached, upon termination of the employment or contractor relationship, or for security reasons.',
            ]},
            { t: '9. Changes; governing law', b: [
                'These terms may change; the new version will be published here and Pohua will ask you to accept it upon logging in. They are governed by the following law and courts: {{jurisdiccion}}, without prejudice to the rights granted to each user under the employment and data protection laws of the user\'s country. Version {{version}}.',
            ]},
        ],
    },
};
