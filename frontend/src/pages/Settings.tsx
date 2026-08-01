import { useState, useEffect } from 'react'
import { Card, Form, Input, Select, Button, message, Alert, Descriptions } from 'antd'
import axios from 'axios'

export default function Settings() {
  const [config, setConfig] = useState<any>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchConfig()
  }, [])

  const fetchConfig = async () => {
    try {
      const res = await axios.get('/api/data/sources')
      // Just fetch what we have from backend health
      const healthRes = await axios.get('/api/health')
      setConfig(healthRes.data)
    } catch {
      // ignore
    }
  }

  const saveDataConfig = async (values: any) => {
    setLoading(true)
    try {
      await axios.put('/api/data/source', null, { params: { source_id: values.default_source } })
      message.success('数据源配置已保存')
    } catch {
      message.error('保存失败')
    }
    setLoading(false)
  }

  return (
    <div>
      <h2>系统设置</h2>

      <Card title="系统信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2}>
          <Descriptions.Item label="应用名称">QTrader</Descriptions.Item>
          <Descriptions.Item label="版本">0.1.0</Descriptions.Item>
          <Descriptions.Item label="后端地址">http://localhost:8000</Descriptions.Item>
          <Descriptions.Item label="数据目录">~/.qtrader/data</Descriptions.Item>
          <Descriptions.Item label="Qlib 数据">~/.qlib/qlib_data/cn_data</Descriptions.Item>
          <Descriptions.Item label="数据库">SQLite</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="数据源配置" style={{ marginBottom: 16 }}>
        <Form layout="vertical" onFinish={saveDataConfig} initialValues={{ default_source: 'akshare' }}>
          <Form.Item label="默认数据源" name="default_source">
            <Select
              options={[
                { value: 'akshare', label: 'AKShare（A股全量数据）' },
                { value: 'qlib', label: 'Qlib 本地数据' },
              ]}
            />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>保存</Button>
        </Form>
      </Card>

      <Card title="券商配置" style={{ marginBottom: 16 }}>
        <Alert
          message="交易配置说明"
          description="券商配置通过环境变量或 .env 文件设置，前缀为 QTRADER_。支持的变量：QTRADER_BROKER_TYPE、QTRADER_EASTMONEY_GATEWAY、QTRADER_EASTMONEY_TOKEN"
          type="info"
          showIcon
        />
        <Form layout="vertical" style={{ marginTop: 16 }} initialValues={{ broker_type: 'sim' }}>
          <Form.Item label="券商类型" name="broker_type">
            <Select
              options={[
                { value: 'sim', label: '模拟交易（SimBroker）' },
                { value: 'eastmoney', label: '东方财富' },
              ]}
            />
          </Form.Item>
          <Form.Item label="网关地址" name="gateway">
            <Input placeholder="jvQuant 网关地址（可选）" />
          </Form.Item>
          <Form.Item label="Token" name="token">
            <Input.Password placeholder="交易 Token（可选）" />
          </Form.Item>
          <Button type="primary" htmlType="submit">保存（需重启后端）</Button>
        </Form>
      </Card>

    </div>
  )
}
