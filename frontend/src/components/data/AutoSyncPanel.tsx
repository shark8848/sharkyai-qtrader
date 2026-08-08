import { Card, Switch, Descriptions, Tag, Space, Typography } from 'antd'
import { ClockCircleOutlined } from '@ant-design/icons'

const { Text } = Typography

export default function AutoSyncPanel() {
  // 目前由后端 APScheduler 管理（15:30 日线 / 15:35 分钟）
  // 前端仅展示配置说明，开关可后续接入 API
  const enabled = true

  return (
    <Card title="每日自动同步" size="small">
      <Space direction="vertical" style={{ width: '100%' }}>
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="自动同步">
            <Switch checked={enabled} disabled />{' '}
            <Text type="secondary">（由后端 APScheduler 调度）</Text>
          </Descriptions.Item>
          <Descriptions.Item label="日线增量同步">
            <ClockCircleOutlined style={{ color: '#1677ff' }} /> 工作日 <Tag color="blue">15:30</Tag>
            <Text type="secondary">A 股收盘后，全市场日线增量 → Qlib .bin</Text>
          </Descriptions.Item>
          <Descriptions.Item label="分钟同步">
            <ClockCircleOutlined style={{ color: '#722ed1' }} /> 工作日 <Tag color="purple">15:35</Tag>
            <Text type="secondary">1 分钟 K 线 → Parquet</Text>
          </Descriptions.Item>
        </Descriptions>
        <Text type="secondary" style={{ fontSize: 12 }}>
          提示：如需关闭自动同步，可设置环境变量 QTRADER_AUTO_SYNC=false 后重启服务。
        </Text>
      </Space>
    </Card>
  )
}
