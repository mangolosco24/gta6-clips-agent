Voglio ricreare sul mio PC il sistema "gta6-clips-agent": una pipeline Python che ogni giorno
prepara YouTube Short (e TikTok/Reels) con clip di streamer che hanno campagne di clipping su
Content Rewards (Whop), pagate a views. Io pubblico a mano e invio il link alla campagna.
Rispondimi in italiano, breve.

Repository (pubblico): https://github.com/mangolosco24/gta6-clips-agent
(clonalo con git clone; se non è raggiungibile, dimmelo e fermati).

Fai così:

1. Clona il repository in una cartella con percorso CORTO (es. Documenti\gta6-clips-agent: i
   percorsi lunghi su Windows rompono pip e il download del modello) e spostaci la sessione.
   Leggi README.md, SETUP.md, CLAUDE.md e campaigns.json: contengono architettura, routine
   giornaliera e regole. Segui CLAUDE.md come istruzioni di progetto.

2. Rendi il repository "mio" (è la copia di un altro canale):
   - svuota le righe delle tabelle in used_clips.md ed earnings.md (lascia intestazioni);
   - in performance.md svuota la tabella ma tieni la sezione "Lessons so far";
   - cancella i file in scripts/;
   - in campaigns.json metti "active": false a tutte le campagne: le riattivo io una alla volta
     quando mi iscrivo e ti incollo il brief (aggiorna anche le regole se il brief è cambiato);
   - stacca il remote originale (git remote remove origin): lavoro solo in locale, salvo che io
     ti chieda di collegare un mio repository.

3. Installa e verifica (chiedimi conferma prima di installare programmi di sistema):
   Python 3.12, Git, ffmpeg (su Windows con winget), poi
   `python -m venv .venv` e `.venv\Scripts\python -m pip install -r requirements.txt`
   (include yt-dlp[default], deno per le challenge di YouTube, faster-whisper, av<16), poi
   `.venv\Scripts\python transcribe.py` per scaricare il modello dei sottotitoli.
   Se sono su Mac/Linux adatta i comandi (.venv/bin/python).

4. Google Drive per desktop (consigliato, per pubblicare dal telefono): deve essere il programma
   "Drive per desktop" scaricato da google.com/drive/download (GoogleDriveSetup.exe), NON l'app
   di Chrome. Quando l'ho installato e ho fatto l'accesso, verifica che esista l'unità con
   "Il mio Drive" e aggiorna il percorso in settings.json ("share_dirs").
   Se YouTube risponde "Sign in to confirm you're not a bot", guidami passo passo a creare
   youtube_cookies.txt con un account Google SECONDARIO e l'estensione "Get cookies.txt
   LOCALLY" in incognito (vedi SETUP.md). Controlla il file senza mostrarne il contenuto. Non
   chiedermi mai cookie, password o token in chat: dimmi dove salvarli.

5. Prova completa con un solo Short, appena ho almeno una campagna attiva:
   `clips.py scan`, scegli un momento secondo le RULES di writer.py e il brief della campagna,
   scrivi scripts/<slug>.json, `writer.py check`, `agent.py --script ...`,
   `agent.py --frames ...`, guarda i frame e mandami mp4 e _upload.txt. NON pubblicare nulla
   tu: la pubblicazione è manuale (MANUAL POSTING MODE in CLAUDE.md).

5b. Pubblicazione automatica su YouTube (io la uso già con shorts-agent): riusa il mio progetto
   Google Cloud e il client OAuth "App desktop" già pubblicato. Guidami a:
   - mettere il JSON del client (client_secret*.json) in questa cartella, oppure impostare
     YT_CLIENT_ID e YT_CLIENT_SECRET come variabili d'ambiente sul PC;
   - lanciare `.venv\Scripts\python publisher.py --auth` e scegliere il NUOVO canale GTA (non
     quello vecchio): il token viene salvato in youtube_token.json, solo sul PC;
   - mettere "posting_mode": "auto" in settings.json.
   Da quel momento si usa la AUTO POSTING MODE di CLAUDE.md: lo Short viene caricato su YouTube
   programmato esattamente all'orario dello slot, e io devo solo inviare il link alla campagna
   entro 30 minuti da quell'orario (più TikTok/Instagram a mano). Anche le risposte ai commenti
   diventano automatiche. Tutto gira sul mio PC, non nel cloud: YouTube blocca spesso i download
   dai server.

6. Crea i task pianificati dell'app desktop (modalità che ti indico io), uno per slot, che
   eseguono la "Daily routine" di CLAUDE.md in AUTO POSTING MODE (o MANUAL se il token YouTube
   non è ancora pronto):
   - ore 16:00 -> Short che esce alle 17:00
   - ore 19:00 -> Short che esce alle 20:00
   - ore 22:00 -> Short che esce alle 23:00
   In AUTO il task lo programma su YouTube per quell'orario e mi avvisa con il link da inviare.
   Ogni task: momenti mai già in used_clips.md, campagne alternate a parità di qualità, salta lo
   slot se non c'è niente di buono; alla fine mi scrive per quale campagna è, titolo, durata,
   piattaforme (TikTok sempre, Instagram solo se la campagna lo prevede), "invia ogni link entro
   30 minuti" con il link della campagna, il primo commento da fissare.

7. Dimmi cosa devo fare io, in breve:
   - canale YouTube e account TikTok/Instagram NUOVI, dedicati e in inglese (le campagne
     vogliono pagine GTA 6 / streamer clips), con il warm-up delle guide delle campagne prima di
     pubblicare;
   - iscrizione alle campagne su Content Rewards, account collegati in Whop, Discord delle
     agenzie (Clipping Nation, RUCKUS, ClipLaunch...), lettura dei brief;
   - pubblicare negli orari degli slot, inviare ogni link entro 30 minuti, mandare gli
     screenshot dei Paesi del pubblico quando richiesto (molte campagne vogliono >= 40% USA,
     UK, Canada, Australia);
   - ogni 2 giorni passarti le views, così aggiorni performance.md;
   - TikTok: account nuovo = 2-3 giorni di solo warm-up, poi un video per slot, mai tanti
     insieme; ogni link (YouTube, TikTok, Instagram) si invia alla campagna entro 30 minuti da
     quando esce su QUELLA piattaforma;
   - pubblicare dal telefono: video e testi su Drive (cartella "Shorts GTA6"), invio del link
     dal sito di Content Rewards o dall'app Whop;
   - PC: i task girano solo con PC acceso, app di Claude e Drive aperte; sospensione su "Mai"
     quando è in carica; se sto via più giorni, sospendere gli aggiornamenti di Windows;
   - mettermi d'accordo con l'amico da cui viene questo sistema per dividerci le campagne
     (o almeno non pubblicare lo stesso momento lo stesso giorno).

Lezioni già imparate (sono nel codice, non rifarle diversamente):
   - niente zoom/effetti "punch-in": desincronizzavano l'audio;
   - le clip Kick hanno salti nei tempi ogni ~10 s: il codice li ricostruisce (KICK_RETIME);
   - i sottotitoli censurano le parolacce scritte, l'audio resta originale;
   - KreekCraft: logo ufficiale per tutto il video (assets/) e nessun link nei testi.

Regole: niente contenuti generati con AI nei video; mai clickbait o contesto falso; rispetta
ogni riga del "brief" della campagna; non committare output/, models/, .venv/, cookie, token.
