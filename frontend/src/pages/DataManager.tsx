import { useState, useEffect } from 'react'
import { Card, Select, Table, Input, Button, Space, Tag, message } from 'antd'
import { SyncOutlined, SearchOutlined } from '@ant-design/icons'
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

  return (
    <div>
      <h2>数据管理</h2>

      <Card title="数据源" style={{ marginBottom: 16 }}>
        <Space>
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
          pagination={{ pageSize: 20 }}
          size="small"
        />
      </Card>
    </div>
  )
}
