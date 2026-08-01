import { useState, useEffect } from 'react'
import { Card, Col, Row, Statistic, Table, Tag, Space, Button, Spin, Empty } from 'antd'
import { ArrowUpOutlined, ArrowDownOutlined, ReloadOutlined } from '@ant-design/icons'
import axios from 'axios'

interface Balance {
  total: number
  available: number
  market_value: number
  frozen: number
}

interface Position {
  symbol: string
  name: string
  amount: number
  available: number
  cost_price: number
  current_price: number
  pnl: number
  pnl_pct: number
  market_value: number
}

interface OrderItem {
  order_id: string
  symbol: string
  side: string
  price: number
  amount: number
  filled: number
  status: string
  created_at: string
}

export default function Dashboard() {
  const [balance, setBalance] = useState<Balance | null>(null)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<OrderItem[]>([])
  const [loading, setLoading] = useState(true)
  const [connected, setConnected] = useState(false)
  const [todayPnl, setTodayPnl] = useState(0)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    setLoading(true)
    try {
      const statusRes = await axios.get('/api/trade/status')
      const isConnected = statusRes.data.connected
      setConnected(isConnected)

      if (isConnected) {
        const [balRes, posRes, ordRes, riskRes] = await Promise.allSettled([
          axios.get('/api/trade/balance'),
          axios.get('/api/trade/positions'),
          axios.get('/api/trade/orders'),
          axios.get('/api/trade/risk/stats'),
        ])

        if (balRes.status === 'fulfilled') setBalance(balRes.value.data)
        if (posRes.status === 'fulfilled') setPositions(posRes.value.data)
        if (ordRes.status === 'fulfilled') setOrders(ordRes.value.data)
        if (riskRes.status === 'fulfilled') setTodayPnl(riskRes.value.data.daily_pnl || 0)
      }
    } catch {
      // Backend may not be ready
    }
    setLoading(false)
  }

  const totalPnl = positions.reduce((sum, p) => sum + p.pnl, 0)
  const pnlPct = balance && balance.total > 0 ? (totalPnl / (balance.total - totalPnl)) * 100 : 0

  return (
    <div>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>仪表盘</h2>
        <Space>
          <Tag color={connected ? 'green' : 'default'}>
            {connected ? '已连接' : '未连接'}
          </Tag>
          <Button icon={<ReloadOutlined />} onClick={fetchData} size="small">刷新</Button>
        </Space>
      </Space>

      <Spin spinning={loading}>
        {!connected && !loading ? (
          <Empty description="请先在「实盘交易」页面连接券商" />
        ) : (
          <>
            <Row gutter={[16, 16]}>
              <Col xs={24} sm={12} lg={6}>
                <Card>
                  <Statistic title="总资产" value={balance?.total || 0} prefix="¥" precision={2} />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card>
                  <Statistic
                    title="当日盈亏" value={todayPnl} prefix="¥" precision={2}
                    valueStyle={{ color: todayPnl >= 0 ? '#3f8600' : '#cf1322' }}
                    suffix={todayPnl >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                  />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card>
                  <Statistic title="持仓数量" value={positions.length} suffix="只" />
                </Card>
              </Col>
              <Col xs={24} sm={12} lg={6}>
                <Card>
                  <Statistic
                    title="持仓收益" value={pnlPct} suffix="%" precision={2}
                    valueStyle={{ color: pnlPct >= 0 ? '#3f8600' : '#cf1322' }}
                  />
                </Card>
              </Col>
            </Row>

            <Card title="持仓概览" style={{ marginTop: 16 }}>
              <Table
                dataSource={positions} rowKey="symbol" pagination={false}
                columns={[
                  { title: '代码', dataIndex: 'symbol' },
                  { title: '名称', dataIndex: 'name' },
                  { title: '数量', dataIndex: 'amount' },
                  { title: '成本', dataIndex: 'cost_price', render: (v: number) => v?.toFixed(2) },
                  { title: '现价', dataIndex: 'current_price', render: (v: number) => v?.toFixed(2) },
                  { title: '市值', dataIndex: 'market_value', render: (v: number) => `¥${v?.toLocaleString()}` },
                  {
                    title: '盈亏', dataIndex: 'pnl_pct',
                    render: (v: number) => <Tag color={v >= 0 ? 'red' : 'green'}>{v >= 0 ? '+' : ''}{(v * 100).toFixed(2)}%</Tag>,
                  },
                ]}
              />
            </Card>

            <Card title="最近交易" style={{ marginTop: 16 }}>
              <Table
                dataSource={orders} rowKey="order_id" pagination={false}
                columns={[
                  { title: '时间', dataIndex: 'created_at' },
                  { title: '代码', dataIndex: 'symbol' },
                  {
                    title: '方向', dataIndex: 'side',
                    render: (v: string) => <Tag color={v === 'buy' ? 'red' : 'green'}>{v === 'buy' ? '买入' : '卖出'}</Tag>,
                  },
                  { title: '价格', dataIndex: 'price' },
                  { title: '数量', dataIndex: 'amount' },
                  {
                    title: '状态', dataIndex: 'status',
                    render: (v: string) => {
                      const m: Record<string, string> = { pending: 'default', submitted: 'processing', filled: 'success', cancelled: 'warning', rejected: 'error' }
                      return <Tag color={m[v] || 'default'}>{v}</Tag>
                    },
                  },
                ]}
              />
            </Card>
          </>
        )}
      </Spin>
    </div>
  )
}
