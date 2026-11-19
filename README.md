# gta6-clips-agent

Ogni giorno prende il momento migliore dalle live GTA 6 di uno streamer di una campagna di
clipping a cui sei iscritto, lo monta in verticale con sottotitoli e lo pubblica come YouTube Short.
Adattato da [sniff3er/shorts-agent](https://github.com/sniff3er/shorts-agent).

| File | Cosa fa |
|---|---|
| `campaigns.json` | Campagne attive: streamer, canali sorgente, hashtag/testi obbligatori, layout |
| `clips.py` | Trova i momenti candidati (heatmap "più riprodotti" o picchi della chat) + trascrizione |
| `writer.py` | Formato dello script e regole per scegliere e confezionare la clip; `check` lo valida |
| `agent.py` | Scarica solo lo spezzone, trascrive, monta, estrae i frame di controllo |
| `transcribe.py` | Sottotitoli parola per parola con faster-whisper (locale, gratis) |
| `montage.py` | 1080x1920: video su sfondo sfocato o facecam sopra/gioco sotto, hook, credito, volume |
| `publisher.py` | Carica su YouTube (programmato per lo slot delle 17:00, 20:00 o 23:00 di Roma) |
| `engager.py` | Primo commento e risposte ai commenti |
| `used_clips.md` / `earnings.md` | Clip già usate / Short da inviare alla campagna |
| `CLAUDE.md` | Routine giornaliera che Claude esegue |

Configurazione: vedi [SETUP.md](SETUP.md).

```powershell
.venv\Scripts\python clips.py scan
.venv\Scripts\python agent.py --script scripts\<slug>.json
.venv\Scripts\python agent.py --frames output\<slug>
.venv\Scripts\python publisher.py output\<slug> --slot auto
```
