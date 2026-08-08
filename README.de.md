# QTrader

<p align="center">
  <img src="docs/qtrader-banner.svg" alt="QTrader Banner" width="100%">
</p>

**[简体中文](README.zh-CN.md)** | **[English](README.en.md)** | **[Français](README.fr.md)** | **[Deutsch](README.de.md)** | **[Español](README.es.md)** | **[日本語](README.ja.md)** | **[한국어](README.ko.md)**

---

## Einführung

Eine Full-Stack-Plattform für quantitatives Trading, aufgebaut auf dem [Qlib](https://github.com/microsoft/qlib)-Ökosystem, mit mehreren Datenquellen, KI-Modelltraining & Backtesting, simuliertem/echtem Trading und Echtzeit-Risikomanagement.

### Funktionen

- **Mehrere Datenquellen**: Einheitliche AKShare / Qlib-Abstraktion mit Hot-Switching zur Laufzeit und inkrementellem SQLite-Cache
- **Minuten-Daten**: 1/5/15/30/60-Minuten-K-Line-Sync & -Abfrage, automatische APScheduler-Synchronisierung nach Börsenschluss
- **KI-Trainings-Engine**: Verbindet das Qlib-Ökosystem — unterstützt 15 Modelle (LightGBM / XGBoost / CatBoost / Linear / GRU / LSTM / ALSTM / Transformer / TCN / TabNet / DNN / GATs / SFM / DoubleEnsemble / **HFLGBModel**)
- **Hochfrequenz-Modell**: HFLGBModel + HighFreqHandler, trainiert auf 1-Minuten-Daten mit Positionspuffer (REBALANCE_INTERVAL=5, BUFFER_ZONE=2)
- **Trainings-Dashboard**: 6-dimensionale Signalanalyse-Diagramme (Loss / RankIC / RankICIR / Long-Short-NAV / Dezil-Renditen / Turnover) + HF-spezifische Metriken (Rendite pro Turnover / Kostenanalyse / Signalhalbwertszeit / Kapazitätskurve)
- **Portfolio-Backtest**: TopkDropoutStrategy (topk=30, n_drop=3) + VWAP-Ausführung + echter Turnover + annualisierte Rendite/Sharpe/Max-Drawdown/IR
- **Einzelaktien-Vorhersage**: Geladene Modelle erzeugen Vorhersage-Scores + bullisches/bärisches Signal + Stärke (automatisches Routing von HF-Modellen auf den Minuten-Pfad)
- **Modellversionierung**: Trainierte Modelle automatisch persistiert mit inkrementeller Versionierung, abfragbar nach Job und herunterladbar
- **Modell-Sternebewertung**: Trainierte Modelle mit 1–5 Sternen bewerten, für einfache Auswahl des besten Modells
- **Backtesting-Engine**: TopkDropout-Strategie + Evaluator (Sharpe, Max-Drawdown, Calmar, IR) mit Plotly-Diagrammen + Multi-Strategie-Vergleich
- **Handelsmodul**: SimBroker In-Memory-Abgleich (T+1) + EastMoney jvQuant-API-Integration
- **Risikomanagement**: Limit pro Order / tägliches Trade-Limit / Positionsquote / Limit-Hoch-Filter / Tagesverlust-Unterbrecher
- **Strategie-Engine**: Signal → Risikofilter → Orderausführung mit geplantem Rebalancing + Laufzeit-Logs
- **Job-Persistenz**: Trainings-/Backtest-Jobs in SQLite (Standard) oder PostgreSQL
- **Echtzeit-Fortschritt**: Trainingsfortschritt in Prozent + Log-Zeitachse + WebSocket-Push
- **Lokaler K-Line-Reader**: Qlib-.bin-Dateien direkt ohne Netzwerkanfragen lesen, unterstützt hfq/raw-Umschaltung
- **Sync-Checkpoint**: Exakte Fortsetzung nach Unterbrechung, vermeidet doppelte Abrufe
- **Service-Verwaltung**: `qtrader.sh`-Skript mit einem Befehl (start / stop / restart / status / logs)

### Technologie-Stack

| Ebene | Technologie |
|---|---|
| Backend | FastAPI + Pydantic v2 + Uvicorn |
| Frontend | React 18 + TypeScript + Vite 6 + Ant Design 5 + Zustand |
| Visualisierung | Plotly + Lightweight Charts |
| KI/ML | Qlib + LightGBM + XGBoost + CatBoost + PyTorch (GRU/LSTM/Transformer/TCN/GATs) |
| Speicher | SQLite / PostgreSQL (Jobs) + Dateisystem (Modelle) |

### Schnellstart

**Voraussetzungen**: Python 3.10+ / Node.js 18+ / Qlib-Daten (`~/.qlib/qlib_data/cn_data`)

```bash
git clone https://github.com/shark8848/sharkyai-qtrader.git
cd sharkyai-qtrader

pip install -r requirements.txt

cd frontend && npm install && cd ..

./qtrader.sh start
```

| Dienst | URL |
|---|---|
| Frontend | http://localhost:5173 |
| Backend-API | http://localhost:8000 |
| API-Dokumentation | http://localhost:8000/docs |

Benutzerdefinierte Ports: `QTRADER_PORT=9000 QTRADER_FE_PORT=3000 ./qtrader.sh start`

### API-Übersicht

**Datenverwaltung** `/api/data`
- `GET /sources` — Verfügbare Datenquellen auflisten
- `POST /switch` — Aktive Datenquelle wechseln
- `GET /stocks` — Aktienliste abrufen
- `GET /kline` — K-Line-Daten abrufen
- `POST /sync_minute` — Minuten-K-Line-Daten synchronisieren
- `GET /sync_minute/status` — Fortschritt der Minuten-Synchronisierung
- `GET /minute/calendar` — Daten mit Minutendaten
- `GET /minute/{symbol}` — Minuten-K-Line einer Aktie an einem Datum abrufen
- `GET /minute_stocks/{date}` — Aktien mit Minutendaten an einem Datum
- `GET /local_kline/{symbol}` — Lokale .bin-Tages-K-Line lesen

**Training** `/api/train`
- `GET /config` — Standard-Trainingskonfiguration abrufen (Modelle/Handler/Märkte)
- `POST /start` — Trainingsjob starten (asynchron)
- `GET /status/{job_id}` — Trainingsfortschritt abfragen (mit Echtzeit-Logs)
- `GET /jobs` — Alle Trainingsjobs auflisten
- `DELETE /jobs/{job_id}` — Trainingsjob löschen

**Modellverwaltung** `/api/models`
- `GET /` — Alle gespeicherten Modelle auflisten (mit Versionsinfo)
- `GET /{model_id}` — Modellmetadaten abrufen
- `GET /by-job/{job_id}` — Modell nach Trainingsjob finden
- `GET /{model_id}/download` — Modelldatei herunterladen
- `DELETE /{model_id}` — Modell löschen
- `PATCH /{model_id}/rating?rating=N` — Modell-Sternebewertung festlegen (0–5)

**Backtest** `/api/backtest`
- `POST /run` — Backtest ausführen (asynchron)
- `GET /result/{job_id}` — Backtest-Ergebnisse + Diagramme abrufen
- `GET /jobs` — Alle Backtest-Jobs auflisten
- `POST /compare` — Mehrere Strategien vergleichen

**Trading** `/api/trade`
- `POST /connect` — Mit Broker verbinden
- `GET /status` — Broker-/Strategiestatus
- `GET /balance` — Guthaben abfragen
- `GET /positions` — Positionen abfragen
- `POST /order` — Order aufgeben (mit Risikoprüfung)
- `GET /orders` — Heutige Orders abfragen
- `POST /cancel/{order_id}` — Order stornieren
- `POST /strategy/start` — Automatische Strategie starten
- `POST /strategy/stop` — Automatische Strategie stoppen
- `GET /strategy/logs` — Laufzeit-Logs der Strategie

**Risikomanagement** `/api/trade/risk`
- `GET /config` — Risikokonfiguration abrufen
- `PUT /config` — Risikokonfiguration aktualisieren
- `GET /stats` — Tägliche Risikostatistiken

**Vorhersage** `/api/predict`
- `GET /data_range` — Verfügbaren Datumsbereich abrufen
- `POST /run` — Einzelaktien-Vorhersage (automatische HF/Tages-Erkennung, gibt Score-Reihe + Signal + Stärke zurück)
- `POST /minute` — Minuten-HF-Vorhersage (Tages-Bar-Level-Signale)

**WebSocket**: `ws://localhost:8000/ws` — Echtzeit-Push (Kanäle quotes / orders / training / position)

### Risikoparameter

| Parameter | Standard | Beschreibung |
|---|---|---|
| `max_order_amount` | 100,000 | Max. Betrag pro Order |
| `max_daily_trades` | 50 | Max. tägliche Trades |
| `max_position_pct` | 0.2 | Max. Positionsquote pro Aktie |
| `filter_limit_up` | true | Limit-Hoch-Aktien filtern |
| `circuit_breaker_loss` | -0.05 | Tagesverlust-Unterbrecher-Schwelle |

### Umgebungsvariablen

Alle Einstellungen unterstützen `QTRADER_`-präfixierte Umgebungsvariablen oder eine `.env`-Datei:

| Variable | Standard | Beschreibung |
|---|---|---|
| `QTRADER_PORT` | 8000 | Backend-Port |
| `QTRADER_FE_PORT` | 5173 | Frontend-Port |
| `QTRADER_HOST` | 0.0.0.0 | Backend-Listen-Adresse |
| `QTRADER_JOB_STORE_BACKEND` | sqlite | Job-Speicher-Backend (sqlite / postgresql) |
| `QTRADER_JOB_STORE_PG_DSN` | — | PostgreSQL-Verbindungsstring |
| `QTRADER_BROKER_TYPE` | sim | Broker-Typ (sim / eastmoney) |

---

## Lizenz

[MIT-Lizenz](LICENSE)
