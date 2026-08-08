# QTrader

<p align="center">
  <img src="docs/qtrader-banner.svg" alt="QTrader Banner" width="100%">
</p>

<p align="center">
  A full-stack quantitative trading platform built on the <a href="https://github.com/microsoft/qlib">Qlib</a> ecosystem — multi-source data, AI model training & backtesting, simulated/live trading, and real-time risk control.
</p>

---

## 🌍 Language / 语言 / Langue / Sprache / Idioma / 言語 / 언어

| | |
|---|---|
| 🇨🇳 **简体中文** | [README.zh-CN.md](README.zh-CN.md) |
| 🇺🇸 **English** | [README.en.md](README.en.md) |
| 🇫🇷 **Français** | [README.fr.md](README.fr.md) |
| 🇩🇪 **Deutsch** | [README.de.md](README.de.md) |
| 🇪🇸 **Español** | [README.es.md](README.es.md) |
| 🇯🇵 **日本語** | [README.ja.md](README.ja.md) |
| 🇰🇷 **한국어** | [README.ko.md](README.ko.md) |

---

## About

QTrader is a complete quantitative trading platform for individual researchers, built on the Microsoft Qlib ecosystem. It covers the entire pipeline:

- **Data**: AKShare / Qlib unified abstraction, minute-level K-line sync, hot data-source switching
- **AI Training**: 15 models (LightGBM / XGBoost / CatBoost / Linear / GRU / LSTM / ALSTM / Transformer / TCN / TabNet / DNN / GATs / SFM / DoubleEnsemble / HFLGBModel)
- **Backtesting**: TopkDropoutStrategy + VWAP execution + multi-strategy comparison
- **Trading**: SimBroker (T+1) + EastMoney jvQuant API + real-time risk control
- **Real-Time**: WebSocket push for quotes / orders / training / positions

Select your language above for the full documentation.

---

## License

[MIT License](LICENSE)
