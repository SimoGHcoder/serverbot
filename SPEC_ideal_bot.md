# Server Bot — Specifica Funzionalità e Potenzialità Idealmente Desiderate

**Autore:** programmatore esperto (prospettiva AI) · **Data:** 15 novembre 2026
**Ambito:** bot di controllo e gestione di un server casalingo, interfaccia Telegram

---

## 1. Filosofia progettuale

Un bot domestico deve essere **utile, sicuro, verificabile**. Ogni azione deve essere:

1. **Autorizzata** — solo l'utente configurato può operare.
2. **Confermata** — nessuna azione distruttiva senza sfida monouso.
3. **Auditata** — ogni operazione lascia traccia con attore, target, esito.
4. **Osservabile** — log strutturati, health check, metriche.
5. **Idempotente** — le operazioni di automazione devono poter essere rieseguite senza effetti collaterali.

---

## 2. Funzionalità core (il minimo indispensabile)

### 2.1 Controllo container Docker
- Inventario con stato, health, immagine, uptime, restart count.
- Start / stop / restart singolo con conferma monouso (challenge + scadenza).
- Restart-all degli attivi, escluso il bot stesso.
- Log recenti limitati e HTML-escaped.
- **Assenza totale** di pull-on-check, aggiornamenti impliciti, prune, shutdown host: azioni pericolose vanno gestite da procedure Compose dedicate, non dal bot.

### 2.2 Stato host
- Uptime, RAM, dischi, load da `/proc` e API filesystem (sola lettura, no shell).
- Riconoscimento mount specifici (es. `/mnt/storage_immich`) per storage dedicato.

### 2.3 Audit e stato
- SQLite con 3 tabelle: stati container (watchdog), audit azioni, eventi webhook.
- Migrazione schema non distruttiva per preservare la storia.
- Troncamento campi per evitare righe eccessive.

### 2.4 Autenticazione
- Autorizzazione per ID Telegram esatto, nessun fallback a gruppi.
- Challenge crittografici (`secrets.token_urlsafe`) con scadenza.
- Token per container con purga automatica degli scaduti.

---

## 3. Sicurezza (livello atteso)

| Controllo | Requisito |
|-----------|-----------|
| Socket Docker | Mount con capability rimosse; **obiettivo**: proxy API write-scoped o agente host ristretto |
| Webhook | Bearer token HMAC, body limitato, 404 se non configurato |
| Anti-SSRF | Allowlist host/schema per health check esterni |
| Input | HTML escaping su tutti i testi dinamici; validazione formato orario; limiti lunghezza |
| Segreti | Mai nei layer Docker, mai nel repo; env globale montato a runtime |
| Container | read-only, cap_drop ALL, no-new-privileges, pids/mem limit, nessuna porta pubblicata |

---

## 4. Potenzialità idealmente desiderate (roadmap)

Queste funzionalità trasformerebbero il bot da "pannello di controllo" a "assistente operativo autonomo". Sono ordinate per priorità e fattibilità.

### 4.1 Osservabilità avanzata
- **Metriche storiche**: serie temporali di CPU/RAM/dischi/container su SQLite o InfluxDB, con grafici settimanali inviati su comando.
- **Alert proattivi**: notifica soglie (es. disco > 90%, container riavviato N volte, memoria > 85%) invece di solo stato on-demand.
- **Aggregazione log**: ricerca testuale nei log container con filtri (intervallo, livello, pattern) e paginazione.
- **Health check end-to-end**: ping periodico dei servizi critici (Immich, OmniRoute, DIUN) con dashboard "tutto verde / qualcosa non va".

### 4.2 Automazione operativa
- **Scheduler comandi**: esegui azioni a orari definiti (es. stop container non usati dopo mezzanotte, restart mattutino).
- **Scene predefinite**: macro "buongiorno" / "buonanotte" che avviano/arrestano gruppi di container con una conferma.
- **Auto-remediation**: riavvio automatico di container con health `unhealthy` dopo N tentativi, con notifica e log.
- **Backup**: trigger backup giornaliero (dump DB, tar volumi) con verifica integrità e notifica esito.
- **Update management**: elenco immagini con update available (senza pull automatico), approvazione via bot, esecuzione tramite Compose con rollback automatico su fallimento health check.

### 4.3 Sicurezza avanzata
- **Autorizzazione multi-utente**: lista ID autorizzati con ruoli (viewer / operator / admin) e permessi per azione.
- **Autenticazione a due fattori**: conferma via codice per azioni critiche (restart-all, stop DB).
- **Rate limiting**: throttling comandi per utente per prevenire abusi.
- **IP allowlist webhook**: restrizione per rete locale o proxy reverse.
- **Audit export**: dump CSV/JSON dello storico azioni per analisi esterna.
- **Rotazione segreti**: comando per rigenerare token webhook e challenge senza riavvio.

### 4.4 Integrazioni
- **Home Assistant**: stato device, trigger scene, lettura sensori.
- **Immich**: foto recenti, conteggio asset, stato backup.
- **Smart notifications**: alert da servizi di terze parti (Grafana, Uptime Kuma, Pi-hole) inoltrati come messaggi Telegram.
- **Voice/Telegram inline**: risposte vocali o messaggi vocali trascrizioni per comandi hands-free.
- **Web UI locale**: dashboard web (FastAPI + template) per chi preferisce browser a Telegram.

### 4.5 Robustezza e manutenibilità
- **Config hot-reload**: ricarica configurazione senza riavvio (SIGHUP o comando Telegram).
- **Graceful degradation**: se Docker non raggiungibile, bot rimane attivo per comandi non-Docker (orario, Alea, stato host).
- **Test coverage > 80%**: test async, test integrazione Docker con container effimeri, test webhook con TestClient.
- **CI/CD locale**: pipeline che esegue lint, test, bandit, build Compose prima del deploy.
- **Documentazione vivente**: README auto-aggiornato con hash dei file e ultimo esito test.
- **Versioning semantico**: tag release, changelog, rollback a versione precedente.

### 4.6 Esperienza utente
- **Onboarding**: primo avvio guida alla configurazione (token, user ID, container da escludere).
- **Help contestuale**: `/help` per ogni area (Docker, Alea, OmniRoute) con esempi.
- **i18n**: italiano/inglese switchabile.
- **Accessibilità**: risposte concise, emoji coerenti, tastiere numeriche per conferme.
- **Storico conversazione**: cache ultime azioni in Telegram per scroll indietro.

---

## 5. Architettura target (visione)

```
bot_server.py                    Orchestrazione: handler, task, webhook, scheduler
├── modules/settings.py          Config + validazione strict
├── modules/authorization.py     Auth multi-ruolo
├── modules/docker_mgr.py        Docker SDK + proxy write-scoped (futuro)
├── modules/db.py                SQLite + retention policy + export
├── modules/system.py            Metriche host + storici
├── modules/metrics.py           Serie temporali + soglie + alert  [NUOVO]
├── modules/scheduler.py         Scene + job cron-like              [NUOVO]
├── modules/backup.py            Backup + verifica + notifica       [NUOVO]
├── modules/alea.py              Calendario rifiuti (intatto)
├── modules/diun.py              Log DIUN
├── modules/omniroute_mgr.py     Health check con allowlist
├── modules/system_updates.py    Buffer aggiornamenti OS
├── modules/keyboards.py         Tastiere inline
└── modules/webui.py             Dashboard FastAPI locale           [NUOVO]
```

---

## 6. Criteri di accettazione per ogni nuova funzionalità

1. **Isolamento**: nessuna side-effect reale nei test unitari.
2. **AAA**: ogni test strutturato Arrange-Act-Assert.
3. **Logging**: strutturato, con livello e contesto.
4. **Exit codes**: documentati e consistenti.
5. **Health check**: ogni daemon/servizio nuovo espone un modo per verificare la vita.
6. **Sicurezza**: nessun segreto in chiaro, nessun comando shell, nessuna azione irreversibile senza conferma.
7. **Documentazione**: README aggiornato con variabili, limiti, esiti test.

---

## 7. Cosa NON deve fare il bot

- Non deve esporre pulsanti per `docker system prune`, pull/aggiornamento immagini, reset fittizio OmniRoute, shutdown host.
- Non deve pubblicare porte inbound.
- Non deve memorizzare credenziali o payload log completi.
- Non deve sostituire procedure Compose verificate per deploy di immagini.

---

## 8. Conclusione

Il bot attuale è una base solida: sicuro, auditato, osservabile, con test e documentazione. Le potenzialità descritte sopra lo porterebbero da "pannello di controllo" a "assistente operativo autonomo", mantenendo intatti i principi di isolamento, conferma e audit che lo rendono affidabile su un server casalingo.

**Priorità consigliata per il prossimo step:** metriche storiche + alert proattivi (4.1), poi scene predefinite (4.2), poi multi-utente (4.3).
