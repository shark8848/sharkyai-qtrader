import { useEffect, useState } from 'react'
import { Card, Table, Tag, Progress, Button, Space } from 'antd'
import { ReloadOutlined } from '@ant-design/icons'
import { fetchSyncJobs } from '../../api/data'

const STATUS_MAP: Record<string, { color: string; text: string }> = {
  pending: { color: 'default', text: '等待中' },
  running: { color: 'processing', text: '运行中' },
  done: { color: 'success', text: '已完成' },
  error: { color: 'error', text: '失败' },
  stopped: { color: 'warning', text: '已停止' },
}

export default function SyncTaskList() {
  const [jobs, setJobs] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  const load = async () => {
    setLoading(true)
    try {
      const data = await fetchSyncJobs()
      setJobs(data)
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [])

  const columns = [
    {
      title: '任务 ID',
      dataIndex: 'job_id',
      key: 'job_id',
      render: (v: string) => <code style={{ fontSize: 12 }}>{v}</code>,
    },
    {
      title: '数据源',
      dataIndex: 'source_id',
      key: 'source_id',
      width: 100,
    },
    {
      title: '市场 / 频率',
      key: 'market_freq',
      width: 140,
      render: (_: any, r: any) => (
        <Space size={4}>
          <Tag>{r.market}</Tag>
          <Tag color="blue">{r.freq}</Tag>
        </Space>
      ),
    },
    {
      title: '目标',
      dataIndex: 'target',
      key: 'target',
      width: 100,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      render: (v: string) => <Tag color={STATUS_MAP[v]?.color}>{STATUS_MAP[v]?.text || v}</Tag>,
    },
    {
      title: '进度',
      dataIndex: 'progress',
      key: 'progress',
      width: 160,
      render: (v: number, r: any) =>
        r.status === 'running' ? <Progress percent={Math.round(v)} size="small" status="active" /> : <Progress percent={Math.round(v)} size="small" />,
    },
    {
      title: '信息',
      dataIndex: 'message',
      key: 'message',
      ellipsis: true,
    },
  ]

  return (
    <Card
      title="同步任务列表"
      size="small"
      extra={
        <Button size="small" icon={<ReloadOutlined />} onClick={load} loading={loading}>
          刷新
        </Button>
      }
    >
      <Table
        rowKey="job_id"
        columns={columns}
        dataSource={jobs}
        size="small"
        pagination={{ pageSize: 8 }}
      />
    </Card>
  )
}
