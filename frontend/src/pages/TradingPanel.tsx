import { useState, useEffect } from 'react'
import {
  Card, Row, Col, Form, Input, InputNumber, Button, Select, Table, Tag,
  Space, Switch, Divider, message, Modal, Descriptions, Alert,
} from 'antd'
import {
  PlusOutlined, MinusOutlined, ReloadOutlined,
  PlayCircleOutlined, PauseCircleOutlined,
} from '@ant-design/icons'
import axios from 'axios'

interface Position {
  key: string
  symbol: string
  name: string
  amount: number
  available: number
  cost_price: number
  current_price: number
  pnl: number
  pnl_pct: number
}

interface Order {
  key: string
  order_id: string
  time: string
  symbol: string
  name: string
  side: string
  price: number
  amount: number
  filled: number
  status: string
}

export default function TradingPanel() {
  const [form] = Form.useForm()
  const [orderSide, setOrderSide] = useState<'buy' | 'sell'>('buy')
  const [loading, setLoading] = useState(false)
  const [positions, setPositions] = useState<Position[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [connected, setConnected] = useState(false)
  const [balance, setBalance] = useState<any>(null)
  const [strategyRunning, setStrategyRunning] = useState(false)
  const [riskConfig, setRiskConfig] = useState<any>({
    max_order_amount: 100000,
    max_daily_trades: 50,
    max_position_pct: 0.2,
    filter_limit_up: true,
    circuit_breaker_loss: -0.05,
  })

  useEffect(() => {
    fetchStatus()
  }, [])

  const fetchStatus = async () => {
    try {
      const [balRes, posRes, ordRes, riskRes] = await Promise.allSettled([
        axios.get('/api/trade/balance'),
        axios.get('/api/trade/positions'),
        axios.get('/api/trade/orders'),
        axios.get('/api/trade/risk/config'),
      ])
      if (balRes.status === 'fulfilled') {
        setBalance(balRes.value.data)
        setConnected(true)
      }
      if (posRes.status === 'fulfilled') setPositions(posRes.value.data)
      if (ordRes.status === 'fulfilled') setOrders(ordRes.value.data)
      if (riskRes.status === 'fulfilled') setRiskConfig(riskRes.value.data)
    } catch {
      // broker not connected
    }
  }

  const connectBroker = async () => {
    setLoading(true)
    try {
      await axios.post('/api/trade/connect')
      message.success('券商连接成功')
      setConnected(true)
      fetchStatus()
    } catch {
      message.error('连接失败，请检查配置')
    }
    setLoading(false)
  }

  const submitOrder = async (values: any) => {
    setLoading(true)
    try {
      const res = await axios.post('/api/trade/order', {
        symbol: values.symbol,
        side: orderSide,
        price: values.price,
        amount: values.amount,
      })
      message.success(`委托已提交: ${res.data.order_id}`)
      form.resetFields()
      fetchStatus()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '下单失败')
    }
    setLoading(false)
  }

  const cancelOrder = async (orderId: string) => {
    try {
      await axios.post(`/api/trade/cancel/${orderId}`)
      message.success('撤单成功')
      fetchStatus()
    } catch {
      message.error('撤单失败')
    }
  }

  const toggleStrategy = async () => {
    const action = strategyRunning ? 'stop' : 'start'
    try {
      await axios.post(`/api/trade/strategy/${action}`)
      setStrategyRunning(!strategyRunning)
      message.success(`策略已${strategyRunning ? '停止' : '启动'}`)
    } catch {
      message.error('操作失败')
    }
  }

  const saveRiskConfig = async (values: any) => {
    try {
      await axios.put('/api/trade/risk/config', values)
      message.success('风控配置已保存')
    } catch {
      message.error('保存失败')
    }
  }

  return (
    <div>
      <h2>实盘交易</h2>

      {!connected && (
        <Alert
          message="券商未连接"
          description="请先连接券商以进行交易"
          type="warning"
          showIcon
          action={<Button size="small" onClick={connectBroker} loading={loading}>连接</Button>}
          style={{ marginBottom: 16 }}
        />
      )}

      <Row gutter={16}>
        {/* 左侧：下单 + 资金 */}
        <Col xs={24} lg={8}>
          <Card title="账户资金" size="small" style={{ marginBottom: 16 }}>
            {balance ? (
              <Descriptions column={1} size="small">
                <Descriptions.Item label="总资产">¥{balance.total?.toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="可用资金">¥{balance.available?.toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="持仓市值">¥{balance.market_value?.toLocaleString()}</Descriptions.Item>
              </Descriptions>
            ) : (
              <div style={{ color: '#999' }}>未连接</div>
            )}
          </Card>

          <Card title="手动下单">
            <Form form={form} layout="vertical" onFinish={submitOrder}>
              <Form.Item label="股票代码" name="symbol" rules={[{ required: true, message: '请输入代码' }]}>
                <Input placeholder="如 600519" />
              </Form.Item>
              <Row gutter={8}>
                <Col span={12}>
                  <Form.Item label="价格" name="price" rules={[{ required: true, message: '请输入价格' }]}>
                    <InputNumber style={{ width: '100%' }} min={0} step={0.01} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item label="数量" name="amount" rules={[{ required: true, message: '请输入数量' }]}>
                    <InputNumber style={{ width: '100%' }} min={100} step={100} />
                  </Form.Item>
                </Col>
              </Row>
              <Space style={{ width: '100%' }}>
                <Button
                  type="primary"
                  danger
                  icon={<PlusOutlined />}
                  onClick={() => setOrderSide('buy')}
                  htmlType="submit"
                  loading={loading}
                  style={{ flex: 1 }}
                >
                  买入
                </Button>
                <Button
                  type="primary"
                  style={{ flex: 1, background: '#52c41a', borderColor: '#52c41a' }}
                  icon={<MinusOutlined />}
                  onClick={() => setOrderSide('sell')}
                  htmlType="submit"
                  loading={loading}
                >
                  卖出
                </Button>
              </Space>
            </Form>
          </Card>
        </Col>

        {/* 中间：持仓 */}
        <Col xs={24} lg={10}>
          <Card
            title="当前持仓"
            extra={<Button icon={<ReloadOutlined />} onClick={fetchStatus} size="small">刷新</Button>}
          >
            <Table
              dataSource={positions}
              rowKey="symbol"
              size="small"
              pagination={false}
              columns={[
                { title: '代码', dataIndex: 'symbol', width: 90 },
                { title: '名称', dataIndex: 'name', width: 80 },
                { title: '数量', dataIndex: 'amount', width: 70 },
                { title: '成本', dataIndex: 'cost_price', width: 80 },
                { title: '现价', dataIndex: 'current_price', width: 80 },
                {
                  title: '盈亏', dataIndex: 'pnl_pct', width: 80,
                  render: (v: number) => (
                    <Tag color={v >= 0 ? 'red' : 'green'}>
                      {v >= 0 ? '+' : ''}{(v * 100).toFixed(2)}%
                    </Tag>
                  ),
                },
              ]}
            />
          </Card>

          <Card title="今日委托" style={{ marginTop: 16 }}>
            <Table
              dataSource={orders}
              rowKey="order_id"
              size="small"
              pagination={false}
              columns={[
                { title: '时间', dataIndex: 'time', width: 100 },
                { title: '代码', dataIndex: 'symbol', width: 80 },
                {
                  title: '方向', dataIndex: 'side', width: 60,
                  render: (v: string) => <Tag color={v === 'buy' ? 'red' : 'green'}>{v === 'buy' ? '买' : '卖'}</Tag>,
                },
                { title: '价格', dataIndex: 'price', width: 70 },
                { title: '数量', dataIndex: 'amount', width: 70 },
                {
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (v: string) => {
                    const colorMap: Record<string, string> = {
                      pending: 'default', submitted: 'processing',
                      filled: 'success', cancelled: 'warning', partial_fill: 'processing',
                    }
                    return <Tag color={colorMap[v] || 'default'}>{v}</Tag>
                  },
                },
                {
                  title: '', width: 60,
                  render: (_: any, record: Order) =>
                    record.status === 'pending' || record.status === 'submitted' ? (
                      <Button size="small" danger onClick={() => cancelOrder(record.order_id)}>撤</Button>
                    ) : null,
                },
              ]}
            />
          </Card>
        </Col>

        {/* 右侧：策略 + 风控 */}
        <Col xs={24} lg={6}>
          <Card title="自动策略" size="small" style={{ marginBottom: 16 }}>
            <Space direction="vertical" style={{ width: '100%' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span>策略运行</span>
                <Switch
                  checked={strategyRunning}
                  onChange={toggleStrategy}
                  checkedChildren={<PlayCircleOutlined />}
                  unCheckedChildren={<PauseCircleOutlined />}
                />
              </div>
              <Tag color={strategyRunning ? 'green' : 'default'}>
                {strategyRunning ? '运行中' : '已停止'}
              </Tag>
            </Space>
          </Card>

          <Card title="风控配置" size="small">
            <Form layout="vertical" size="small" onFinish={saveRiskConfig} initialValues={riskConfig}>
              <Form.Item label="单笔最大金额" name="max_order_amount">
                <InputNumber style={{ width: '100%' }} min={1000} step={10000} />
              </Form.Item>
              <Form.Item label="日最大交易次数" name="max_daily_trades">
                <InputNumber style={{ width: '100%' }} min={1} max={500} />
              </Form.Item>
              <Form.Item label="单票最大仓位" name="max_position_pct">
                <InputNumber style={{ width: '100%' }} min={0.01} max={1} step={0.05} addonAfter="%" />
              </Form.Item>
              <Form.Item label="过滤涨停板" name="filter_limit_up" valuePropName="checked">
                <Switch />
              </Form.Item>
              <Form.Item label="熔断线（日亏损）" name="circuit_breaker_loss">
                <InputNumber style={{ width: '100%' }} min={-1} max={0} step={0.01} />
              </Form.Item>
              <Button type="primary" htmlType="submit" block>保存配置</Button>
            </Form>
          </Card>
        </Col>
      </Row>
    </div>
  )
}
