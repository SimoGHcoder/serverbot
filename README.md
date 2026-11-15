# Server Bot

Un bot Telegram per il monitoraggio e il controllo di un server casalingo, con funzionalità di gestione container Docker, monitoraggio host e integrazioni modulari.

## Funzionalità Principali

- **Gestione Container Docker**: Inventario, dettagli, log, start/stop/restart di container.
- **Monitoraggio Host**: Metriche di sistema (uptime, RAM, disco, load) in sola lettura.
- **Integrazioni Modulari**: Supporto per DIUN, OmniRoute, aggiornamenti di sistema e altro.
- **Sicurezza**: Autenticazione utente Telegram, conferme monouso per azioni critiche, logging delle azioni in SQLite.
- **Modulo Alea**: Funzionalità di promemoria per la raccolta rifiuti, mantenuta dal modulo originale.

## Struttura del Progetto

```
server-bot/
├── bot_server.py          # Core del bot: gestione comandi, callback, webhook, task periodici
├── modules/               # Moduli funzionali
│   ├── settings.py        # Configurazione globale
│   ├── authorization.py   # Autenticazione utente Telegram
│   ├── docker_mgr.py      # Gestione container Docker
│   ├── system.py          # Metriche host
│   ├── db.py              # Logging azioni e stati in SQLite
│   ├── diun.py            # Integrazione DIUN
│   ├── omniroute_mgr.py   # Integrazione OmniRoute
│   ├── system_updates.py  # Aggiornamenti di sistema
│   ├── alea.py            # Modulo promemoria raccolta rifiuti
│   └── config_alea.json   # Configurazione modulo Alea
├── docker-compose.yml     # Definizione dell'ambiente Docker
├── Dockerfile             # Immagine Docker del bot
├── requirements.txt       # Dipendenze Python
└── .dockerignore          # File ignorati da Docker
```

## Variabili d'Ambiente

Il bot utilizza le seguenti variabili d'ambiente per la configurazione:

- `TELEGRAM_TOKEN` / `TELEGRAM_BOT_TOKEN`: Token del bot Telegram (obbligatorio)
- `ALLOWED_USER_ID`: ID numerico dell'utente Telegram autorizzato (obbligatorio)
- `OMNIROUTE_WEBHOOK_TOKEN`: Token per il webhook OmniRoute (facoltativo)
- `OMNIROUTE_HEALTH_URL`: URL per il controllo dello stato OmniRoute (facoltativo)
- `SERVER_BOT_DB_PATH`: Percorso del database SQLite (facoltativo, default: `DB_PATH` legacy)
- `SERVER_BOT_METRICS_ENABLED`: Abilita la raccolta metriche (default: `1`)
- `SERVER_BOT_METRICS_DISK_WARN`: Soglia disco per alert (default: `90%`)
- `SERVER_BOT_METRICS_MEM_WARN`: Soglia RAM per alert (default: `85%`)
- `SERVER_BOT_METRICS_LOAD_WARN`: Soglia load per alert (default: `5.0`)
- `SERVER_BOT_METRICS_INTERVAL`: Intervallo raccolta metriche (default: `300` secondi)

## Installazione

1. Clona la repository:

   ```bash
   git clone https://github.com/tuo-username/server-bot.git
   cd server-bot
   ```

2. Installa le dipendenze:

   ```bash
   pip install -r requirements.txt
   ```

3. Configura le variabili d'ambiente in un file `.env` o direttamente nell'ambiente.
4. Avvia il bot con Docker Compose:

   ```bash
   docker-compose up --build
   ```

## Utilizzo

Interagisci con il bot tramite Telegram utilizzando i seguenti comandi:

- `/menu`: Mostra il menu principale
- `/status`: Stato corrente del server e dei container
- `/orario HH:MM`: Imposta un orario specifico
- `/metriche`: Mostra le metriche di sistema (via callback)

## Sicurezza

- **Docker Socket**: Il container ha accesso in scrittura al socket Docker, equivalente a privilegi root. Non esporre porte inbound e proteggi l'account Telegram.
- **Webhook OmniRoute**: Richiede bearer token e limita i campi salvati. La porta non è esposta esternamente.

## Contributi

I contributi sono benvenuti! Segui questi passaggi:

1. Fork la repository
2. Crea un branch per la tua feature (`git checkout -b feature/nuova-feature`)
3. Commit le tue modifiche (`git commit -m 'Aggiunta nuova feature'`)
4. Push al branch (`git push origin feature/nuova-feature`)
5. Apri una Pull Request

## Licenza

Questo progetto è rilasciato sotto la Licenza MIT. Vedi il file [LICENSE](LICENSE) per dettagli
=======

# serverbot
>>>>>>>
>>>>>>> e61c185dad59ecc5b0eae6750c785c8d3cad2174
