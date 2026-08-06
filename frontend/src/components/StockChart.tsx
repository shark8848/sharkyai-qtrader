import { useState, useEffect, useRef, useCallback } from 'react'
import { Select, Radio, Spin, Empty, Space, Button, Card, Tag, message } from 'antd'
import { ExperimentOutlined } from '@ant-design/icons'
import { createChart, ColorType, IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts'
import axios from 'axios'

interface BarData {
  time: string | number
  open: number
  high: number
  low: number
  close: number
  volume: number
}

type Period = 'daily' | 'minute'

/** Convert 'YYYY-MM-DD HH:mm:ss' to UNIX timestamp (seconds) */
function toTimestamp(dt: string): number {
  return Math.floor(new Date(dt.replace(' ', 'T') + '+08:00').getTime() / 1000)
}

export default function StockChart() {
  const [symbol, setSymbol] = useState('sh600519')
  const [period, setPeriod] = useState<Period>('daily')
  const [days, setDays] = useState(120)
  const [adjust, setAdjust] = useState<'hfq' | 'none'>('hfq')
  const [date, setDate] = useState('')
  const [dates, setDates] = useState<{ date: string; count: number }[]>([])
  const [loading, setLoading] = useState(false)
  const [hasData, setHasData] = useState(true)
  const [stockOptions, setStockOptions] = useState<{ value: string; label: string }[]>([])
  const [searchLoading, setSearchLoading] = useState(false)
  // HF prediction state
  const [predictLoading, setPredictLoading] = useState(false)
  const [predictSignal, setPredictSignal] = useState<any>(null)

  const chartContainerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
  const predictSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)

  // Load minute dates (only dates with sufficient coverage, showing stock counts)
  useEffect(() => {
    axios.get('/api/data/minute/calendar', { params: { min_stocks: 100 } }).then(res => {
      const entries = res.data.entries || []
      setDates(entries)
      if (entries.length > 0) setDate(entries[entries.length - 1].date)
    }).catch(() => {})
  }, [])

  // Stock search with debounce
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const doSearch = useCallback(async (keyword: string) => {
    setSearchLoading(true)
    try {
      const res = await axios.get('/api/data/stocks', { params: { keyword, page_size: 30 } })
      const items = res.data.data || []
      setStockOptions(items.map((s: any) => {
        const prefix = (s.market || '').toLowerCase()
        const fullSymbol = `${prefix}${s.symbol}`.toLowerCase()
        return {
          value: fullSymbol,
          label: `${s.symbol} ${s.name}`,
        }
      }))
    } catch { /* ignore */ }
    setSearchLoading(false)
  }, [])

  const handleSearch = useCallback((keyword: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!keyword || keyword.length < 1) {
      // Show popular stocks when cleared
      loadPopular()
      return
    }
    debounceRef.current = setTimeout(() => doSearch(keyword), 300)
  }, [doSearch])

  // Load popular stocks for initial dropdown
  const loadPopular = useCallback(async () => {
    if (stockOptions.length > 5) return // already loaded
    try {
      const codes = ['600519', '000001', '601318', '000858', '600036', '300750', '601899', '002594']
      const res = await axios.get('/api/data/stocks', { params: { page_size: 5000 } })
      const items = res.data.data || []
      // Prioritize popular codes, then fill with first items
      const popular = codes.map(c => items.find((s: any) => s.symbol === c)).filter(Boolean)
      const rest = items.filter((s: any) => !codes.includes(s.symbol)).slice(0, 22)
      const merged = [...popular, ...rest]
      setStockOptions(merged.map((s: any) => {
        const prefix = (s.market || '').toLowerCase()
        return { value: `${prefix}${s.symbol}`.toLowerCase(), label: `${s.symbol} ${s.name}` }
      }))
    } catch { /* ignore */ }
  }, [stockOptions.length])

  // Initialize chart
  useEffect(() => {
    if (!chartContainerRef.current) return
    const chart = createChart(chartContainerRef.current, {
      width: chartContainerRef.current.clientWidth,
      height: 420,
      layout: {
        background: { type: ColorType.Solid, color: '#ffffff' },
        textColor: '#333',
      },
      grid: {
        vertLines: { color: '#f0f0f0' },
        horzLines: { color: '#f0f0f0' },
      },
      crosshair: { mode: 0 },
      rightPriceScale: { borderColor: '#ddd' },
      timeScale: { borderColor: '#ddd', timeVisible: period === 'minute' },
    })

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#ef5350',
      downColor: '#26a69a',
      borderUpColor: '#ef5350',
      borderDownColor: '#26a69a',
      wickUpColor: '#ef5350',
      wickDownColor: '#26a69a',
    })

    const volumeSeries = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: '',
    })
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    })

    chartRef.current = chart
    candleSeriesRef.current = candleSeries
    volumeSeriesRef.current = volumeSeries
    predictSeriesRef.current = null  // reset prediction line on chart rebuild

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth })
      }
    }
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
    }
  }, [period])

  // Fetch and render data
  useEffect(() => {
    if (!symbol) return
    if (period === 'minute' && !date) return

    setLoading(true)
    const fetchData = async () => {
      try {
        let bars: BarData[] = []
        if (period === 'daily') {
          let rows: any[] = []
          if (adjust === 'hfq') {
            const res = await axios.get(`/api/data/local_kline/${symbol}`, { params: { days } })
            rows = res.data.data || []
          } else {
            // 不复权: 新浪接口（内存缓存 1h）
            const res = await axios.get(`/api/data/raw_kline/${symbol}`, { params: { days } })
            rows = res.data.data || []
          }
          bars = rows.map((r: any) => ({
            time: r.date,
            open: r.open,
            high: r.high,
            low: r.low,
            close: r.close,
            volume: r.volume || 0,
          }))
        } else {
          const res = await axios.get(`/api/data/minute/${symbol}`, { params: { date } })
          const rows = res.data.data || []
          bars = rows.map((r: any) => ({
            time: toTimestamp(r.datetime || `${r.date} ${r.time}`),
            open: r.open,
            high: r.high,
            low: r.low,
            close: r.close,
            volume: r.volume || 0,
          }))
        }

        setHasData(bars.length > 0)
        if (bars.length > 0 && candleSeriesRef.current && volumeSeriesRef.current) {
          candleSeriesRef.current.setData(
            bars.map(b => ({ time: b.time as UTCTimestamp, open: b.open, high: b.high, low: b.low, close: b.close }))
          )
          volumeSeriesRef.current.setData(
            bars.map(b => ({
              time: b.time as UTCTimestamp,
              value: b.volume,
              color: b.close >= b.open ? 'rgba(239,83,80,0.4)' : 'rgba(38,166,154,0.4)',
            }))
          )
          chartRef.current?.timeScale().fitContent()
        }
        // Clear prediction when data changes
        setPredictSignal(null)
        if (predictSeriesRef.current) {
          predictSeriesRef.current.setData([])
          predictSeriesRef.current = null
        }
      } catch {
        setHasData(false)
      }
      setLoading(false)
    }
    fetchData()
  }, [symbol, period, days, date, adjust])

  // HF Predict handler
  const handlePredict = async () => {
    if (!symbol || !date) return
    setPredictLoading(true)
    try {
      const res = await axios.post('/api/predict/minute', { symbol, date })
      const data = res.data
      setPredictSignal(data.signal)

      // Draw prediction score line on chart
      if (data.predicted && data.predicted.length > 0 && chartRef.current) {
        // Remove old prediction series if exists
        if (predictSeriesRef.current) {
          chartRef.current.removeSeries(predictSeriesRef.current)
        }
        const lineSeries = chartRef.current.addLineSeries({
          color: '#2196F3',
          lineWidth: 2,
          lineStyle: 2, // dashed
          priceScaleId: 'predict',
          title: 'HF Score',
        })
        lineSeries.priceScale().applyOptions({
          scaleMargins: { top: 0.1, bottom: 0.6 },
        })
        lineSeries.setData(
          data.predicted.map((p: any) => ({
            time: toTimestamp(p.time) as UTCTimestamp,
            value: p.score,
          }))
        )
        predictSeriesRef.current = lineSeries
      }
      message.success(`预测完成: ${data.signal.direction} (强度 ${data.signal.strength}%)`)
    } catch (err: any) {
      const detail = err.response?.data?.detail || '预测失败'
      message.error(detail)
    }
    setPredictLoading(false)
  }

  return (
    <div>
      <Space wrap style={{ marginBottom: 12 }}>
        <Select
          showSearch
          value={symbol}
          onChange={setSymbol}
          onSearch={handleSearch}
          onDropdownVisibleChange={open => { if (open) loadPopular() }}
          filterOption={false}
          loading={searchLoading}
          style={{ width: 240 }}
          placeholder="输入代码/名称搜索"
          options={stockOptions.length > 0 ? stockOptions : [{ value: 'sh600519', label: '600519 贵州茅台' }]}
        />
        <Radio.Group value={period} onChange={e => setPeriod(e.target.value)} size="small">
          <Radio.Button value="daily">日线</Radio.Button>
          <Radio.Button value="minute">1分钟</Radio.Button>
        </Radio.Group>
        {period === 'daily' && (
          <Radio.Group value={days} onChange={e => setDays(e.target.value)} size="small">
            <Radio.Button value={60}>60天</Radio.Button>
            <Radio.Button value={120}>120天</Radio.Button>
            <Radio.Button value={250}>1年</Radio.Button>
            <Radio.Button value={500}>2年</Radio.Button>
          </Radio.Group>
        )}
        {period === 'daily' && (
          <Radio.Group value={adjust} onChange={e => setAdjust(e.target.value)} size="small">
            <Radio.Button value="hfq">后复权</Radio.Button>
            <Radio.Button value="none">不复权</Radio.Button>
          </Radio.Group>
        )}
        {period === 'minute' && (
          <Select
            value={date}
            onChange={setDate}
            style={{ width: 190 }}
            size="small"
            options={dates.map(d => ({ value: d.date, label: `${d.date} (${d.count}只)` }))}
          />
        )}
        {period === 'minute' && (
          <Button
            type="primary"
            size="small"
            icon={<ExperimentOutlined />}
            loading={predictLoading}
            onClick={handlePredict}
            ghost
          >
            HF预测
          </Button>
        )}
      </Space>

      <div style={{ position: 'relative', minHeight: 420 }}>
        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(255,255,255,0.7)', zIndex: 10 }}>
            <Spin size="large" />
          </div>
        )}
        {!hasData && !loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 5 }}>
            <Empty description={period === 'daily' ? `${symbol} 无本地日线数据，请先同步` : `${symbol} 在 ${date} 无分钟数据`} />
          </div>
        )}
        <div ref={chartContainerRef} style={{ width: '100%' }} />
      </div>

      {/* Prediction signal card */}
      {predictSignal && (
        <Card size="small" style={{ marginTop: 12 }}>
          <Space size="large">
            <span>
              信号方向：
              <Tag color={predictSignal.direction === '看涨' ? 'red' : 'green'}>
                {predictSignal.direction}
              </Tag>
            </span>
            <span>强度：<b>{predictSignal.strength}%</b></span>
            <span>当前价：<b>{predictSignal.current_price}</b></span>
            <span>目标价：<b style={{ color: predictSignal.direction === '看涨' ? '#ef5350' : '#26a69a' }}>{predictSignal.target_price}</b></span>
            <span>预期涨跌：<b>{predictSignal.change_pct}%</b></span>
          </Space>
        </Card>
      )}
    </div>
  )
}
