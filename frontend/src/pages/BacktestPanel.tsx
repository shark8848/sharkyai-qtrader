import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Card, Form, Select, DatePicker, Button, Row, Col, Statistic, Table, Tag,
  message, Space, Progress, Badge, Descriptions, Divider,
} from 'antd'
import {
  PlayCircleOutlined, CheckCircleOutlined, CloseCircleOutlined,
  LoadingOutlined, ClockCircleOutlined, ExperimentOutlined,
} from '@ant-design/icons'
import axios from 'axios'
import dayjs from 'dayjs'

const { RangePicker } = DatePicker

interface LogEntry {
  time: string
  step: string
  level: string
}

interface JobStatus {
  job_id: string
  status: string
  progress: number
  current_step: string
  logs: LogEntry[]
  created_at: string
  finished_at: string | null
  error: string | null
  metrics: any
  config: any
}

export default function BacktestPanel() {
  const [loading, setLoading] = useState(false)
  const [activeJob, setActiveJob] = useState<JobStatus | null>(null)
  const [jobList, setJobList] = useState<JobStatus[]>([])
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const logEndRef = useRef<HTMLDivElement>(null)

  const startPolling = useCallback((jobId: string) => {
    if (pollRef.current) clearInterval(pollRef.current)
    pollRef.current = setInterval(async () => {
      try {
        const res = await axios.get(`/api/train/status/${jobId}`)
        setActiveJob(res.data)
        if (res.data.status === 'success' || res.data.status === 'failed') {
          if (pollRef.current) clearInterval(pollRef.current)
          pollRef.current = null
          fetchJobList()
        }
      } catch { /* ignore */ }
    }, 1500)
  }, [])

  useEffect(() => {
    fetchJobList()
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [activeJob?.logs])

  const fetchJobList = async () => {
    try {
      const res = await axios.get('/api/train/jobs')
      setJobList(res.data)
    } catch { /* ignore */ }
  }

  const startTraining = async (values: any) => {
    setLoading(true)
    try {
      const payload = { ...values }
      if (values.train_range) {
        payload.train_range = [values.train_range[0].format('YYYY-MM-DD'), values.train_range[1].format('YYYY-MM-DD')]
        payload.valid_range = [values.valid_range[0].format('YYYY-MM-DD'), values.valid_range[1].format('YYYY-MM-DD')]
        payload.test_range = [values.test_range[0].format('YYYY-MM-DD'), values.test_range[1].format('YYYY-MM-DD')]
      }
      const res = await axios.post('/api/train/start', payload)
      message.success(`训练已启动: ${res.data.job_id}`)
      const jobId = res.data.job_id
      setActiveJob({ job_id: jobId, status: 'pending', progress: 0, current_step: '初始化...', logs: [], created_at: '', finished_at: null, error: null, metrics: null, config: payload })
      startPolling(jobId)
    } catch (err: any) {
      message.error(err.response?.data?.detail || '启动训练失败')
    }
    setLoading(false)
  }

  const statusIcon = (s: string) => {
    switch (s) {
      case 'running': return <LoadingOutlined spin style={{ color: '#1890ff' }} />
      case 'success': return <CheckCircleOutlined style={{ color: '#52c41a' }} />
      case 'failed': return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />
      default: return <ClockCircleOutlined style={{ color: '#999' }} />
    }
  }

  const statusColor = (s: string) => {
    switch (s) {
      case 'running': return 'processing'
      case 'success': return 'success'
      case 'failed': return 'error'
      default: return 'default'
    }
  }

  return (
    <div>
      <h2>训练与回测</h2>

      <Row gutter={16}>
        <Col xs={24} lg={9}>
          <Card title="模型配置">
            <Form layout="vertical" onFinish={startTraining}>
              <Form.Item label="模型类型" name="model_class" initialValue="LGBModel">
                <Select options={[
                  { value: 'LGBModel', label: 'LightGBM' },
                  { value: 'XGBModel', label: 'XGBoost' },
                  { value: 'CatBoostModel', label: 'CatBoost' },
                  { value: 'LinearModel', label: 'Linear' },
                ]} />
              </Form.Item>
              <Form.Item label="因子集" name="handler" initialValue="Alpha158">
                <Select options={[
                  { value: 'Alpha158', label: 'Alpha158' },
                  { value: 'Alpha360', label: 'Alpha360' },
                ]} />
              </Form.Item>
              <Form.Item label="股票池" name="market" initialValue="csi300">
                <Select options={[
                  { value: 'csi300', label: '沪深300' },
                  { value: 'csi500', label: '中证500' },
                  { value: 'csi800', label: '中证800' },
                ]} />
              </Form.Item>
              <Form.Item label="训练集" name="train_range">
                <RangePicker defaultValue={[dayjs('2008-01-01'), dayjs('2014-12-31')]} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item label="验证集" name="valid_range">
                <RangePicker defaultValue={[dayjs('2015-01-01'), dayjs('2016-12-31')]} style={{ width: '100%' }} />
              </Form.Item>
              <Form.Item label="测试集" name="test_range">
                <RangePicker defaultValue={[dayjs('2017-01-01'), dayjs('2020-08-01')]} style={{ width: '100%' }} />
              </Form.Item>
              <Button
                type="primary" htmlType="submit" icon={<PlayCircleOutlined />}
                loading={loading || activeJob?.status === 'running'} block
              >
                开始训练
              </Button>
            </Form>
          </Card>
        </Col>

        <Col xs={24} lg={15}>
          {activeJob && (
            <Card
              title={
                <Space>
                  <ExperimentOutlined />
                  训练进度
                  <Badge status={statusColor(activeJob.status) as any} text={activeJob.status} />
                </Space>
              }
              style={{ marginBottom: 16 }}
            >
              <Progress
                percent={activeJob.progress}
                status={activeJob.status === 'failed' ? 'exception' : activeJob.status === 'success' ? 'success' : 'active'}
                strokeColor={activeJob.status === 'failed' ? '#ff4d4f' : undefined}
              />
              <Descriptions column={1} size="small" style={{ marginTop: 8 }}>
                <Descriptions.Item label="任务 ID">{activeJob.job_id}</Descriptions.Item>
                <Descriptions.Item label="当前步骤">{activeJob.current_step || '-'}</Descriptions.Item>
                {activeJob.error && (
                  <Descriptions.Item label="错误">
                    <Tag color="red">{activeJob.error}</Tag>
                  </Descriptions.Item>
                )}
              </Descriptions>

              {activeJob.logs.length > 0 && (
                <>
                  <Divider orientation="left" style={{ margin: '12px 0 8px' }}>执行日志</Divider>
                  <div style={{
                    maxHeight: 280, overflowY: 'auto',
                    background: '#fafafa', borderRadius: 6, padding: '8px 12px',
                    fontFamily: 'monospace', fontSize: 13,
                  }}>
                    {activeJob.logs.map((log, i) => (
                      <div key={i} style={{ padding: '2px 0', color: log.level === 'error' ? '#ff4d4f' : '#333' }}>
                        <span style={{ color: '#999', marginRight: 8 }}>{log.time}</span>
                        {log.step}
                      </div>
                    ))}
                    <div ref={logEndRef} />
                  </div>
                </>
              )}
            </Card>
          )}

          <Card title="回测结果">
            {activeJob?.status === 'success' && activeJob.metrics ? (
              <Row gutter={16}>
                <Col span={12}><Statistic title="年化收益" value={activeJob.metrics.annualized_return ?? '-'} suffix="%" /></Col>
                <Col span={12}><Statistic title="Sharpe" value={activeJob.metrics.sharpe ?? '-'} /></Col>
                <Col span={12}><Statistic title="最大回撤" value={activeJob.metrics.max_drawdown ?? '-'} suffix="%" /></Col>
                <Col span={12}><Statistic title="信息比率" value={activeJob.metrics.information_ratio ?? '-'} /></Col>
                {activeJob.metrics.ic != null && (
                  <>
                    <Col span={12}><Statistic title="IC" value={activeJob.metrics.ic} /></Col>
                    <Col span={12}><Statistic title="ICIR" value={activeJob.metrics.icir} /></Col>
                    <Col span={12}><Statistic title="Rank IC" value={activeJob.metrics.rank_ic} /></Col>
                    <Col span={12}><Statistic title="Rank ICIR" value={activeJob.metrics.rank_icir} /></Col>
                  </>
                )}
              </Row>
            ) : (
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                {activeJob?.status === 'running' ? '训练中，完成后显示结果...' : '暂无回测结果，请先训练模型'}
              </div>
            )}
          </Card>

          <Card title="历史任务" style={{ marginTop: 16 }}>
            <Table
              dataSource={[...jobList].reverse()}
              rowKey="job_id"
              size="small"
              pagination={{ pageSize: 5 }}
              columns={[
                {
                  title: '状态', dataIndex: 'status', width: 80,
                  render: (v: string) => <Space>{statusIcon(v)}{v}</Space>,
                },
                { title: '任务 ID', dataIndex: 'job_id', width: 160 },
                {
                  title: '模型', width: 100,
                  render: (_: any, r: any) => r.config?.model_class || '-',
                },
                { title: '进度', dataIndex: 'progress', width: 80, render: (v: number) => `${v}%` },
                { title: '创建时间', dataIndex: 'created_at', width: 170 },
              ]}
              onRow={(record) => ({
                onClick: () => {
                  setActiveJob(record)
                  if (record.status === 'running') startPolling(record.job_id)
                },
                style: { cursor: 'pointer' },
              })}
            />
          </Card>
        </Col>
      </Row>
    </div>
  )
}
