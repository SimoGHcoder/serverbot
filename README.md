# Server Bot — copia locale revisionata

Questa directory è una copia locale di `/opt/server-bot` acquisita via Termalin il **11 novembre 2026** e revisionata per l'uso come pannello operativo Telegram. Le modifiche si applicano soltanto a questa copia. Sul server non è stato scritto nulla.

## Struttura

- `bot_server.py`: avvio, comandi, callback, webhook e task periodici.
- `modules/settings.py`: lettura centralizzata della configurazione globale.
- `modules/authorization.py`: controllo dell'ID Telegram autorizzato.
- `modules/docker_mgr.py`: inventario, dettaglio, log e start/stop/restart container tramite Docker SDK.
- `modules/system.py`: metriche host in sola lettura.
- `modules/db.py`: storico azioni e stati in SQLite, con migrazione non distruttiva dello schema precedente.
- `modules/diun.py`, `modules/omniroute_mgr.py`, `modules/system_updates.py`: integrazioni modulari.
- `modules/alea.py` e `modules/config_alea.json`: copie byte-per-byte del server; SHA-256 verificati uguali ai file remoti. Il sorgente Alea non è stato toccato.
- `docker-compose.yml`, `dockerfile`, `requirements.txt`, `.dockerignore`: definizione locale del container revisionata.

La directory `logs/` è creata dal bind mount Compose al primo avvio. Non ho copiato database o log: sono dati runtime e possono contenere informazioni operative; inoltre la directory remota è `700 root:root` e non è leggibile dall'account Termalin. Non sono inclusi `__pycache__` e file `.env`.

## Variabili

Il Compose continua a usare esclusivamente il file globale `/opt/.env` sul server. Nessun `.env` locale è incluso. Le variabili lette dal codice sono:

- `TELEGRAM_TOKEN` oppure `TELEGRAM_BOT_TOKEN` (obbligatorio).
- `ALLOWED_USER_ID` (obbligatorio, ID numerico dell'utente Telegram autorizzato; il fallback storico `TELEGRAM_CHAT_ID` è mantenuto ma deve identificare l'utente, non un gruppo).
- `OMNIROUTE_WEBHOOK_TOKEN` (facoltativo; se assente l'endpoint webhook è disabilitato).
- `OMNIROUTE_HEALTH_URL` (facoltativo; se assente il bot dichiara chiaramente che lo stato OmniRoute non è verificato).
- `BOT_VERSION` (non più usata): la versione del bot è gestita localmente in `modules/settings.py` come costante `BOT_VERSION`.
- `SERVER_BOT_DB_PATH` (facoltativa, fallback: `DB_PATH` legacy): percorso database SQLite.
- `SERVER_BOT_METRICS_ENABLED` (facoltativa, default `1`): abilita raccolta metriche e alert soglie.
- `SERVER_BOT_METRICS_DISK_WARN` (facoltativa, default `90`): soglia % disco per alert.
- `SERVER_BOT_METRICS_MEM_WARN` (facoltativa, default `85`): soglia % RAM per alert.
- `SERVER_BOT_METRICS_LOAD_WARN` (facoltativa, default `5.0`): soglia load 1m per alert.
- `SERVER_BOT_METRICS_INTERVAL` (facoltativa, default `300`): intervallo raccolta metriche in secondi.

Prima di un eventuale deploy, aggiungere le nuove variabili richieste al file globale sul server con procedura manuale e approvata; questa copia non lo modifica.

## Funzioni operative

- `/menu`, `/status`, `/orario HH:MM`, `/metriche` (via callback `metrics`).
- Stato risorse, elenco e dettagli container, ultimi log, avvio/arresto/riavvio singolo, riavvio dei container attivi (esclude il bot stesso).
- Le azioni Docker richiedono conferma Telegram monouso con scadenza di 90 secondi.
- Log recenti HTML-escaped e limitati; azioni registrate in SQLite.
- Alea mantiene il comportamento del modulo originale.

## Test locali

Esegui dalla cartella del progetto:

```text
python -m unittest discover -s tests -v
```

La suite copre date/regole Alea senza modificare il modulo, configurazione e autorizzazione, funzioni di sistema, migrazione SQLite, callback, log e start/stop/restart Docker simulati. Nella verifica del 11/11/2026: **12 test superati** e sintassi AST valida per 13 file Python. I vincoli in `requirements.txt` sono stati letti dal parser PEP 508 vendorizzato da pip. La suite è stata eseguita con Python 3.13 su Windows; la build Compose non è stata eseguita perché in questa postazione non sono disponibili Docker, Docker SDK, FastAPI e Uvicorn.

Non sono esposti pulsanti per `docker system prune`, pull/aggiornamento immagini, reset fittizio OmniRoute o shutdown host. Il vecchio pulsante “controlla/aggiorna” scaricava immagini durante il controllo e riavviava container senza ricrearli, quindi dichiarava aggiornamenti non applicati. Un deploy di immagini va gestito tramite Compose e una procedura verificata specifica per progetto.

## Limite di sicurezza da non perdere

Per le operazioni Docker il container mantiene l'accesso al socket host in scrittura. Questo concede poteri equivalenti a root sull'host anche se il container è read-only e ha le capability rimosse. Non pubblicare porte inbound per il bot; proteggere l'account Telegram e `ALLOWED_USER_ID`. La riduzione sostanziale del rischio richiede un proxy API Docker con allowlist di scrittura verificata o un agente host ristretto, non il solo mount `:ro` del socket.

Il webhook OmniRoute ascolta sulla porta interna 8000 soltanto se `OMNIROUTE_WEBHOOK_TOKEN` è configurato; richiede bearer token e limita i campi salvati. La Compose non pubblica la porta.

## Provenienza e perimetro

Inclusi tutti i file sorgente/configurazione necessari trovati in `/opt/server-bot` (esclusi file generati/runtime e segreti). Il file montato esternamente `/opt/scripts/power_control.sh` è stato letto per capire la vecchia azione host, ma non copiato: non appartiene alla directory del bot e non è più invocato. Il file globale `/opt/.env` non è stato letto o copiato.

## Evidenze runtime lette in sola lettura

- Il database storico contiene 44 azioni audit: 27 riavvii host, 7 prune Docker, 2 spegnimenti, 5 riavvii container, 2 stop e 1 start. Sono conteggi aggregati; i dettagli e gli ID non sono stati copiati.
- Nei log ruotati sono presenti 66.438 errori del task promemoria Alea concentrati in quattro secondi il 4 novembre 2026. La classe di errore indica che il modulo Alea caricato allora non esponeva `get_notification_time`; il sorgente letto oggi contiene quella funzione e l'hash del modulo locale coincide col server. È evidenza di una discrepanza storica tra il modulo in esecuzione e quello ora presente, non prova la causa esatta. Ho lasciato Alea intatto.
- Le tracce registrano anche errori di rete Telegram (`NetworkError`, `ConnectTimeout`, `ReadError`, `ConnectError`); dal log non si può attribuire la causa a un problema del bot o della rete esterna.
- Ultimo stato salvato dal bot nel DB (11/11/2026 21:16): `server-bot` attivo, `diun` terminato con codice 0. È stato snapshot interno, non una lettura Docker corrente. `aleabot` risulta terminato il 5/11; è un container separato, escluso da questa copia e non modificato.

Non ho installato dipendenze né eseguito test o build. La copia richiede una revisione operativa e la verifica dell'ambiente prima del deploy.
