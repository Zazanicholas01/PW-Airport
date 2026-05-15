# PW-Airport

Simulazione aeroportuale in tempo reale con:

- Backend Python (scheduling autorevole, stato DB e clock di simulazione)
- Client Unity (setup della scena, spawning dei prefab, movimento su spline)
- Placement AR dello scenario aeroportuale in Unity AR Space
- Parcheggi circolari di holding sopra l'aeroporto per la gestione degli arrivi senza stand libero
- Servizi di terra per bus passeggeri e mezzi cargo/bagagli coordinati dal backend
- PostgreSQL + Metabase (persistenza dei dati e analisi)
- Dashboard FastAPI con viste live e dettaglio
- Servizio chatbot FastAPI che inoltra prompt verso un server LLM remoto

## Documentazione

La documentazione del progetto e organizzata in `src/docs` (cartelle tematiche, in ordine di lettura):

- `src/docs/README.md` (indice)

## Macro Architettura

### Componenti principali

- `src/server.py`: entrypoint del processo; inizializza lo stato condiviso (`PrefabStore`, `InitGraph`, `WorldState`) e avvia il server WebSocket.
- `src/transport/ws_server.py`: orchestratore del flusso di setup, del flusso runtime, degli scheduler, della sincronizzazione del clock e del dispatch dei comandi verso Unity.
- `src/transport/message_bus.py`: code async in ingresso/uscita tra il trasporto WebSocket e la logica backend.
- `src/handlers/setup_bus.py`: gestisce i payload di bootstrap di Unity (spline + prefab), costruisce i path e scrive la tabella `Percorso`.
- `src/handlers/runtime_bus.py`: gestisce gli eventi runtime di Unity (`path_completed`, `plane_left_stand`) e i timer di sbarco.
- `src/schedulers/spawn_scheduler.py`: pianifica gli spawn iniziali degli aerei parcheggiati dopo il setup.
- `src/schedulers/flight_scheduler.py`: motore decisionale a finestra scorrevole per il lifecycle di partenze/arrivi.
- `src/services/flight_generator.py`: crea voli casuali nel DB per la simulazione.
- `src/services/ground_vehicle_coordinator.py`: coordina bus passeggeri e mezzi cargo, assegna i path ai veicoli e gestisce i cicli di servizio.
- `src/db/db_functions.py`: transizioni DB a livello di dominio (assegnazione aerei, prenotazione stand, assegnazione path, transizioni di stato).
- `src/domain/sim_clock.py`: clock di simulazione autorevole con `time_scale` regolabile.
- `src/web/dashboard_app.py`: dashboard FastAPI con shell HTML, websocket live (`/ws/clock`, `/ws/window-flights`) e API di dettaglio per voli e aerei.
- `src/llm_service/app.py` + `src/llm_service/templates/index.html` + `src/llm_service/static/*`: servizio chatbot web che inoltra richieste a un endpoint LLM remoto.
- `Unity_Scripts/*`: lato Unity per client websocket, dispatcher, export/import spline, spawning, movimento lungo i path e controlli temporali.
- `Unity_Scripts/AirportSimulationBootstrap.cs` + `Unity_Scripts/AutoARPlacementController.cs`: placement AR, rebuild delle cache spline dopo il posizionamento e bootstrap della simulazione.

### Modello dati (alto livello)

Entita principali in `src/db/models.py`:

- `Flight` (`Viaggio`): pianificazione + stato operativo.
- `Airplane` (`Aereo`): stato dell'aeromobile e percorso corrente.
- `Stand` (`Piazzola`): disponibilita del parcheggio/stand e collegamento opzionale con un aereo.
- `Path` (`Percorso`): segmenti spline generati per il movimento.
- `ParkingSpot`: parcheggi circolari di attesa usati quando uno stand non e disponibile.
- `Vehicle`: mezzi di terra usati per trasferimento passeggeri, bagagli e cargo.
- Di supporto: `Airport`, `Airline`, `Terminal`, `Vehicle`, `Operation`, `Passenger`, `Cargo`, `ParkingSpot`.

Creazione/reset dello schema: `scripts/init_db.py`  
Seed dei dati statici (aeroporti, compagnie aeree, terminal, stand, parcheggi, veicoli): `scripts/startup.py`

## Workflow End-to-End

### 1) Startup e handshake di setup (Unity -> Python)

1. Unity si connette a `ws://localhost:8765` (`UnityWSClient.cs`).
2. Unity `SplineRegistry` invia controllo + batch spline:
   - `setup-init`
   - `send-splines`
   - molti payload spline (inclusa `MasterSpline`)
   - `finish-send-splines`
3. Unity `PrefabRegistry` aspetta il completamento dell'invio delle spline, poi invia:
   - `send-prefabs`
   - lista prefab
   - `finish-send-prefabs`
4. Python `SetupBusHandler`:
   - bufferizza i batch di spline/prefab
   - memorizza i prefab in `PrefabStore`
   - memorizza le posizioni degli stand + il riferimento di spawn per l'atterraggio ricavato dalle spline
   - costruisce i path completi di atterraggio/partenza tramite `InitGraph`
   - svuota/ricostruisce `Percorso` nel DB
   - marca il setup come completato (`setup_completed=True`)

Risultato: il backend dispone di prefab, coordinate degli stand e rotte di movimento generate e persistite.

### 2) Logica di generazione dei path (macro)

`src/init_graph.py` esegue:

- Caricamento dello schema nodi-collegamenti da `schema_nodi.json`.
- Parsing dei knot della master spline per calcolare gli intervalli `t` normalizzati lungo `MasterSpline`.
- Costruzione dei path di atterraggio:
  - `LandingSpline -> MasterSpline slice -> StandSpline (reverse)`
- Costruzione dei path di partenza:
  - `StandSpline -> MasterSpline slice -> Spline_Departure`
- Emissione dei record path con `{source, destination, segments[]}` e salvataggio nel DB.

### 3) Bootstrap dello spawn iniziale

Quando il setup e completato:

- `schedule_initial_spawns()` esegue `SpawnScheduler.plan_initial_spawns()`.
- Lo scheduler resetta stand e tabelle collegate agli aerei per un bootstrap pulito.
- Seleziona stand disponibili e prefab aereo casuali.
- Emette comandi `spawn_plane` con `airplane_id` generato.
- Hook di uscita in `ws_server.py`:
  - garantisce che esista la riga dell'aereo (`ensure_airplane_row`)
  - collega stand -> aereo per gli spawn di bootstrap
  - registra lo snapshot del mondo in memoria (`WorldState`)

### 4) Scheduling del lifecycle dei voli (autorevole in Python)

`flight_scheduler_loop()` in `src/transport/ws_server.py`:

- aspetta il completamento del setup
- genera i voli casuali iniziali (`RandomFlightGenerator.generate_flights`)
- a ogni poll:
  - legge il tempo di simulazione da `SimulationClock`
  - recupera i voli nella finestra scorrevole (`list_flights_in_sliding_window`)
  - applica le guardie di fase di `FlightSlidingWindowScheduler`

Decisioni sul lifecycle:

- Scheduling delle partenze:
  - assegna un aereo compatibile parcheggiato (`assign_airplane_to_departure_flight`)
  - assegna il path stand->Departure (`assign_path_to_airplane`)
- Preparazione dei voli in ingresso:
  - crea/collega l'aereo al volo in ingresso (`create_and_assign_airplane_for_landing_departure`)
  - marca la partenza come `Ongoing` (`mark_landing_departed`)
- Prenotazione arrivi:
  - prenota uno stand compatibile + collega l'aereo (`reserve_stand_and_link_airplane_for_landing_arrival`)
  - assegna il path di atterraggio in base al range dell'aereo (`assign_landing_path_for_airplane`)
  - se non esiste uno stand libero, instrada l'aereo verso un parking circolare (`assign_arrival_route_or_parking`)
- Comandi di movimento:
  - invia `start_path` per le partenze all'ora di partenza
  - spawna l'aereo in ingresso vicino all'atterraggio poco prima dell'arrivo
  - invia `start_path` per l'avvicinamento all'atterraggio

### 5) Gestione degli eventi runtime (Unity -> Python)

Unity emette eventi:

- `path_completed` (da `PathCompletionReporter`)
- `plane_left_stand` (evento consumato dal runtime handler)

`RuntimeBusHandler` aggiorna lo stato DB:

- Al completamento del path di atterraggio:
  - aereo `Disembarking`
  - volo `Disembarking`
  - stand `Occupied`
  - avvia il timer simulato di sbarco
- Dopo la scadenza del timer:
  - aereo `Parked`
  - volo `Completed`
- Su `plane_left_stand`:
  - lo stand viene scollegato e riportato a `Available`
- Su completamento di un percorso verso parking:
  - il `ParkingSpot` viene marcato `Occupied`
  - l'aereo passa allo stato `InParking`
  - il backend puo liberare il parking con `clear_parking` quando uno stand torna disponibile

### 6) Holding nei parcheggi circolari sopra l'aeroporto

Il sistema supporta parcheggi circolari di attesa (`PARKING_SPLINES = (1, 2, 3)`) costruiti in `src/init_graph.py`.

- I path di ingresso vengono generati come `Path_LandingRoute_<direction>_Parking<n>`.
- I path di uscita vengono generati come `Path_Parking<n>_<landing_id>_<stand_id>`.
- Lo scheduler puo usare questi path quando un arrivo non trova subito una piazzola libera.
- `RuntimeBusHandler` osserva eventi come `parking_entered` e coordina l'uscita dal parking appena uno stand torna disponibile.

### 7) Servizi di terra: bus, bagagli e cargo

`src/services/ground_vehicle_coordinator.py` orchestra i servizi di terra in base al tipo di volo, allo stand e alla capacita dei mezzi.

- Per voli passeggeri: sequenza `passenger_transfer` + `luggage_transfer`.
- Per voli cargo: sequenza `cargo_transfer`.
- I nodi di home dei mezzi includono `BusHome_P`, `BusHome_O`, `CargoHome_P`, `CargoHome_C`, `CargoHome_O`.
- I path dei mezzi vengono risolti nel DB e inviati a Unity tramite `start_vehicle_path`.
- Durante il servizio, il backend invia anche eventi di progresso come `start_service_progress` e `stop_service_progress`.

### 8) Clock di simulazione e controllo del tempo

- Il `SimulationClock` Python e autorevole.
- `clock_sync_loop()` invia eventi `clock_sync` a Unity (10 Hz).
- Unity consuma la sincronizzazione (`SimClockClient`, `SimTimeLabel`).
- I controlli UI di Unity (`SimTimeControls`) inviano:
  - `set_time_scale`
  - opzionalmente `set_sim_time`
- `handle_clock_control()` applica le modifiche e risveglia i loop di scheduling.

### 9) Workflow dashboard

L'app FastAPI (`src/web/dashboard_app.py`) attualmente espone:

- `GET /`: dashboard principale
- `GET /flight/{flight_id}` e `GET /plane/{airplane_id}`: pagine di dettaglio
- `GET /api/status`: stato applicativo
- `GET /api/flight/{flight_id}` e `GET /api/plane/{airplane_id}`: snapshot JSON
- `WS /ws/clock`: stream live del clock di simulazione
- `WS /ws/window-flights`: stream live della finestra voli
- `/static/*`: asset CSS e immagini

La dashboard usa `src/web/dashboard_data.py`, `src/web/dashboard_live.py` e `src/web/dashboard_views.py` per combinare letture DB, stream realtime e rendering delle viste di dettaglio.

### 10) Workflow chatbot

Il servizio chatbot (`src/llm_service/app.py`) e un frontend FastAPI separato per interrogare un server LLM remoto sul progetto.

- `GET /`: interfaccia chat HTML
- `GET /health`: stato del servizio e URL remoti configurati
- `POST /api/prompt`: inoltro del prompt verso il server LLM remoto
- supporta risposta diretta oppure recupero differito via `request_id`
- supporta anche risposta streaming lato backend (`REMOTE_STREAM = True`)
- la UI web include input vocale e bridge nativo Android (`Android.sendJsonData`, `window.setPromptFromNative`)

### 11) Unity AR Space e superfici web embeddabili

Il progetto include un flusso AR nativo in Unity e due superfici web pensate per essere affiancate all'esperienza AR: dashboard e chatbot.

- `AutoARPlacementController` rileva un piano AR valido e posiziona l'aeroporto nello spazio reale.
- `AirportSimulationBootstrap` aspetta il placement, ricostruisce le cache spline e poi invia a Python il setup completo.
- Dopo il placement, il client puo mostrare superfici operative come dashboard e chatbot all'interno dell'esperienza AR o su un companion device.
- La UI del chatbot e orientata al mobile e include hook per integrazione Android, utile per embedding in contesti AR Space.

## Contratti Messaggi (principali)

### Unity -> Python

- Eventi di controllo setup: `setup-init`, `send-splines`, `finish-send-splines`, `send-prefabs`, `finish-send-prefabs`
- Payload spline: `{ "type":"event", "event":"spline", "spline": {...} }`
- Eventi runtime: `path_completed`, `plane_left_stand`
- Comandi tempo: `set_time_scale`, `set_sim_time`

### Python -> Unity

- `spawn_plane`
- `start_path` con segmenti spline ordinati
- `clock_sync`
- `welcome` iniziale

## Convenzioni di stato / vocabolario

I valori canonici sono documentati in `src/docs/14-message-contracts/standard_vocabulary.md` e usati in tutto il codice:

- Stati volo: `Unscheduled`, `Scheduled`, `Ongoing`, `Landing`, `Disembarking`, `Completed`, `StandReserved`
- Stati aereo: `Parked`, `Reserved`, `InFlight`, `Disembarking`
- Stati stand: `Available`, `Reserved`, `Occupied`
- Tipi di volo: `Cargo`, `Passengers`
- Range: `Short`, `Medium`, `Long`

## Esecuzione locale / servizi

### Stack infrastrutturale

```bash
docker compose up -d
```

Servizi:

- Postgres: `localhost:5432`
- Metabase: `http://localhost:3000`
- URI DB Metabase: `postgresql://airport:airport@postgres:5432/Airport`

### Server Python

```bash
python -m src.server
```

### Dashboard

```bash
uvicorn src.web.dashboard_app:app --reload --host 0.0.0.0 --port 8000
```

### Chatbot

```bash
uvicorn src.llm_service.app:app --reload --host 0.0.0.0 --port 8010
```
