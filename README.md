# 📈 QTrader

English | [简体中文](./README.zh-CN.md) | [Français](./README.fr.md) | [Deutsch](./README.de.md) | [Español](./README.es.md) | [日本語](./README.ja.md) | [한국어](./README.ko.md)

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](./requirements.txt)
[![Node.js](https://img.shields.io/badge/Node.js-18%2B-339933?logo=node.js&logoColor=white)](./frontend/package.json)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

<p align="center">
  <img src="docs/qtrader-banner.svg" alt="QTrader Banner" width="100%">
</p>

A full-stack **quantitative trading platform** built on [Qlib](https://github.com/microsoft/qlib) — multi-source data, 15 AI models, backtesting, simulated/live trading, and real-time risk control.

## ✨ Features

- **Multi-Source Data** — AKShare/Qlib, minute-level K-lines, hot-switching, SQLite cache
- **AI Training** — 15 models (LightGBM/XGBoost/CatBoost/GRU/LSTM/ALSTM/TCN/TabNet/DNN/GATs/SFM/Transformer/DoubleEnsemble/HFLGBModel)
- **Backtesting** — TopkDropoutStrategy + VWAP execution + multi-strategy comparison
- **Trading** — SimBroker (T+1) + EastMoney jvQuant API + risk control
- **Real-Time** — WebSocket push (quotes / orders / training / positions)

## 🚀 Quick Start

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
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

## 📖 Docs

- Full docs in your language via the links at the top
- API reference: http://localhost:8000/docs (Swagger UI)

## 📜 License

[MIT License](./LICENSE)
