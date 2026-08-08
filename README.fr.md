# QTrader

<p align="center">
  <img src="docs/qtrader-banner.svg" alt="QTrader Banner" width="100%">
</p>

**[简体中文](README.zh-CN.md)** | **[English](README.en.md)** | **[Français](README.fr.md)** | **[Deutsch](README.de.md)** | **[Español](README.es.md)** | **[日本語](README.ja.md)** | **[한국어](README.ko.md)**

---

## Introduction

Une plateforme de trading quantitatif complète construite sur l'écosystème [Qlib](https://github.com/microsoft/qlib), avec sources de données multiples, entraînement & backtest de modèles IA, trading simulé/réel et contrôle de risque en temps réel.

### Fonctionnalités

- **Sources de données multiples** : Abstraction unifiée AKShare / Qlib avec bascule à chaud en temps réel et cache incrémental SQLite
- **Données au niveau minute** : Synchronisation et requête de K-lines 1/5/15/30/60 minutes, synchronisation automatique APScheduler après la clôture
- **Moteur d'entraînement IA** : Connecté à l'écosystème Qlib — 15 modèles pris en charge (LightGBM / XGBoost / CatBoost / Linear / GRU / LSTM / ALSTM / Transformer / TCN / TabNet / DNN / GATs / SFM / DoubleEnsemble / **HFLGBModel**)
- **Modèle haute fréquence** : HFLGBModel + HighFreqHandler, entraîné sur données 1min avec exécution tamponnée des positions (REBALANCE_INTERVAL=5, BUFFER_ZONE=2)
- **Tableau de bord d'entraînement** : Graphiques d'analyse de signal à 6 dimensions (Loss / RankIC / RankICIR / NAV Long-Short / Rendements par décile / Turnover) + métriques HF dédiées (rendement par turnover / décomposition des coûts / demi-vie du signal / courbe de capacité)
- **Backtest de portefeuille** : TopkDropoutStrategy (topk=30, n_drop=3) + exécution VWAP + turnover réel + rendement annualisé/Sharpe/drawdown max/IR
- **Prédiction d'une action** : Charger des modèles entraînés pour générer des scores de prédiction + signal haussier/baissier + force (routage automatique des modèles HF vers le chemin minute)
- **Gestion des versions de modèles** : Modèles entraînés persistés automatiquement avec numérotation incrémentale, consultables par tâche et téléchargeables
- **Notation par étoiles des modèles** : Noter les modèles entraînés de 1 à 5 étoiles, persistés pour faciliter la sélection
- **Moteur de backtest** : Stratégie TopkDropout + évaluateur (Sharpe, drawdown max, Calmar, IR) avec graphiques Plotly + comparaison multi-stratégies
- **Module de trading** : SimBroker correspondance en mémoire (T+1) + intégration API EastMoney jvQuant
- **Contrôle de risque** : Limite par ordre / plafond de trades quotidiens / ratio de position / filtre limite-haute / disjoncteur de perte journalière
- **Moteur de stratégie** : Signal → filtre de risque → exécution d'ordre avec rééquilibrage programmé + journaux d'exécution
- **Persistance des tâches** : Tâches d'entraînement/backtest stockées dans SQLite (défaut) ou PostgreSQL
- **Progression en temps réel** : Pourcentage de progression + chronologie des journaux + push WebSocket
- **Lecture de K-lines locale** : Lire les fichiers .bin Qlib directement sans requêtes réseau, prise en charge hfq/raw
- **Point de contrôle de synchronisation** : Reprise exacte après interruption, évitant les téléchargements dupliqués
- **Gestion des services** : Script `qtrader.sh` en une commande (start / stop / restart / status / logs)

### Pile technologique

| Couche | Technologie |
|---|---|
| Backend | FastAPI + Pydantic v2 + Uvicorn |
| Frontend | React 18 + TypeScript + Vite 6 + Ant Design 5 + Zustand |
| Visualisation | Plotly + Lightweight Charts |
| IA/ML | Qlib + LightGBM + XGBoost + CatBoost + PyTorch (GRU/LSTM/Transformer/TCN/GATs) |
| Stockage | SQLite / PostgreSQL (tâches) + Système de fichiers (modèles) |

### Démarrage rapide

**Prérequis** : Python 3.10+ / Node.js 18+ / Données Qlib (`~/.qlib/qlib_data/cn_data`)

```bash
git clone https://github.com/shark8848/sharkyai-qtrader.git
cd sharkyai-qtrader

pip install -r requirements.txt

cd frontend && npm install && cd ..

./qtrader.sh start
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API Backend | http://localhost:8000 |
| Documentation API | http://localhost:8000/docs |

Ports personnalisés : `QTRADER_PORT=9000 QTRADER_FE_PORT=3000 ./qtrader.sh start`

### Aperçu de l'API

**Gestion des données** `/api/data`
- `GET /sources` — Lister les sources de données disponibles
- `POST /switch` — Basculer la source de données active
- `GET /stocks` — Obtenir la liste des actions
- `GET /kline` — Obtenir les données K-line
- `POST /sync_minute` — Synchroniser les données K-line au niveau minute
- `GET /sync_minute/status` — Progression de la synchronisation minute
- `GET /minute/calendar` — Dates avec données minute
- `GET /minute/{symbol}` — Obtenir la K-line minute d'une action sur une date
- `GET /minute_stocks/{date}` — Actions avec données minute sur une date
- `GET /local_kline/{symbol}` — Lire la K-line quotidienne .bin locale

**Entraînement** `/api/train`
- `GET /config` — Obtenir la configuration d'entraînement par défaut (modèles/handlers/marchés)
- `POST /start` — Démarrer une tâche d'entraînement (asynchrone)
- `GET /status/{job_id}` — Interroger la progression de l'entraînement (avec journaux en temps réel)
- `GET /jobs` — Lister toutes les tâches d'entraînement
- `DELETE /jobs/{job_id}` — Supprimer une tâche d'entraînement

**Gestion des modèles** `/api/models`
- `GET /` — Lister tous les modèles sauvegardés (avec informations de version)
- `GET /{model_id}` — Obtenir les métadonnées du modèle
- `GET /by-job/{job_id}` — Trouver un modèle par tâche d'entraînement
- `GET /{model_id}/download` — Télécharger le fichier du modèle
- `DELETE /{model_id}` — Supprimer un modèle
- `PATCH /{model_id}/rating?rating=N` — Définir la notation par étoiles du modèle (0–5)

**Backtest** `/api/backtest`
- `POST /run` — Exécuter un backtest (asynchrone)
- `GET /result/{job_id}` — Obtenir les résultats du backtest + graphiques
- `GET /jobs` — Lister toutes les tâches de backtest
- `POST /compare` — Comparer plusieurs stratégies

**Trading** `/api/trade`
- `POST /connect` — Se connecter au courtier
- `GET /status` — Statut courtier/stratégie
- `GET /balance` — Interroger le solde
- `GET /positions` — Interroger les positions
- `POST /order` — Passer un ordre (avec contrôle de risque)
- `GET /orders` — Interroger les ordres du jour
- `POST /cancel/{order_id}` — Annuler un ordre
- `POST /strategy/start` — Démarrer la stratégie automatique
- `POST /strategy/stop` — Arrêter la stratégie automatique
- `GET /strategy/logs` — Journaux d'exécution de la stratégie

**Contrôle de risque** `/api/trade/risk`
- `GET /config` — Obtenir la configuration de risque
- `PUT /config` — Mettre à jour la configuration de risque
- `GET /stats` — Statistiques de risque quotidiennes

**Prédiction** `/api/predict`
- `GET /data_range` — Obtenir la plage de dates disponible
- `POST /run` — Prédiction d'une action (détection auto HF/quotidien, retourne séquence de scores + signal + force)
- `POST /minute` — Prédiction HF au niveau minute (signaux par barre d'un jour)

**WebSocket** : `ws://localhost:8000/ws` — Push en temps réel (canaux quotes / orders / training / position)

### Paramètres de risque

| Paramètre | Défaut | Description |
|---|---|---|
| `max_order_amount` | 100,000 | Montant max par ordre |
| `max_daily_trades` | 50 | Trades quotidiens max |
| `max_position_pct` | 0.2 | Ratio de position max par action |
| `filter_limit_up` | true | Filtrer les actions à limite-haute |
| `circuit_breaker_loss` | -0.05 | Seuil du disjoncteur de perte journalière |

### Variables d'environnement

Tous les paramètres prennent en charge les variables d'env préfixées `QTRADER_` ou un fichier `.env` :

| Variable | Défaut | Description |
|---|---|---|
| `QTRADER_PORT` | 8000 | Port backend |
| `QTRADER_FE_PORT` | 5173 | Port frontend |
| `QTRADER_HOST` | 0.0.0.0 | Adresse d'écoute backend |
| `QTRADER_JOB_STORE_BACKEND` | sqlite | Backend de stockage des tâches (sqlite / postgresql) |
| `QTRADER_JOB_STORE_PG_DSN` | — | Chaîne de connexion PostgreSQL |
| `QTRADER_BROKER_TYPE` | sim | Type de courtier (sim / eastmoney) |

---

## Licence

[Licence MIT](LICENSE)
