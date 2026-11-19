# Configurazione (una volta sola, ~30 minuti)

Tutto gira sul tuo PC: il PC deve essere acceso all'ora del task. Python, Git e ffmpeg sono già
installati e la cartella `.venv` contiene le dipendenze.

## 1. Campagna TOMO (Clipping Nation)

Le regole del brief sono già in `campaigns.json` (hashtag #tomovids #gta6, CTA "Subscribe to Tomo
on YouTube", niente AI, niente clickbait...). Tu devi:

1. Entrare nel **Discord di Clipping Nation** (obbligatorio per i pagamenti).
2. Leggere l'**Approval Guide**, **How to Target a Tier 1 Audience** e l'**Account Warm-Up Guide**.
3. In Whop: **Settings → Connected Accounts** e collega il canale YouTube.
4. Ogni giorno: quando Claude pubblica lo Short, **invia il link entro 30 minuti** nella pagina
   della campagna.
5. Quando uno Short supera **2.000 views**: YouTube Studio → Analytics → Pubblico → Aree
   geografiche principali, fai uno screenshot e mandalo nella support chat del Discord. Serve
   almeno il 40% da USA, UK, Canada, Australia. Poi segna "yes" in `earnings.md`.

## 2. Canale YouTube

Crea un canale **nuovo** dedicato, in inglese, con un nome legato alla campagna (es. TomoClips,
TomoGTA6) e l'immagine della campagna come foto profilo. Fai il **warm-up** della guida prima di
pubblicare. Non nascondere mai i "Mi piace" e non cancellare gli Short (devono restare online 30 giorni).

## 3. Token YouTube (Google Cloud)

1. Vai su https://console.cloud.google.com, crea un progetto (es. `gta6-clips`) e in
   **API e servizi → Libreria** attiva **YouTube Data API v3**.
2. **Schermata consenso OAuth** (Google Auth Platform): tipo **Esterno**, nome app a piacere,
   la tua email come contatto. In **Pubblico** premi **Pubblica app** (in modalità test il token
   scade dopo 7 giorni). L'avviso "app non verificata" è normale per uso personale.
3. **Client → Crea client → App desktop**. Scarica il JSON e mettilo nella cartella
   `gta6-clips-agent` (resta solo sul PC: `.gitignore` lo esclude).
4. Nella cartella, da PowerShell:
   ```powershell
   .venv\Scripts\python publisher.py --auth
   ```
   Si apre il browser: scegli **il canale nuovo**, premi Avanzate → Vai all'app → Consenti.
   Il token viene salvato in `youtube_token.json` (anche lui solo sul PC).

Non incollare mai token o password in chat.

## 4. Prova a mano

Apri una sessione di Claude (app desktop, scheda Code) su questa cartella e scrivi:
`crea lo Short del giorno`. Claude segue la routine di `CLAUDE.md`.

## 5. Automatico

Già configurato in modalità manuale: due task pianificati (19:00 e 22:00) preparano gli Short
che pubblichi a mano alle **20:00** e alle **23:00** di Roma (19/22 nel Regno Unito, 14/17 sulla
costa est degli USA: utile per il 40% di pubblico Tier 1). Per la modalità automatica, il prompt:

```
Crea lo Short del giorno: leggi CLAUDE.md e segui per intero la "Daily routine".
Concludi con 3-4 righe in italiano: titolo, durata, link YouTube, link da inviare alla campagna entro 30 minuti.
```

Lo Short viene pubblicato subito (non programmato), quindi tieni il telefono a portata di mano
per inviare il link in tempo.

## Se YouTube blocca i download ("conferma di non essere un bot")

Succede dopo molte richieste. Spesso si sblocca da solo in qualche ora. Se dura:

1. Usa un **account Google secondario**, non quello del canale: YouTube può segnalare l'account.
2. In Chrome installa l'estensione **"Get cookies.txt LOCALLY"**, poi in `chrome://extensions` →
   Dettagli → attiva **"Consenti in modalità di navigazione in incognito"**.
3. Apri una finestra in incognito (Ctrl+Shift+N), vai su youtube.com, accedi con l'account
   secondario e fai partire un video qualche secondo.
4. Con la scheda di YouTube aperta clicca l'estensione → formato **Netscape** → **Export** (solo
   questo sito). Rinomina il file in `youtube_cookies.txt` e mettilo in questa cartella.
5. Chiudi la finestra incognito **senza fare logout** (il logout invalida i cookie).
6. `settings.json` contiene già `"youtube_cookies": "youtube_cookies.txt"`.

yt-dlp ha anche bisogno di un motore JavaScript (Deno): è in requirements.txt, non serve altro.

Il file resta solo sul PC (`.gitignore` lo esclude). Non condividerlo con nessuno.

## Limiti

- YouTube: ~6 caricamenti al giorno (quota API 10.000 unità; una risposta a un commento = 50).
- Il primo commento viene postato subito dopo la pubblicazione. Fissalo a mano in YouTube Studio
  → Commenti → ⋮ → Fissa.
