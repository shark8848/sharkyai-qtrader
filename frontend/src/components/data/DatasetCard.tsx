import { Card, Tag, Progress, Space, Button, Tooltip } from 'antd'
import { ReloadOutlined, WarningOutlined, CheckCircleOutlined } from '@ant-design/icons'
import { resyncDataset } from '../../api/data'

interface Dataset {
  dataset_id: string
  source_id: string
  market: string
  freq: string
  storage: string
  stock_count: number
  coverage_pct: number
  start_date: string
  end_date: string
  synced_at: string
  status: string
  stale?: boolean
}

const STORAGE_TAGS: Record<string, string> = {
  qlib_bin: 'blue',
  parquet: 'purple',
  sqlite: 'cyan',
}

export default function DatasetCard({ dataset }: { dataset: Dataset }) {
  const handleResync = async () => {
    await resyncDataset(dataset.dataset_id)
  }

  return (
    <Card
      size="small"
      style={{ width: '100%' }}
      title={
        <Space>
          <code style={{ fontSize: 13 }}>{dataset.market}</code>
          <Tag color="geekblue">{dataset.freq}</Tag>
          <Tag color={STORAGE_TAGS[dataset.storage] || 'default'}>{dataset.storage}</Tag>
        </Space>
      }
      extra={
        <Space size={4}>
          {dataset.stale ? (
            <Tooltip title="数据已过期，建议重新同步">
              <Tag color="warning" icon={<WarningOutlined />}>过期</Tag>
            </Tooltip>
          ) : (
            <Tag color="success" icon={<CheckCircleOutlined />}>最新</Tag>
          )}
          <Button size="small" icon={<ReloadOutlined />} onClick={handleResync}>
            重同步
          </Button>
        </Space>
      }
    >
      <div style={{ marginBottom: 6, fontSize: 13 }}>
        <Space split="·">
          <span>源: <b>{dataset.source_id}</b></span>
          <span>股票: <b>{dataset.stock_count}</b></span>
          <span>
            {dataset.start_date} ~ {dataset.end_date}
          </span>
        </Space>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Progress
          percent={Math.round(dataset.coverage_pct)}
          size="small"
          style={{ flex: 1 }}
          status={dataset.coverage_pct > 95 ? 'success' : dataset.coverage_pct > 80 ? 'active' : 'exception'}
        />
        <span style={{ fontSize: 12, color: '#999', whiteSpace: 'nowrap' }}>
          同步于 {dataset.synced_at?.slice(5, 16) || '—'}
        </span>
      </div>
    </Card>
  )
}
