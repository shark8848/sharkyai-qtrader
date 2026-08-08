import { useState } from 'react'
import { Card, Select, Button, Space, Form, message } from 'antd'
import { CloudSyncOutlined } from '@ant-design/icons'
import { startSync } from '../../api/data'

const SOURCES = [
  { value: 'akshare', label: 'AKShare（聚合）' },
  { value: 'sina', label: 'Sina（新浪）' },
  { value: 'eastmoney', label: '东方财富' },
  { value: 'baostock', label: 'Baostock' },
]

const MARKETS = [
  { value: 'all', label: '全部 A 股' },
  { value: 'csi300', label: '沪深300' },
  { value: 'csi500', label: '中证500' },
  { value: 'sh50', label: '上证50' },
]

const FREQS = [
  { value: 'daily', label: '日线' },
  { value: '1min', label: '1分钟' },
  { value: '5min', label: '5分钟' },
]

const TARGETS = [
  { value: 'qlib_bin', label: 'Qlib .bin（训练用）' },
  { value: 'parquet', label: 'Parquet' },
  { value: 'sqlite', label: 'SQLite 缓存' },
]

export default function SyncForm({ onStarted }: { onStarted?: () => void }) {
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (values: any) => {
    setLoading(true)
    try {
      const res = await startSync({
        source_id: values.source_id,
        market: values.market,
        freq: values.freq,
        target: values.target,
      })
      if (res.error) {
        message.warning(res.error)
      } else {
        message.success('同步任务已启动')
        onStarted?.()
      }
    } catch {
      message.error('启动同步失败')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Card title="新建同步任务" size="small" style={{ marginBottom: 16 }}>
      <Form layout="inline" onFinish={handleSubmit} initialValues={{ source_id: 'akshare', market: 'all', freq: 'daily', target: 'qlib_bin' }}>
        <Form.Item name="source_id" label="数据源">
          <Select options={SOURCES} style={{ width: 160 }} />
        </Form.Item>
        <Form.Item name="market" label="市场">
          <Select options={MARKETS} style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="freq" label="频率">
          <Select options={FREQS} style={{ width: 110 }} />
        </Form.Item>
        <Form.Item name="target" label="目标">
          <Select options={TARGETS} style={{ width: 180 }} />
        </Form.Item>
        <Form.Item>
          <Button type="primary" htmlType="submit" icon={<CloudSyncOutlined />} loading={loading}>
            启动
          </Button>
        </Form.Item>
      </Form>
    </Card>
  )
}
