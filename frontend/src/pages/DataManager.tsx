import { useState, useEffect, useRef } from 'react'
import { Tabs, Card, Select, Button, Space, Tag, message, Progress, Empty } from 'antd'
import {
  SyncOutlined,
  CloudSyncOutlined,
  LineChartOutlined,
  SwapOutlined,
  DatabaseOutlined,
  AppstoreOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons'
import axios from 'axios'
import StockChart from '../components/StockChart'
import SourceCard from '../components/data/SourceCard'
import SyncForm from '../components/data/SyncForm'
import SyncTaskList from '../components/data/SyncTaskList'
import DatasetCard from '../components/data/DatasetCard'
import AutoSyncPanel from '../components/data/AutoSyncPanel'
import {
  fetchSources,
  switchSource as apiSwitchSource,
  startQlibSync,
  fetchQlibSyncStatus,
  startMinuteSync,
  fetchMinuteSyncStatus,
  startConvert1min,
  fetchConvertStatus,
  fetchDatasets,
} from '../api/data'

interface DataSource {
  id: string
  name: string
  active: boolean
  capabilities: string[]
  data_format: string
}

export default function DataManager() {
  const [tab, setTab] = useState('sources')
  const [sources, setSources] = useState<DataSource[]>([])
  const [activeSource, setActiveSource] = useState('')
  const [datasets, setDatasets] = useState<any[]>([])

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
    fetchSources().then(data => {
      setSources(data)
      const active = data.find((s: DataSource) => s.active)
      if (active) setActiveSource(active.id)
    })
    fetchDatasets().then(data => setDatasets(data)).catch(() => {})
  }, [])

  const switchSource = async (sourceId: string) => {
    await apiSwitchSource(sourceId)
    setActiveSource(sourceId)
    message.success(`已切换查询默认源到 ${sourceId}`)
  }

  // === 同步轮询 ===
  const startQlibSyncClick = async () => {
    try {
      const res = await startQlibSync('all')
      if (res.error) {
        message.warning(res.error)
        return
      }
      message.info('日线同步任务已启动')
      syncPollRef.current = setInterval(pollSyncStatus, 2000)
      pollSyncStatus()
    } catch {
      message.error('启动同步失败')
    }
  }

  const pollSyncStatus = async () => {
    try {
      const res = await fetchQlibSyncStatus()
      setSyncStatus(res)
      if (res.status === 'done' || res.status === 'error') {
        if (syncPollRef.current) clearInterval(syncPollRef.current)
        syncPollRef.current = null
        if (res.status === 'done') message.success(res.message)
        else message.error(res.message)
        // 刷新数据集
        fetchDatasets().then(d => setDatasets(d)).catch(() => {})
      }
    } catch { /* ignore */ }
  }

  // 页面加载时检查运行中的任务
  useEffect(() => {
    const initPoll = async () => {
      try {
        const res = await fetchQlibSyncStatus()
        setSyncStatus(res)
        if (res.status === 'running' && !syncPollRef.current) {
          syncPollRef.current = setInterval(pollSyncStatus, 2000)
        }
      } catch { /* ignore */ }
      try {
        const res2 = await fetchMinuteSyncStatus()
        setMinSyncStatus(res2)
        if (res2.status === 'running' && !minSyncPollRef.current) {
          minSyncPollRef.current = setInterval(pollMinSyncStatus, 2000)
        }
      } catch { /* ignore */ }
      try {
        const res3 = await fetchConvertStatus()
        setConvertStatus(res3)
        if (res3.status === 'running' && !convertPollRef.current) {
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

  const startMinuteSyncClick = async () => {
    try {
      const res = await startMinuteSync('all', '1')
      if (res.error) {
        message.warning(res.error)
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
      const res = await fetchMinuteSyncStatus()
      setMinSyncStatus(res)
      if (res.status === 'done' || res.status === 'error') {
        if (minSyncPollRef.current) clearInterval(minSyncPollRef.current)
        minSyncPollRef.current = null
        if (res.status === 'done') message.success(res.message)
        else if (res.status === 'error') message.error(res.message)
      }
    } catch { /* ignore */ }
  }

  const startConvertClick = async () => {
    try {
      const res = await startConvert1min()
      if (res.error) {
        message.warning(res.error)
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
      const res = await fetchConvertStatus()
      setConvertStatus(res)
      if (res.status === 'done' || res.status === 'error') {
        if (convertPollRef.current) clearInterval(convertPollRef.current)
        convertPollRef.current = null
        if (res.status === 'done') message.success(res.message)
        else if (res.status === 'error') message.error(res.message)
      }
    } catch { /* ignore */ }
  }

  const renderSyncProgress = (status: any) => {
    if (!status) return null
    return (
      <div style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13, marginBottom: 4 }}>
          <span style={{ fontWeight: 500 }}>
            已同步 {status.overall_synced}/{(status.total_stocks || 0) + (status.skip_stocks || 0)} 只
          </span>
          <span style={{ color: '#1677ff' }}>{status.overall_pct}%</span>
        </div>
        <Progress
          percent={status.overall_pct}
          status={status.status === 'error' ? 'exception' : status.status === 'done' ? 'success' : status.status === 'running' ? 'active' : 'normal'}
          size="small"
          showInfo={false}
        />
        {status.message && status.status !== 'idle' && (
          <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{status.message}</div>
        )}
      </div>
    )
  }

  return (
    <div>
      <h2>数据管理</h2>

      <Tabs
        activeKey={tab}
        onChange={setTab}
        items={[
          {
            key: 'sources',
            label: (
              <span>
                <DatabaseOutlined /> 数据源
              </span>
            ),
            children: (
              <div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
                  {sources.map(s => (
                    <SourceCard key={s.id} source={s} onSwitch={switchSource} onToggle={() => {}} />
                  ))}
                </div>
                <Card size="small" style={{ marginTop: 12 }}>
                  <p style={{ margin: 0, fontSize: 13, color: '#888' }}>
                    多源并存：所有数据源同时可用，可分别作为同步/训练的渠道。设置"查询默认"仅影响不带
                    source 参数的数据查询接口。
                  </p>
                </Card>
              </div>
            ),
          },
          {
            key: 'sync',
            label: (
              <span>
                <CloudSyncOutlined /> 同步任务
              </span>
            ),
            children: (
              <div>
                <SyncForm onStarted={() => {}} />
                <SyncTaskList />
              </div>
            ),
          },
          {
            key: 'datasets',
            label: (
              <span>
                <AppstoreOutlined /> 数据集
              </span>
            ),
            children: (
              <div>
                {datasets.length === 0 ? (
                  <Empty description="暂无数据集。完成一次同步后，这里会显示可用的数据集（含覆盖度与新鲜度）" />
                ) : (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 12 }}>
                    {datasets.map(d => (
                      <DatasetCard key={d.dataset_id} dataset={d} />
                    ))}
                  </div>
                )}
              </div>
            ),
          },
          {
            key: 'autosync',
            label: (
              <span>
                <ClockCircleOutlined /> 自动同步
              </span>
            ),
            children: <AutoSyncPanel />,
          },
        ]}
      />

      {/* 快速操作区：保留传统日线/分钟/转换入口 */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        <Card title="日线数据同步" size="small" extra={<Tag color="blue">Qlib .bin</Tag>}>
          <p style={{ fontSize: 13, color: '#888', margin: '0 0 4px' }}>全市场日K线 → Qlib 二进制（训练用）</p>
          {syncStatus?.data_start && (
            <p style={{ fontSize: 12, color: '#aaa', margin: '0 0 12px' }}>
              数据范围：{syncStatus.data_start} ~ {syncStatus.data_end}（{syncStatus.data_days} 个交易日）
            </p>
          )}
          <Button type="primary" icon={<SyncOutlined spin={syncStatus?.status === 'running'} />} onClick={startQlibSyncClick} loading={syncStatus?.status === 'running'} block>
            同步日线数据
          </Button>
          {renderSyncProgress(syncStatus)}
        </Card>

        <Card title="分钟数据同步" size="small" extra={<Tag color="purple">Parquet</Tag>}>
          <p style={{ fontSize: 13, color: '#888', margin: '0 0 4px' }}>1分钟K线 → Parquet 存储</p>
          {minSyncStatus?.data_start && (
            <p style={{ fontSize: 12, color: '#aaa', margin: '0 0 12px' }}>
              数据范围：{minSyncStatus.data_start} ~ {minSyncStatus.data_end}
            </p>
          )}
          <Button type="primary" icon={<LineChartOutlined spin={minSyncStatus?.status === 'running'} />} onClick={startMinuteSyncClick} loading={minSyncStatus?.status === 'running'} block>
            同步分钟数据
          </Button>
          {renderSyncProgress(minSyncStatus)}
          <div style={{ marginTop: 12, borderTop: '1px solid #f0f0f0', paddingTop: 12 }}>
            <Button icon={<SwapOutlined spin={convertStatus?.status === 'running'} />} onClick={startConvertClick} loading={convertStatus?.status === 'running'} block>
              转换为 Qlib 1min（高频训练用）
            </Button>
            {convertStatus?.qlib_stocks > 0 && convertStatus.status !== 'running' && (
              <p style={{ fontSize: 12, color: '#aaa', margin: '8px 0 0' }}>
                已转换: {convertStatus.qlib_stocks} 只，{convertStatus.qlib_bars || 0} 个时间戳
              </p>
            )}
            {convertStatus && convertStatus.status === 'running' && (
              <div style={{ marginTop: 8 }}>
                <Progress percent={convertStatus.progress} status="active" size="small" />
                <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>{convertStatus.message}</div>
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card title="行情图表" size="small" style={{ marginTop: 16 }}>
        <StockChart />
      </Card>
    </div>
  )
}
