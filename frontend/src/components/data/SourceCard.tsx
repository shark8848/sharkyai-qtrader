import { Card, Tag, Switch, Button, Space, Tooltip } from 'antd'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ThunderboltOutlined,
  DatabaseOutlined,
} from '@ant-design/icons'

interface SourceInfo {
  id: string
  name: string
  active: boolean
  capabilities: string[]
  data_format: string
  healthy?: boolean
}

const CAP_LABELS: Record<string, { text: string; color: string }> = {
  daily: { text: '日线', color: 'blue' },
  minute: { text: '分钟', color: 'purple' },
  realtime: { text: '实时', color: 'green' },
  financial: { text: '财务', color: 'orange' },
  stock_list: { text: '股票列表', color: 'cyan' },
}

export default function SourceCard({
  source,
  onSwitch,
  onToggle,
}: {
  source: SourceInfo
  onSwitch: (id: string) => void
  onToggle: (id: string, enabled: boolean) => void
}) {
  const healthy = source.healthy !== false

  return (
    <Card
      size="small"
      title={
        <Space>
          <DatabaseOutlined style={{ color: '#1677ff' }} />
          <span>{source.name}</span>
          {source.active && <Tag color="gold">查询默认</Tag>}
        </Space>
      }
      extra={
        <Tag color={healthy ? 'success' : 'error'} icon={healthy ? <CheckCircleOutlined /> : <CloseCircleOutlined />}>
          {healthy ? '正常' : '不可用'}
        </Tag>
      }
      style={{ width: '100%' }}
    >
      <div style={{ marginBottom: 8, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {(source.capabilities || []).map(cap => (
          <Tag key={cap} color={CAP_LABELS[cap]?.color || 'default'}>
            {CAP_LABELS[cap]?.text || cap}
          </Tag>
        ))}
        <Tag>{source.data_format === 'local_bin' ? '本地 .bin' : 'API'}</Tag>
      </div>
      <Space>
        <Button
          size="small"
          type={source.active ? 'primary' : 'default'}
          icon={<ThunderboltOutlined />}
          onClick={() => onSwitch(source.id)}
        >
          {source.active ? '当前默认' : '设为查询默认'}
        </Button>
        <Tooltip title={source.active ? '当前为查询默认源' : '启用/停用数据源'}>
          <Switch size="small" checked={!source.active || true} onChange={v => onToggle(source.id, v)} />
        </Tooltip>
      </Space>
    </Card>
  )
}
