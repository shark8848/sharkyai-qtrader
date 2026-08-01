import { useState, useEffect, useRef } from 'react'
import { Card, Select, Table, Input, Button, Space, Tag, message, Progress, Alert } from 'antd'
import { SyncOutlined, SearchOutlined, CloudSyncOutlined } from '@ant-design/icons'
import axios from 'axios'

interface DataSource {
  id: string
  name: string
  active: boolean
}

interface StockItem {
  symbol: string
  name: string
  market: string
  industry: string
}

export default function DataManager() {
  const [sources, setSources] = useState<DataSource[]>([])
  const [activeSource, setActiveSource] = useState('')
  const [stocks, setStocks] = useState<StockItem[]>([])
  const [total, setTotal] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [pagination, setPagination] = useState({ current: 1, pageSize: 20 })

  // Qlib 同步状态
  const [syncStatus, setSyncStatus] = useState<any>(null)
  const syncPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    fetchSources()
  }, [])

  useEffect(() => {
    if (activeSource) fetchStocks()
  }, [activeSource])

  const fetchSources = async () => {
    const res = await axios.get('/api/data/sources')
    setSources(res.data)
    const active = res.data.find((s: DataSource) => s.active)
    if (active) setActiveSource(active.id)
  }

  const fetchStocks = async () => {
    setLoading(true)
    setPagination(prev => ({ ...prev, current: 1 }))
    try {
      const params: any = {}
      if (keyword) params.keyword = keyword
      const res = await axios.get('/api/data/stocks', { params })
      setStocks(res.data.data)
      setTotal(res.data.total)
    } catch {
      message.error('获取股票列表失败')
    }
    setLoading(false)
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

  // 页面加载时检查是否有正在运行的同步
  useEffect(() => {
    pollSyncStatus()
    return () => { if (syncPollRef.current) clearInterval(syncPollRef.current) }
  }, [])

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
          <Button
            type="primary"
            icon={<CloudSyncOutlined spin={syncStatus?.status === 'running'} />}
            onClick={startQlibSync}
            loading={syncStatus?.status === 'running'}
          >
            同步到 Qlib
          </Button>
        </Space>
        {syncStatus && syncStatus.status !== 'idle' && (
          <div style={{ marginTop: 12 }}>
            <Progress
              percent={syncStatus.progress}
              status={syncStatus.status === 'error' ? 'exception' : syncStatus.status === 'done' ? 'success' : 'active'}
              size="small"
            />
            <div style={{ fontSize: 12, color: '#666', marginTop: 4 }}>
              {syncStatus.message}
              {syncStatus.status === 'running' && ` (${syncStatus.done_stocks}/${syncStatus.total_stocks})`}
            </div>
          </div>
        )}
      </Card>

      <Card title={`股票列表 (共 ${total} 只)`}>
        <Space style={{ marginBottom: 16 }}>
          <Input
            placeholder="搜索代码或名称"
            prefix={<SearchOutlined />}
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
            onPressEnter={fetchStocks}
            style={{ width: 300 }}
            allowClear
          />
          <Button type="primary" onClick={fetchStocks}>搜索</Button>
        </Space>
        <Table
          dataSource={stocks}
          rowKey="symbol"
          loading={loading}
          columns={[
            { title: '代码', dataIndex: 'symbol', key: 'symbol' },
            { title: '名称', dataIndex: 'name', key: 'name' },
            {
              title: '市场', dataIndex: 'market', key: 'market',
              render: (v: string) => <Tag color={v === 'SH' ? 'red' : 'blue'}>{v}</Tag>,
            },
            { title: '行业', dataIndex: 'industry', key: 'industry' },
          ]}
          pagination={{
            current: pagination.current,
            pageSize: pagination.pageSize,
            total: total,
            showSizeChanger: true,
            pageSizeOptions: ['10', '20', '50', '100'],
            showTotal: (t) => `共 ${t} 条`,
            onChange: (page, size) => setPagination({ current: page, pageSize: size }),
          }}
          size="small"
        />
      </Card>
    </div>
  )
}
