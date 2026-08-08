# QTrader

<p align="center">
  <img src="docs/qtrader-banner.svg" alt="QTrader Banner" width="100%">
</p>

**[简体中文](README.zh-CN.md)** | **[English](README.en.md)** | **[Français](README.fr.md)** | **[Deutsch](README.de.md)** | **[Español](README.es.md)** | **[日本語](README.ja.md)** | **[한국어](README.ko.md)**

---

## 소개

[Qlib](https://github.com/microsoft/qlib) 생태계 위에 구축된 풀스택 퀀트 트레이딩 플랫폼으로, 다중 데이터 소스, AI 모델 학습 및 백테스트, 모의/실전 트레이딩, 실시간 리스크 관리를 지원합니다.

### 기능

- **다중 데이터 소스**: AKShare / Qlib 통합 추상화, 실행 중 핫 스위칭, SQLite 증분 캐시
- **분봉 데이터**: 1/5/15/30/60분 K-라인 동기화 및 조회, APScheduler 장 마감 후 자동 동기화
- **AI 학습 엔진**: Qlib 생태계 연결 — 15개 모델 지원 (LightGBM / XGBoost / CatBoost / Linear / GRU / LSTM / ALSTM / Transformer / TCN / TabNet / DNN / GATs / SFM / DoubleEnsemble / **HFLGBModel**)
- **고빈도 모델**: HFLGBModel + HighFreqHandler, 1분 데이터로 학습, 포지션 버퍼링 실행 (REBALANCE_INTERVAL=5, BUFFER_ZONE=2)
- **학습 대시보드**: 6차원 신호 분석 차트 (Loss / RankIC / RankICIR / Long-Short NAV / 십분위 수익률 / 회전율) + HF 전용 지표 (회전율당 수익 / 비용 분해 / 신호 반감기 / 용량 곡선)
- **포트폴리오 백테스트**: TopkDropoutStrategy (topk=30, n_drop=3) + VWAP 체결 + 실회전율 + 연환산 수익률/Sharpe/최대 낙폭/IR
- **단일 종목 예측**: 학습된 모델을 로드하여 예측 점수 + 강세/약세 신호 + 강도를 생성 (HF 모델을 분봉 경로로 자동 라우팅)
- **모델 버전 관리**: 학습된 모델을 자동 영구 저장, 버전 번호 증가, 작업별 조회 및 다운로드 가능
- **모델 별점 평가**: 학습된 모델에 1~5점 별점 부여, 최적 모델 선택 용이
- **백테스트 엔진**: TopkDropout 전략 + 평가기 (Sharpe, 최대 낙폭, Calmar, IR) + Plotly 차트 + 다중 전략 비교
- **트레이딩 모듈**: SimBroker 인메모리 체결 (T+1) + EastMoney jvQuant API 통합
- **리스크 관리**: 주문당 한도 / 일일 거래 상한 / 포지션 비율 / 상한가 필터 / 일일 손실 서킷 브레이커
- **전략 엔진**: 신호 → 리스크 필터 → 주문 실행, 예약 리밸런싱 + 실행 로그
- **작업 영구화**: 학습/백테스트 작업을 SQLite(기본) 또는 PostgreSQL에 저장
- **실시간 진행 상황**: 학습 진행률 + 로그 타임라인 + WebSocket 푸시
- **로컬 K-라인 읽기**: 네트워크 요청 없이 Qlib .bin 파일 직접 읽기, hfq/raw 전환 지원
- **동기화 체크포인트**: 중단 후 정확한 재개, 중복 요청 방지
- **서비스 관리**: `qtrader.sh` 원클릭 스크립트 (start / stop / restart / status / logs)

### 기술 스택

| 계층 | 기술 |
|---|---|
| 백엔드 | FastAPI + Pydantic v2 + Uvicorn |
| 프론트엔드 | React 18 + TypeScript + Vite 6 + Ant Design 5 + Zustand |
| 시각화 | Plotly + Lightweight Charts |
| AI/ML | Qlib + LightGBM + XGBoost + CatBoost + PyTorch (GRU/LSTM/Transformer/TCN/GATs) |
| 저장소 | SQLite / PostgreSQL (작업) + 파일 시스템 (모델) |

### 빠른 시작

**요구 사항**: Python 3.10+ / Node.js 18+ / Qlib 데이터 (`~/.qlib/qlib_data/cn_data`)

```bash
git clone https://github.com/shark8848/sharkyai-qtrader.git
cd sharkyai-qtrader

pip install -r requirements.txt

cd frontend && npm install && cd ..

./qtrader.sh start
```

| 서비스 | URL |
|---|---|
| 프론트엔드 | http://localhost:5173 |
| 백엔드 API | http://localhost:8000 |
| API 문서 | http://localhost:8000/docs |

사용자 지정 포트: `QTRADER_PORT=9000 QTRADER_FE_PORT=3000 ./qtrader.sh start`

### API 개요

**데이터 관리** `/api/data`
- `GET /sources` — 사용 가능한 데이터 소스 목록
- `POST /switch` — 활성 데이터 소스 전환
- `GET /stocks` — 종목 목록 가져오기
- `GET /kline` — K-라인 데이터 가져오기
- `POST /sync_minute` — 분봉 K-라인 데이터 동기화
- `GET /sync_minute/status` — 분봉 동기화 진행 상황
- `GET /minute/calendar` — 분봉 데이터가 있는 날짜
- `GET /minute/{symbol}` — 특정 날짜의 종목 분봉 K-라인 가져오기
- `GET /minute_stocks/{date}` — 특정 날짜에 분봉 데이터가 있는 종목
- `GET /local_kline/{symbol}` — 로컬 .bin 일봉 K-라인 읽기

**학습** `/api/train`
- `GET /config` — 기본 학습 설정 가져오기 (모델/핸들러/시장)
- `POST /start` — 학습 작업 시작 (비동기)
- `GET /status/{job_id}` — 학습 진행 상황 조회 (실시간 로그 포함)
- `GET /jobs` — 모든 학습 작업 목록
- `DELETE /jobs/{job_id}` — 학습 작업 삭제

**모델 관리** `/api/models`
- `GET /` — 저장된 모든 모델 목록 (버전 정보 포함)
- `GET /{model_id}` — 모델 메타데이터 가져오기
- `GET /by-job/{job_id}` — 학습 작업으로 모델 찾기
- `GET /{model_id}/download` — 모델 파일 다운로드
- `DELETE /{model_id}` — 모델 삭제
- `PATCH /{model_id}/rating?rating=N` — 모델 별점 설정 (0–5)

**백테스트** `/api/backtest`
- `POST /run` — 백테스트 실행 (비동기)
- `GET /result/{job_id}` — 백테스트 결과 + 차트 가져오기
- `GET /jobs` — 모든 백테스트 작업 목록
- `POST /compare` — 여러 전략 비교

**트레이딩** `/api/trade`
- `POST /connect` — 브로커 연결
- `GET /status` — 브로커/전략 상태
- `GET /balance` — 잔고 조회
- `GET /positions` — 포지션 조회
- `POST /order` — 주문 실행 (리스크 검사 포함)
- `GET /orders` — 오늘의 주문 조회
- `POST /cancel/{order_id}` — 주문 취소
- `POST /strategy/start` — 자동 전략 시작
- `POST /strategy/stop` — 자동 전략 중지
- `GET /strategy/logs` — 전략 실행 로그

**리스크 관리** `/api/trade/risk`
- `GET /config` — 리스크 설정 가져오기
- `PUT /config` — 리스크 설정 업데이트
- `GET /stats` — 일일 리스크 통계

**예측** `/api/predict`
- `GET /data_range` — 사용 가능한 데이터 날짜 범위 가져오기
- `POST /run` — 단일 종목 예측 (HF/일봉 자동 감지, 점수 시리즈 + 신호 + 강도 반환)
- `POST /minute` — 분봉 HF 예측 (단일 일자 바 레벨 신호)

**WebSocket**: `ws://localhost:8000/ws` — 실시간 푸시 (quotes / orders / training / position 채널)

### 리스크 매개변수

| 매개변수 | 기본값 | 설명 |
|---|---|---|
| `max_order_amount` | 100,000 | 주문당 최대 금액 |
| `max_daily_trades` | 50 | 일일 최대 거래 횟수 |
| `max_position_pct` | 0.2 | 종목당 최대 포지션 비율 |
| `filter_limit_up` | true | 상한가 종목 필터 |
| `circuit_breaker_loss` | -0.05 | 일일 손실 서킷 브레이커 임계값 |

### 환경 변수

모든 설정은 `QTRADER_` 접두사 환경 변수 또는 `.env` 파일을 지원합니다:

| 변수 | 기본값 | 설명 |
|---|---|---|
| `QTRADER_PORT` | 8000 | 백엔드 포트 |
| `QTRADER_FE_PORT` | 5173 | 프론트엔드 포트 |
| `QTRADER_HOST` | 0.0.0.0 | 백엔드 수신 주소 |
| `QTRADER_JOB_STORE_BACKEND` | sqlite | 작업 저장 백엔드 (sqlite / postgresql) |
| `QTRADER_JOB_STORE_PG_DSN` | — | PostgreSQL 연결 문자열 |
| `QTRADER_BROKER_TYPE` | sim | 브로커 유형 (sim / eastmoney) |

---

## 라이선스

[MIT 라이선스](LICENSE)
