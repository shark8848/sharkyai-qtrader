import { useState, useEffect, useRef } from 'react'
import { Card, Select, Button, Space, Tag, message, Progress } from 'antd'
import { SyncOutlined, CloudSyncOutlined, LineChartOutlined, SwapOutlined } from '@ant-design/icons'
import axios from 'axios'
import StockChart from '../components/StockChart'

interface DataSource {
  id: string
  name: string
  active: boolean
}

export default function DataManager() {
  const [sources, setSources] = useState<DataSource[]>([])
  const [activeSource, setActiveSource] = useState('')

  // Qlib 同步状态
  const [syncStatus, setSyncStatus] = useState<any>(null)
  const syncPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 分钟数据同步状态
  const [minSyncStatus, setMinSyncStatus] = useState<any>(null)
  const minSyncPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Qlib 1min 转换状态
  const [convertStatus, setConvertStatus] = useState<any>(null)
  const convertPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    fetchSources()
  }, [])

  const fetchSources = async () => {
    const res = await axios.get('/api/data/sources')
    setSources(res.data)
    const active = res.data.find((s: DataSource) => s.active)
    if (active) setActiveSource(active.id)
  }

  const switchSource = async (sourceId: string) => {
    await axios.put('/api/data/source', null, { params: { source_id: sourceId } })
    setActiveSource(sourceId)
    message.success(`已切换到 ${sourceId}`)
  }

  // === Qlib 同步 ===
  const startQlibSync = async () => {
    try {
      const res = await axios.post('/api/data/sync_qlib', null, { params: { market: 'all' } })
      if (res.data.error) {
        message.warning(res.data.error)
        return
      }
      message.info('同步任务已启动')
      // 开始轮询进度
      syncPollRef.current = setInterval(pollSyncStatus, 2000)
      pollSyncStatus()
    } catch {
      message.error('启动同步失败')
    }
  }

  const pollSyncStatus = async () => {
    try {
      const res = await axios.get('/api/data/sync_qlib/status')
      setSyncStatus(res.data)
      if (res.data.status === 'done' || res.data.status === 'error') {
        if (syncPollRef.current) clearInterval(syncPollRef.current)
        syncPollRef.current = null
        if (res.data.status === 'done') message.success(res.data.message)
        else message.error(res.data.message)
      }
    } catch { /* ignore */ }
  }

  // 页面加载时检查是否有正在运行的同步，自动启动轮询
  useEffect(() => {
    const initPoll = async () => {
      try {
        const res = await axios.get('/api/data/sync_qlib/status')
        setSyncStatus(res.data)
        if (res.data.status === 'running' && !syncPollRef.current) {
          syncPollRef.current = setInterval(pollSyncStatus, 2000)
        }
      } catch { /* ignore */ }
      try {
        const res2 = await axios.get('/api/data/sync_minute/status')
        setMinSyncStatus(res2.data)
        if (res2.data.status === 'running' && !minSyncPollRef.current) {
          minSyncPollRef.current = setInterval(pollMinSyncStatus, 2000)
        }
      } catch { /* ignore */ }
      try {
        const res3 = await axios.get('/api/data/convert_1min/status')
        setConvertStatus(res3.data)
        if (res3.data.status === 'running' && !convertPollRef.current) {
          convertPollRef.current = setInterval(pollConvertStatus, 2000)
        }
      } catch { /* ignore */ }
    }
    initPoll()
    return () => {
      if (syncPollRef.current) clearInterval(syncPollRef.current)
      if (minSyncPollRef.current) clearInterval(minSyncPollRef.current)
      if (convertPollRef.current) clearInterval(convertPollRef.current)
    }
  }, [])

  // === 分钟数据同步 ===
  const startMinuteSync = async () => {
    try {
      const res = await axios.post('/api/data/sync_minute', null, { params: { market: 'all', period: '1' } })
      if (res.data.error) {
        message.warning(res.data.error)
        return
      }
      message.info('分钟数据同步已启动')
      minSyncPollRef.current = setInterval(pollMinSyncStatus, 2000)
      pollMinSyncStatus()
    } catch {
      message.error('启动分钟同步失败')
    }
  }

  const pollMinSyncStatus = async () => {
    try {
      const res = await axios.get('/api/data/sync_minute/status')
      setMinSyncStatus(res.data)
      if (res.data.status === 'done' || res.data.status === 'error') {
        if (minSyncPollRef.current) clearInterval(minSyncPollRef.current)
        minSyncPollRef.current = null
        if (res.data.status === 'done') message.success(res.data.message)
        else if (res.data.status === 'error') message.error(res.data.message)
      }
    } catch { /* ignore */ }
  }

  // === Qlib 1min 转换 ===
  const startConvert = async () => {
    try {
      const res = await axios.post('/api/data/convert_1min')
      if (res.data.error) {
        message.warning(res.data.error)
        return
      }
      message.info('Parquet → Qlib 1min 转换已启动')
      convertPollRef.current = setInterval(pollConvertStatus, 2000)
      pollConvertStatus()
    } catch {
      message.error('启动转换失败')
    }
  }

  const pollConvertStatus = async () => {
    try {
      const res = await axios.get('/api/data/convert_1min/status')
      setConvertStatus(res.data)
      if (res.data.status === 'done' || res.data.status === 'error') {
        if (convertPollRef.current) clearInterval(convertPollRef.current)
        convertPollRef.current = null
        if (res.data.status === 'done') message.success(res.data.message)
        else if (res.data.status === 'error') message.error(res.data.message)
      }
    } catch { /* ignore */ }
  }

  return (
    <div>
      <h2>数据管理</h2>

      <Card title="数据源" style={{ marginBottom: 16 }}>
        <Space wrap>
          <span>当前数据源：</span>
          <Select
            value={activeSource}
            onChange={switchSource}
            style={{ width: 200 }}
            options={sources.map(s => ({ value: s.id, label: `${s.name} ${s.active ? '(当前)' : ''}` }))}
          />
          <Button icon={<SyncOutlined />} onClick={fetchSources}>刷新</Button>
        </Space>
      </Card>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
        <Card title="日线数据同步" extra={<Tag color="blue">Qlib .bin</Tag>}>
          <p style={{ fontSize: 13, color: '#888', margin: '0 0 4px' }}>
            全市场日K线 → Qlib 二进制格式，用于模型训练与预测
          </p>
          {syncStatus?.data_start && (
            <p style={{ fontSize: 12, color: '#aaa', margin: '0 0 12px' }}>
              数据范围：{syncStatus.data_start} ~ {syncStatus.data_end}（{syncStatus.data_days} 个交易日）
            </p>
          )}
          <Button
            type="primary"
            icon={<CloudSyncOutlined spin={syncStatus?.status === 'running'} />}
            onClick={startQlibSync}
            loading={syncStatus?.status === 'running'}
            block
          >
            同步日线数据
          </Button>
          {syncStatus && (
            <div style={{ marginTop: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                <span style={{ fontWeight: 500 }}>已同步 {syncStatus.overall_synced}/{(syncStatus.total_stocks || 0) + (syncStatus.skip_stocks || 0)} 只</span>
                <span style={{ color: '#1677ff' }}>{syncStatus.overall_pct}%</span>
              </div>
              <Progress
                percent={syncStatus.overall_pct}
                status={syncStatus.status === 'error' ? 'exception' : syncStatus.status === 'done' ? 'success' : syncStatus.status === 'running' ? 'active' : 'normal'}
                size="small"
                showInfo={false}
              />
              {syncStatus.status !== 'idle' && (
                <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                  新增 <b style={{ color: '#52c41a' }}>{syncStatus.success_stocks}</b> | 失败 {syncStatus.fail_stocks || 0}
                </div>
              )}
            </div>
          )}
        </Card>

        <Card title="分钟数据同步" extra={<Tag color="blue">Parquet</Tag>}>
          <p style={{ fontSize: 13, color: '#888', margin: '0 0 4px' }}>
            1分钟K线 → Parquet 存储，用于分时浏览与日内因子
          </p>
          {minSyncStatus?.data_start && (
            <p style={{ fontSize: 12, color: '#aaa', margin: '0 0 12px' }}>
              数据范围：{minSyncStatus.data_start} ~ {minSyncStatus.data_end}（{minSyncStatus.data_days} 个交易日）
            </p>
          )}
          <Button
            type="primary"
            icon={<LineChartOutlined spin={minSyncStatus?.status === 'running'} />}
            onClick={startMinuteSync}
            loading={minSyncStatus?.status === 'running'}
            block
          >
            同步分钟数据
          </Button>
          {minSyncStatus && (
            <div style={{ marginTop: 12 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
                <span style={{ fontWeight: 500 }}>已同步 {minSyncStatus.overall_synced}/{(minSyncStatus.total_stocks || 0) + (minSyncStatus.skip_stocks || 0)} 只</span>
                <span style={{ color: '#1677ff' }}>{minSyncStatus.overall_pct}%</span>
              </div>
              <Progress
                percent={minSyncStatus.overall_pct}
                status={minSyncStatus.status === 'error' ? 'exception' : minSyncStatus.status === 'done' ? 'success' : minSyncStatus.status === 'running' ? 'active' : 'normal'}
                size="small"
                showInfo={false}
              />
              {minSyncStatus.status !== 'idle' && (
                <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                  新增 <b style={{ color: '#52c41a' }}>{minSyncStatus.success_stocks}</b> | 失败 {minSyncStatus.fail_stocks || 0}
                </div>
              )}
            </div>
          )}
          {/* Convert to Qlib 1min */}
          <div style={{ marginTop: 16, borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
            <Button
              icon={<SwapOutlined spin={convertStatus?.status === 'running'} />}
              onClick={startConvert}
              loading={convertStatus?.status === 'running'}
              block
            >
              转换为 Qlib 1min（高频训练用）
            </Button>
            {convertStatus?.qlib_stocks > 0 && convertStatus.status !== 'running' && (
              <p style={{ fontSize: 12, color: '#aaa', margin: '8px 0 0' }}>
                已转换: {convertStatus.qlib_stocks} 只股票，{convertStatus.qlib_bars || 0} 个时间戳
              </p>
            )}
            {convertStatus && convertStatus.status === 'running' && (
              <div style={{ marginTop: 8 }}>
                <Progress
                  percent={convertStatus.progress}
                  status="active"
                  size="small"
                />
                <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{convertStatus.message}</div>
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card title="行情图表">
        <StockChart />
      </Card>
    </div>
  )
}
