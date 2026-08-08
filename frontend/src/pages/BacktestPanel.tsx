import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Card, Form, Select, DatePicker, Button, Row, Col, Statistic,
  message, Space, Progress, Badge, Modal, Input, Tooltip, Popconfirm, Tag,
  Collapse, InputNumber, Divider, Switch, AutoComplete, Rate,
} from 'antd'
import {
  PlusOutlined, SearchOutlined, DeleteOutlined, DownloadOutlined,
  CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined,
  ClockCircleOutlined, ExperimentOutlined, RocketOutlined,
  LineChartOutlined, DatabaseOutlined, AppstoreOutlined,
  AreaChartOutlined,
} from '@ant-design/icons'
import axios from 'axios'
import dayjs from 'dayjs'
import Plot from 'react-plotly.js'
import { fetchTrainDatasets } from '../api/data'

const { RangePicker } = DatePicker

interface LogEntry { time: string; step: string; level: string }

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
  model_path: string | null
  config: any
}

interface ModelMeta {
  model_id: string
  version: number
  job_id: string
  model_class: string
  size_bytes: number
  rating?: number
}

const statusIcon = (s: string, size = 16) => {
  const style = { fontSize: size }
  switch (s) {
    case 'running': return <LoadingOutlined spin style={{ ...style, color: '#1890ff' }} />
    case 'success': return <CheckCircleOutlined style={{ ...style, color: '#52c41a' }} />
    case 'failed': return <CloseCircleOutlined style={{ ...style, color: '#ff4d4f' }} />
    default: return <ClockCircleOutlined style={{ ...style, color: '#d9d9d9' }} />
  }
}

const statusTag = (s: string) => {
  const map: Record<string, { color: string; text: string }> = {
    pending: { color: 'default', text: '等待中' },
    running: { color: 'processing', text: '训练中' },
    success: { color: 'success', text: '已完成' },
    failed: { color: 'error', text: '失败' },
  }
  const t = map[s] || map.pending
  return <Tag color={t.color}>{t.text}</Tag>
}

const modelLabel: Record<string, string> = {
  LGBModel: 'LightGBM', XGBModel: 'XGBoost',
  CatBoostModel: 'CatBoost', LinearModel: 'Linear',
  DEnsembleModel: 'Double Ensemble',
  GRU: 'GRU', LSTM: 'LSTM', ALSTM: 'Attention LSTM',
  TransformerModel: 'Transformer', TCN: 'TCN',
  TabnetModel: 'TabNet', DNNModelPytorch: 'DNN/MLP',
  GATs: 'GATs', SFM_Model: 'SFM',
}

// 各模型可调超参数定义
interface ParamDef {
  key: string
  label: string
  type: 'number' | 'switch'
  default: number | boolean
  min?: number
  max?: number
  step?: number
}

const HYPERPARAMS: Record<string, ParamDef[]> = {
  LGBModel: [
    { key: 'learning_rate', label: '学习率', type: 'number', default: 0.0421, min: 0.001, max: 1, step: 0.001 },
    { key: 'max_depth', label: '最大深度', type: 'number', default: 8, min: 1, max: 20, step: 1 },
    { key: 'num_leaves', label: '叶子数', type: 'number', default: 210, min: 2, max: 1024, step: 1 },
    { key: 'subsample', label: 'Subsample', type: 'number', default: 0.8789, min: 0.1, max: 1, step: 0.01 },
    { key: 'colsample_bytree', label: 'Colsample', type: 'number', default: 0.8879, min: 0.1, max: 1, step: 0.01 },
    { key: 'lambda_l1', label: 'L1 正则', type: 'number', default: 205.7, min: 0, max: 1000, step: 0.1 },
    { key: 'lambda_l2', label: 'L2 正则', type: 'number', default: 580.98, min: 0, max: 1000, step: 0.1 },
  ],
  XGBModel: [
    { key: 'learning_rate', label: '学习率', type: 'number', default: 0.05, min: 0.001, max: 1, step: 0.001 },
    { key: 'max_depth', label: '最大深度', type: 'number', default: 8, min: 1, max: 20, step: 1 },
    { key: 'n_estimators', label: '迭代次数', type: 'number', default: 800, min: 10, max: 5000, step: 10 },
    { key: 'subsample', label: 'Subsample', type: 'number', default: 0.8789, min: 0.1, max: 1, step: 0.01 },
    { key: 'colsample_bytree', label: 'Colsample', type: 'number', default: 0.8879, min: 0.1, max: 1, step: 0.01 },
  ],
  CatBoostModel: [
    { key: 'iterations', label: '迭代次数', type: 'number', default: 800, min: 10, max: 5000, step: 10 },
    { key: 'learning_rate', label: '学习率', type: 'number', default: 0.05, min: 0.001, max: 1, step: 0.001 },
    { key: 'depth', label: '深度', type: 'number', default: 8, min: 1, max: 16, step: 1 },
  ],
  DEnsembleModel: [
    { key: 'num_models', label: '子模型数', type: 'number', default: 6, min: 2, max: 20, step: 1 },
    { key: 'epochs', label: '迭代轮数', type: 'number', default: 100, min: 10, max: 1000, step: 10 },
    { key: 'decay', label: '衰减系数', type: 'number', default: 0.5, min: 0.01, max: 1, step: 0.01 },
    { key: 'enable_sr', label: '样本重加权', type: 'switch', default: true },
    { key: 'enable_fs', label: '特征采样', type: 'switch', default: true },
  ],
  LinearModel: [],
  GRU: [
    { key: 'hidden_size', label: 'Hidden Size', type: 'number', default: 64, min: 16, max: 512, step: 16 },
    { key: 'num_layers', label: '层数', type: 'number', default: 2, min: 1, max: 8, step: 1 },
    { key: 'dropout', label: 'Dropout', type: 'number', default: 0.0, min: 0, max: 0.9, step: 0.05 },
    { key: 'n_epochs', label: '训练轮数', type: 'number', default: 200, min: 1, max: 1000, step: 10 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.001, min: 0.00001, max: 0.1, step: 0.0001 },
    { key: 'batch_size', label: 'Batch Size', type: 'number', default: 2000, min: 64, max: 8192, step: 64 },
    { key: 'early_stop', label: 'Early Stop', type: 'number', default: 20, min: 1, max: 100, step: 1 },
  ],
  LSTM: [
    { key: 'hidden_size', label: 'Hidden Size', type: 'number', default: 64, min: 16, max: 512, step: 16 },
    { key: 'num_layers', label: '层数', type: 'number', default: 2, min: 1, max: 8, step: 1 },
    { key: 'dropout', label: 'Dropout', type: 'number', default: 0.0, min: 0, max: 0.9, step: 0.05 },
    { key: 'n_epochs', label: '训练轮数', type: 'number', default: 200, min: 1, max: 1000, step: 10 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.001, min: 0.00001, max: 0.1, step: 0.0001 },
    { key: 'batch_size', label: 'Batch Size', type: 'number', default: 2000, min: 64, max: 8192, step: 64 },
    { key: 'early_stop', label: 'Early Stop', type: 'number', default: 20, min: 1, max: 100, step: 1 },
  ],
  ALSTM: [
    { key: 'hidden_size', label: 'Hidden Size', type: 'number', default: 64, min: 16, max: 512, step: 16 },
    { key: 'num_layers', label: '层数', type: 'number', default: 2, min: 1, max: 8, step: 1 },
    { key: 'dropout', label: 'Dropout', type: 'number', default: 0.0, min: 0, max: 0.9, step: 0.05 },
    { key: 'n_epochs', label: '训练轮数', type: 'number', default: 200, min: 1, max: 1000, step: 10 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.001, min: 0.00001, max: 0.1, step: 0.0001 },
    { key: 'batch_size', label: 'Batch Size', type: 'number', default: 2000, min: 64, max: 8192, step: 64 },
    { key: 'early_stop', label: 'Early Stop', type: 'number', default: 20, min: 1, max: 100, step: 1 },
  ],
  TransformerModel: [
    { key: 'd_model', label: 'D-Model', type: 'number', default: 64, min: 16, max: 512, step: 16 },
    { key: 'nhead', label: '注意力头数', type: 'number', default: 2, min: 1, max: 16, step: 1 },
    { key: 'num_layers', label: '层数', type: 'number', default: 2, min: 1, max: 12, step: 1 },
    { key: 'dropout', label: 'Dropout', type: 'number', default: 0.0, min: 0, max: 0.9, step: 0.05 },
    { key: 'n_epochs', label: '训练轮数', type: 'number', default: 200, min: 1, max: 1000, step: 10 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.0001, min: 0.000001, max: 0.01, step: 0.00001 },
    { key: 'batch_size', label: 'Batch Size', type: 'number', default: 2048, min: 64, max: 8192, step: 64 },
    { key: 'early_stop', label: 'Early Stop', type: 'number', default: 5, min: 1, max: 100, step: 1 },
  ],
  TCN: [
    { key: 'n_chans', label: '通道数', type: 'number', default: 128, min: 16, max: 512, step: 16 },
    { key: 'kernel_size', label: 'Kernel Size', type: 'number', default: 5, min: 2, max: 20, step: 1 },
    { key: 'num_layers', label: '层数', type: 'number', default: 5, min: 1, max: 15, step: 1 },
    { key: 'dropout', label: 'Dropout', type: 'number', default: 0.5, min: 0, max: 0.9, step: 0.05 },
    { key: 'n_epochs', label: '训练轮数', type: 'number', default: 200, min: 1, max: 1000, step: 10 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.0001, min: 0.000001, max: 0.01, step: 0.00001 },
    { key: 'batch_size', label: 'Batch Size', type: 'number', default: 2000, min: 64, max: 8192, step: 64 },
    { key: 'early_stop', label: 'Early Stop', type: 'number', default: 20, min: 1, max: 100, step: 1 },
  ],
  TabnetModel: [
    { key: 'n_epochs', label: '训练轮数', type: 'number', default: 200, min: 1, max: 1000, step: 10 },
    { key: 'pretrain_n_epochs', label: '预训练轮数', type: 'number', default: 50, min: 1, max: 500, step: 5 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.001, min: 0.00001, max: 0.1, step: 0.0001 },
    { key: 'batch_size', label: 'Batch Size', type: 'number', default: 2000, min: 64, max: 8192, step: 64 },
    { key: 'early_stop', label: 'Early Stop', type: 'number', default: 20, min: 1, max: 100, step: 1 },
  ],
  DNNModelPytorch: [
    { key: 'max_steps', label: '训练步数', type: 'number', default: 300, min: 10, max: 5000, step: 10 },
    { key: 'eval_steps', label: '评估间隔', type: 'number', default: 20, min: 5, max: 500, step: 5 },
    { key: 'early_stop_rounds', label: 'Early Stop', type: 'number', default: 50, min: 5, max: 500, step: 5 },
    { key: 'batch_size', label: 'Batch Size', type: 'number', default: 2000, min: 64, max: 8192, step: 64 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.001, min: 0.00001, max: 0.1, step: 0.0001 },
  ],
  GATs: [
    { key: 'hidden_size', label: 'Hidden Size', type: 'number', default: 64, min: 16, max: 512, step: 16 },
    { key: 'num_layers', label: '层数', type: 'number', default: 2, min: 1, max: 8, step: 1 },
    { key: 'dropout', label: 'Dropout', type: 'number', default: 0.0, min: 0, max: 0.9, step: 0.05 },
    { key: 'n_epochs', label: '训练轮数', type: 'number', default: 200, min: 1, max: 1000, step: 10 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.001, min: 0.00001, max: 0.1, step: 0.0001 },
    { key: 'early_stop', label: 'Early Stop', type: 'number', default: 20, min: 1, max: 100, step: 1 },
  ],
  SFM_Model: [
    { key: 'hidden_size', label: 'Hidden Size', type: 'number', default: 64, min: 16, max: 512, step: 16 },
    { key: 'output_dim', label: 'Output Dim', type: 'number', default: 32, min: 8, max: 128, step: 8 },
    { key: 'freq_dim', label: 'Freq Dim', type: 'number', default: 25, min: 1, max: 128, step: 1 },
    { key: 'n_epochs', label: '训练轮数', type: 'number', default: 200, min: 1, max: 1000, step: 10 },
    { key: 'lr', label: '学习率', type: 'number', default: 0.001, min: 0.00001, max: 0.1, step: 0.0001 },
    { key: 'batch_size', label: 'Batch Size', type: 'number', default: 2000, min: 64, max: 8192, step: 64 },
    { key: 'early_stop', label: 'Early Stop', type: 'number', default: 20, min: 1, max: 100, step: 1 },
  ],
  HFLGBModel: [
    { key: 'learning_rate', label: '学习率', type: 'number', default: 0.01, min: 0.001, max: 1, step: 0.001 },
    { key: 'max_depth', label: '最大深度', type: 'number', default: 8, min: 1, max: 20, step: 1 },
    { key: 'num_leaves', label: '叶子数', type: 'number', default: 150, min: 2, max: 1024, step: 1 },
    { key: 'lambda_l1', label: 'L1 正则', type: 'number', default: 1.5, min: 0, max: 100, step: 0.1 },
    { key: 'lambda_l2', label: 'L2 正则', type: 'number', default: 1, min: 0, max: 100, step: 0.1 },
  ],
}

export default function BacktestPanel() {
  const [jobs, setJobs] = useState<JobStatus[]>([])
  const [models, setModels] = useState<ModelMeta[]>([])
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteJobId, setDeleteJobId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [form] = Form.useForm()
  const selectedModel = Form.useWatch('model_class', form)
  const pollRef = useRef<Record<string, ReturnType<typeof setInterval>>>({})
  const logRefs = useRef<Record<string, HTMLDivElement | null>>({})

  const currentParams: ParamDef[] = HYPERPARAMS[selectedModel] || []

  // 训练数据源状态
  const [trainSources, setTrainSources] = useState<any[]>([])
  const [trainDatasets, setTrainDatasets] = useState<any[]>([])
  const selectedDataSource = Form.useWatch('data_source', form)

  useEffect(() => {
    // 加载训练可用数据源（各源目录扫描）
    fetchTrainDatasets().then(res => {
      setTrainSources(res.sources || [])
      setTrainDatasets(res.datasets || [])
    }).catch(() => {})
  }, [])

  // 预测弹窗状态
  const [predictOpen, setPredictOpen] = useState(false)
  const [predictModel, setPredictModel] = useState<ModelMeta | null>(null)
  const [predictSymbol, setPredictSymbol] = useState('SH600519')
  const [predictRange, setPredictRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>([
    dayjs('2020-03-01'), dayjs('2020-09-25'),
  ])
  const [predictLoading, setPredictLoading] = useState(false)
  const [predictResult, setPredictResult] = useState<any>(null)
  const [dataRange, setDataRange] = useState<{ start: string; end: string } | null>(null)
  const [stockOptions, setStockOptions] = useState<{ value: string; label: React.ReactNode }[]>([])
  const stockSearchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 训练曲线弹窗状态
  const [curvesOpen, setCurvesOpen] = useState(false)
  const [curvesJob, setCurvesJob] = useState<JobStatus | null>(null)
  const [curvesData, setCurvesData] = useState<any>(null)
  const curvesPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchAll = useCallback(async () => {
    try {
      const [jr, mr] = await Promise.all([
        axios.get('/api/train/jobs'),
        axios.get('/api/models'),
      ])
      setJobs(jr.data)
      setModels(mr.data)
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    fetchAll()
    return () => { Object.values(pollRef.current).forEach(clearInterval) }
  }, [fetchAll])

  const startPolling = useCallback((jobId: string) => {
    if (pollRef.current[jobId]) return
    pollRef.current[jobId] = setInterval(async () => {
      try {
        const res = await axios.get(`/api/train/status/${jobId}`)
        setJobs(prev => prev.map(j => j.job_id === jobId ? res.data : j))
        if (res.data.status === 'success' || res.data.status === 'failed') {
          clearInterval(pollRef.current[jobId])
          delete pollRef.current[jobId]
          fetchAll()
        }
      } catch { /* ignore */ }
    }, 1500)
  }, [fetchAll])

  const handleCreate = async (values: any) => {
    setCreating(true)
    try {
      const payload = { ...values }
      if (values.train_range) {
        payload.train_range = [values.train_range[0].format('YYYY-MM-DD'), values.train_range[1].format('YYYY-MM-DD')]
        payload.valid_range = [values.valid_range[0].format('YYYY-MM-DD'), values.valid_range[1].format('YYYY-MM-DD')]
        payload.test_range = [values.test_range[0].format('YYYY-MM-DD'), values.test_range[1].format('YYYY-MM-DD')]
      }
      // 收集超参数到 model_kwargs
      const modelKwargs: Record<string, any> = {}
      const params = HYPERPARAMS[values.model_class] || []
      params.forEach(p => {
        const v = values[`hp_${p.key}`]
        if (v !== undefined && v !== null && v !== p.default) {
          modelKwargs[p.key] = v
        }
      })
      if (Object.keys(modelKwargs).length > 0) {
        payload.model_kwargs = modelKwargs
      }
      // 清理 hp_ 前缀字段
      Object.keys(payload).forEach(k => { if (k.startsWith('hp_')) delete payload[k] })
      const res = await axios.post('/api/train/start', payload)
      message.success(`训练已启动: ${res.data.job_id}`)
      const newJob: JobStatus = {
        job_id: res.data.job_id, status: 'pending', progress: 0,
        current_step: '初始化...', logs: [], created_at: new Date().toISOString(),
        finished_at: null, error: null, metrics: null, model_path: null, config: payload,
      }
      setJobs(prev => [newJob, ...prev])
      startPolling(res.data.job_id)
      setCreateOpen(false)
      form.resetFields()
    } catch (err: any) {
      message.error(err.response?.data?.detail || '启动训练失败')
    }
    setCreating(false)
  }

  const handleDelete = async (jobId: string) => {
    try {
      await axios.delete(`/api/train/jobs/${jobId}`)
      setJobs(prev => prev.filter(j => j.job_id !== jobId))
      message.success('任务已删除')
    } catch { message.error('删除失败') }
  }

  const handleDownload = (modelId: string, modelClass: string) => {
    const a = document.createElement('a')
    a.href = `/api/models/${modelId}/download`
    a.download = `${modelId}_${modelClass}.pkl`
    a.click()
  }

  const findModel = (jobId: string) => models.find(m => m.job_id === jobId)

  const openPredict = async (model: ModelMeta) => {
    setPredictModel(model)
    setPredictResult(null)
    setPredictOpen(true)
    // 获取可用数据范围
    try {
      const res = await axios.get('/api/predict/data_range')
      if (res.data.start && res.data.end) {
        setDataRange(res.data)
        // 默认选最近6个月数据
        const end = dayjs(res.data.end)
        const start = end.subtract(6, 'month').isAfter(dayjs(res.data.start))
          ? end.subtract(6, 'month') : dayjs(res.data.start)
        setPredictRange([start, end])
      }
    } catch { /* ignore */ }
  }

  const runPredict = async () => {
    if (!predictModel) return
    setPredictLoading(true)
    setPredictResult(null)
    try {
      const res = await axios.post('/api/predict/run', {
        model_id: predictModel.model_id,
        symbol: predictSymbol,
        start_date: predictRange[0].format('YYYY-MM-DD'),
        end_date: predictRange[1].format('YYYY-MM-DD'),
      })
      setPredictResult(res.data)
    } catch (err: any) {
      message.error(err.response?.data?.detail || '预测失败')
    }
    setPredictLoading(false)
  }

  // 训练曲线
  const fetchCurves = useCallback(async (jobId: string) => {
    try {
      const res = await axios.get(`/api/train/jobs/${jobId}/history`)
      setCurvesData(res.data)
    } catch { /* ignore */ }
  }, [])

  const openCurves = (job: JobStatus) => {
    setCurvesJob(job)
    setCurvesData(null)
    setCurvesOpen(true)
    fetchCurves(job.job_id)
    // 运行中的任务动态刷新
    if (curvesPollRef.current) clearInterval(curvesPollRef.current)
    if (job.status === 'running' || job.status === 'pending') {
      curvesPollRef.current = setInterval(() => fetchCurves(job.job_id), 2000)
    }
  }

  const closeCurves = () => {
    setCurvesOpen(false)
    setCurvesJob(null)
    setCurvesData(null)
    if (curvesPollRef.current) {
      clearInterval(curvesPollRef.current)
      curvesPollRef.current = null
    }
  }

  const filtered = jobs
    .filter(j => {
      if (!search.trim()) return true
      const q = search.toLowerCase()
      return (
        j.job_id.toLowerCase().includes(q) ||
        (j.config?.model_class || '').toLowerCase().includes(q) ||
        (j.config?.handler || '').toLowerCase().includes(q) ||
        (j.config?.market || '').toLowerCase().includes(q) ||
        j.status.toLowerCase().includes(q)
      )
    })
    .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))

  // Auto-scroll logs for running jobs
  useEffect(() => {
    filtered.forEach(j => {
      if (j.status === 'running' && logRefs.current[j.job_id]) {
        const el = logRefs.current[j.job_id]
        if (el) el.scrollTop = el.scrollHeight
      }
    })
  })

  const renderJobCard = (job: JobStatus) => {
    const model = findModel(job.job_id)
    const isRunning = job.status === 'running' || job.status === 'pending'
    const m = job.metrics

    return (
      <Col xs={24} lg={12} key={job.job_id}>
        <Card
          size="small"
          style={{ marginBottom: 16, borderLeft: `3px solid ${job.status === 'success' ? '#52c41a' : job.status === 'failed' ? '#ff4d4f' : job.status === 'running' ? '#1890ff' : '#d9d9d9'}` }}
          title={
            <Space size={8}>
              {statusIcon(job.status)}
              <span style={{ fontSize: 13, fontFamily: 'monospace' }}>{job.job_id}</span>
              {statusTag(job.status)}
            </Space>
          }
          extra={
            <Space size={4}>
              <Tooltip title="训练曲线">
                <Button type="text" size="small" icon={<AreaChartOutlined />}
                  onClick={() => openCurves(job)} />
              </Tooltip>
              {model && (
                <Tooltip title={`下载模型 (${(model.size_bytes / 1024).toFixed(0)}KB)`}>
                  <Button type="text" size="small" icon={<DownloadOutlined />}
                    onClick={() => handleDownload(model.model_id, model.model_class)} />
                </Tooltip>
              )}
              <Tooltip title="删除任务">
                <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => setDeleteJobId(job.job_id)} />
              </Tooltip>
            </Space>
          }
        >
          {/* 基本信息 */}
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 8, fontSize: 12, color: '#666' }}>
            <span><ExperimentOutlined style={{ marginRight: 4 }} />{modelLabel[job.config?.model_class] || job.config?.model_class || '-'}</span>
            <span><AppstoreOutlined style={{ marginRight: 4 }} />{job.config?.handler || '-'}</span>
            <span><DatabaseOutlined style={{ marginRight: 4 }} />{job.config?.market || '-'}</span>
            <span><ClockCircleOutlined style={{ marginRight: 4 }} />{job.created_at?.replace('T', ' ') || '-'}</span>
          </div>

          {/* 运行中：进度 + 日志 */}
          {isRunning ? (
            <>
              <Progress
                percent={job.progress} size="small"
                status={job.status === 'failed' ? 'exception' : 'active'}
                strokeColor={job.status === 'failed' ? '#ff4d4f' : undefined}
              />
              <div style={{ fontSize: 12, color: '#1890ff', margin: '4px 0' }}>{job.current_step}</div>
              {job.logs.length > 0 && (
                <div
                  ref={el => { logRefs.current[job.job_id] = el }}
                  style={{
                    maxHeight: 140, overflowY: 'auto', background: '#fafafa',
                    borderRadius: 4, padding: '6px 10px', fontFamily: 'monospace', fontSize: 11,
                  }}
                >
                  {job.logs.map((log, i) => (
                    <div key={i} style={{ padding: '1px 0', color: log.level === 'error' ? '#ff4d4f' : '#555' }}>
                      <span style={{ color: '#bbb', marginRight: 6 }}>{log.time}</span>{log.step}
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : job.status === 'failed' ? (
            <div style={{ color: '#ff4d4f', fontSize: 12, background: '#fff2f0', padding: '6px 10px', borderRadius: 4 }}>
              <CloseCircleOutlined style={{ marginRight: 6 }} />{job.error || '未知错误'}
            </div>
          ) : m ? (
            /* 完成：回测指标 */
            <Row gutter={[8, 4]}>
              <Col span={6}>
                <Statistic title={<span style={{ fontSize: 11 }}><LineChartOutlined /> 年化收益</span>}
                  value={m.annualized_return ?? '-'} suffix="%" valueStyle={{ fontSize: 16 }} />
              </Col>
              <Col span={6}>
                <Statistic title={<span style={{ fontSize: 11 }}>Sharpe</span>}
                  value={m.sharpe ?? '-'} valueStyle={{ fontSize: 16 }} />
              </Col>
              <Col span={6}>
                <Statistic title={<span style={{ fontSize: 11 }}>最大回撤</span>}
                  value={m.max_drawdown ?? '-'} suffix="%" valueStyle={{ fontSize: 16, color: '#cf1322' }} />
              </Col>
              <Col span={6}>
                <Statistic title={<span style={{ fontSize: 11 }}>信息比率</span>}
                  value={m.information_ratio ?? '-'} valueStyle={{ fontSize: 16 }} />
              </Col>
              {m.ic != null && (
                <>
                  <Col span={6}><Statistic title={<span style={{ fontSize: 11 }}>IC</span>} value={m.ic} valueStyle={{ fontSize: 13 }} /></Col>
                  <Col span={6}><Statistic title={<span style={{ fontSize: 11 }}>ICIR</span>} value={m.icir} valueStyle={{ fontSize: 13 }} /></Col>
                  <Col span={6}><Statistic title={<span style={{ fontSize: 11 }}>Rank IC</span>} value={m.rank_ic} valueStyle={{ fontSize: 13 }} /></Col>
                  <Col span={6}><Statistic title={<span style={{ fontSize: 11 }}>Rank ICIR</span>} value={m.rank_icir} valueStyle={{ fontSize: 13 }} /></Col>
                </>
              )}
            </Row>
          ) : null}

          {/* 模型信息 + 星级评分 + 预测按钮 */}
          {model && (
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid #f0f0f0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: '#999' }}>
                <RocketOutlined style={{ marginRight: 4 }} />
                模型 {model.model_id} (v{model.version}) · {(model.size_bytes / 1024).toFixed(0)}KB
              </span>
              <Space size={8}>
                <Rate
                  count={5}
                  value={model.rating || 0}
                  style={{ fontSize: 14, color: '#1890ff' }}
                  onChange={(val) => {
                    axios.patch(`/api/models/${model.model_id}/rating`, null, { params: { rating: val } })
                      .then(() => {
                        setModels(prev => prev.map(m => m.model_id === model.model_id ? { ...m, rating: val } : m))
                      })
                      .catch(() => message.error('评分保存失败'))
                  }}
                />
                <Button size="small" type="link" icon={<LineChartOutlined />} onClick={() => openPredict(model)}>
                  预测
                </Button>
              </Space>
            </div>
          )}
        </Card>
      </Col>
    )
  }

  return (
    <div>
      {/* 搜索栏 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 20 }}>
        <Input
          placeholder="搜索任务 ID、模型、因子集、股票池..."
          prefix={<SearchOutlined style={{ color: '#bbb' }} />}
          value={search}
          onChange={e => setSearch(e.target.value)}
          allowClear
          style={{ maxWidth: 480 }}
          onPressEnter={() => fetchAll()}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={fetchAll}>检索</Button>
      </div>

      {/* 卡片网格 */}
      <Row gutter={16}>
        {/* 创建按钮 */}
        <Col xs={24} lg={12}>
          <Card
            size="small"
            style={{
              marginBottom: 16, cursor: 'pointer', textAlign: 'center',
              border: '2px dashed #d9d9d9', background: '#fafafa',
              minHeight: 120, display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
            bodyStyle={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: 24, width: '100%' }}
            onClick={() => setCreateOpen(true)}
            hoverable
          >
            <PlusOutlined style={{ fontSize: 36, color: '#999', marginBottom: 8 }} />
            <span style={{ color: '#999', fontSize: 14 }}>创建训练任务</span>
          </Card>
        </Col>

        {/* 任务卡片 */}
        {filtered.map(renderJobCard)}
      </Row>

      {/* 创建任务弹窗 */}
      <Modal
        title={<Space><RocketOutlined />创建训练任务</Space>}
        open={createOpen}
        onCancel={() => setCreateOpen(false)}
        footer={null}
        width={520}
        destroyOnClose
      >
        <Form form={form} layout="vertical" onFinish={handleCreate} style={{ marginTop: 16 }}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="模型类型" name="model_class" initialValue="LGBModel" rules={[{ required: true }]}>
                <Select
                  showSearch
                  onChange={(val: string) => {
                    if (val === 'HFLGBModel') {
                      form.setFieldsValue({
                        handler: 'HighFreqHandler',
                        train_range: [dayjs('2026-07-09'), dayjs('2026-07-22')],
                        valid_range: [dayjs('2026-07-23'), dayjs('2026-07-27')],
                        test_range: [dayjs('2026-07-28'), dayjs('2026-07-31')],
                      })
                    } else {
                      form.setFieldsValue({
                        handler: 'Alpha158',
                        train_range: [dayjs('2019-01-01'), dayjs('2024-12-31')],
                        valid_range: [dayjs('2025-01-01'), dayjs('2025-06-30')],
                        test_range: [dayjs('2025-07-01'), dayjs('2026-07-31')],
                      })
                    }
                  }}
                  options={[
                    { label: '树模型 / 集成', options: [
                      { value: 'LGBModel', label: 'LightGBM' },
                      { value: 'XGBModel', label: 'XGBoost' },
                      { value: 'CatBoostModel', label: 'CatBoost' },
                      { value: 'DEnsembleModel', label: 'Double Ensemble' },
                    ]},
                    { label: '线性模型', options: [
                      { value: 'LinearModel', label: 'Linear' },
                    ]},
                    { label: '深度学习 (PyTorch)', options: [
                      { value: 'GRU', label: 'GRU' },
                      { value: 'LSTM', label: 'LSTM' },
                      { value: 'ALSTM', label: 'Attention LSTM' },
                      { value: 'TransformerModel', label: 'Transformer' },
                      { value: 'TCN', label: 'TCN (时间卷积)' },
                      { value: 'TabnetModel', label: 'TabNet' },
                      { value: 'DNNModelPytorch', label: 'DNN/MLP' },
                      { value: 'GATs', label: 'GATs (图注意力)' },
                      { value: 'SFM_Model', label: 'SFM (频谱特征)' },
                    ]},
                    { label: '高频模型 (1min)', options: [
                      { value: 'HFLGBModel', label: 'HF-LightGBM (分钟级)' },
                    ]},
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="因子集" name="handler" initialValue="Alpha158" rules={[{ required: true }]}>
                <Select
                  disabled={selectedModel === 'HFLGBModel'}
                  options={[
                    { value: 'Alpha158', label: 'Alpha158' },
                    { value: 'Alpha360', label: 'Alpha360' },
                    { value: 'HighFreqHandler', label: 'HighFreq (分钟级因子)' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item
            label="数据源"
            name="data_source"
            initialValue="qlib"
            tooltip="训练使用哪个渠道同步的数据。qlib=默认数据目录；东方财富/Sina 需先用对应源同步数据"
          >
            <Select
              onChange={(val: string) => {
                // 切换到无数据的源时提示
                const src = trainSources.find(s => s.source_id === val)
                if (src && !src.has_data && val !== 'qlib') {
                  message.warning(`「${src.name}」尚未同步数据，请先在数据管理页同步，或继续用默认 qlib 数据`)
                }
              }}
              options={[
                { value: 'qlib', label: 'Qlib（默认）' },
                ...trainSources.filter(s => s.source_id !== 'qlib').map(s => ({
                  value: s.source_id,
                  label: (
                    <span>
                      {s.name}
                      {s.has_data ? <Tag color="success" style={{ marginLeft: 8 }}>{s.stock_count} 只</Tag> : <Tag color="warning" style={{ marginLeft: 8 }}>无数据</Tag>}
                    </span>
                  ),
                })),
              ]}
            />
          </Form.Item>
          <Form.Item label="股票池" name="market" initialValue="csi300" rules={[{ required: true }]}>
            <Select options={[
              { value: 'csi300', label: '沪深300' },
              { value: 'csi500', label: '中证500' },
              { value: 'csi100', label: '中证100' },
              { value: 'all', label: '全市场' },
            ]} />
          </Form.Item>
          {/* 数据源数据集状态提示 */}
          {selectedDataSource && selectedDataSource !== 'qlib' && (
            <div style={{ marginBottom: 16, padding: '8px 12px', background: '#fffbe6', border: '1px solid #ffe58f', borderRadius: 6, fontSize: 13 }}>
              <span style={{ fontWeight: 500 }}>数据集状态：</span>
              {trainDatasets.filter(d => d.source_id === selectedDataSource).length === 0 ? (
                <span style={{ color: '#faad14' }}>该数据源暂无同步记录，将使用其数据目录（如已手动同步则忽略此提示）</span>
              ) : (
                trainDatasets.filter(d => d.source_id === selectedDataSource).map(d => (
                  <div key={d.dataset_id}>
                    <Tag color="blue">{d.market}</Tag>
                    <Tag>{d.freq}</Tag>
                    <span style={{ color: '#666' }}>覆盖 {d.coverage_pct}% · {d.stock_count} 只 · {d.start_date} ~ {d.end_date}</span>
                    {d.stale && <Tag color="warning" style={{ marginLeft: 8 }}>已过期</Tag>}
                  </div>
                ))
              )}
            </div>
          )}
          <Form.Item label="训练集" name="train_range" initialValue={[dayjs('2019-01-01'), dayjs('2024-12-31')]}>
            <RangePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="验证集" name="valid_range" initialValue={[dayjs('2025-01-01'), dayjs('2025-06-30')]}>
            <RangePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item label="测试集" name="test_range" initialValue={[dayjs('2025-07-01'), dayjs('2026-07-31')]}>
            <RangePicker style={{ width: '100%' }} />
          </Form.Item>

          {/* 超参数调整 */}
          {currentParams.length > 0 && (
            <Collapse
              size="small"
              style={{ marginBottom: 16 }}
              items={[{
                key: 'hyperparams',
                label: <span style={{ fontSize: 13 }}>超参数调整（可选，默认值已预填）</span>,
                children: (
                  <Row gutter={[12, 0]}>
                    {currentParams.map(p => (
                      <Col span={12} key={p.key}>
                        <Form.Item
                          label={<span style={{ fontSize: 12 }}>{p.label}</span>}
                          name={`hp_${p.key}`}
                          initialValue={p.default}
                          style={{ marginBottom: 8 }}
                        >
                          {p.type === 'switch' ? (
                            <Switch size="small" />
                          ) : (
                            <InputNumber
                              size="small"
                              style={{ width: '100%' }}
                              min={p.min}
                              max={p.max}
                              step={p.step}
                            />
                          )}
                        </Form.Item>
                      </Col>
                    ))}
                  </Row>
                ),
              }]}
            />
          )}

          <Button type="primary" htmlType="submit" icon={<RocketOutlined />} loading={creating} block>
            开始训练
          </Button>
        </Form>
      </Modal>

      {/* 预测弹窗 */}
      <Modal
        title={<Space><LineChartOutlined />单股预测 — {predictModel?.model_id}</Space>}
        open={predictOpen}
        onCancel={() => setPredictOpen(false)}
        footer={null}
        width={780}
        destroyOnClose
      >
        <Space style={{ marginBottom: 16 }} wrap>
          <AutoComplete
            value={predictSymbol}
            options={stockOptions}
            onSearch={(text) => {
              setPredictSymbol(text)  // 不做 toUpperCase，避免打断中文输入法组合状态
              if (stockSearchTimer.current) clearTimeout(stockSearchTimer.current)
              if (!text.trim()) { setStockOptions([]); return }
              stockSearchTimer.current = setTimeout(async () => {
                try {
                  const res = await axios.get('/api/data/stocks', { params: { keyword: text.trim() } })
                  const items = res.data.data || []
                  setStockOptions(items.slice(0, 20).map((s: any) => ({
                    value: `${s.market}${s.symbol}`,
                    label: <Space><span style={{ fontWeight: 500 }}>{s.market}{s.symbol}</span><span style={{ color: '#999' }}>{s.name}</span></Space>,
                  })))
                } catch { setStockOptions([]) }
              }, 300)
            }}
            onSelect={(val: string) => { setPredictSymbol(val); setStockOptions([]) }}
            placeholder="搜索股票代码/名称，如 600519 或 茅台"
            style={{ width: 240 }}
          >
            <Input prefix={<SearchOutlined style={{ color: '#bbb' }} />} />
          </AutoComplete>
          <RangePicker
            value={predictRange}
            onChange={(v) => { if (v && v[0] && v[1]) setPredictRange([v[0], v[1]]) }}
            style={{ width: 240 }}
          />
          <Button type="primary" icon={<LineChartOutlined />} loading={predictLoading} onClick={runPredict}>
            开始预测
          </Button>
        </Space>
        {dataRange && (
          <div style={{ marginBottom: 12, fontSize: 12, color: '#999' }}>
            可用数据范围：{dataRange.start} ~ {dataRange.end}
          </div>
        )}

        {predictResult && (
          <div>
            {/* 信号摘要 */}
            <Row gutter={16} style={{ marginBottom: 16 }}>
              <Col span={6}>
                <Statistic title="信号方向" value={predictResult.signal.direction}
                  valueStyle={{ color: predictResult.signal.direction === '看多' ? '#cf1322' : '#3f8600', fontSize: 20 }} />
              </Col>
              <Col span={6}>
                <Statistic title="信号强度" value={predictResult.signal.strength} suffix="%" valueStyle={{ fontSize: 20 }} />
              </Col>
              <Col span={6}>
                <Statistic title="最新分数" value={predictResult.signal.latest_score} precision={4} valueStyle={{ fontSize: 20 }} />
              </Col>
              <Col span={6}>
                <Statistic title="数据天数" value={predictResult.total_days} suffix="天" valueStyle={{ fontSize: 20 }} />
              </Col>
            </Row>

            {/* 图表 */}
            {predictResult.data.length > 0 && (
              <Plot
                data={[
                  {
                    x: predictResult.data.map((d: any) => d.date),
                    y: predictResult.data.map((d: any) => d.close),
                    type: 'scatter',
                    mode: 'lines',
                    name: '收盘价',
                    line: { color: '#1890ff', width: 1.5 },
                    yaxis: 'y',
                  },
                  {
                    x: predictResult.data.map((d: any) => d.date),
                    y: predictResult.data.map((d: any) => d.score),
                    type: 'scatter',
                    mode: 'lines',
                    name: '预测分数',
                    line: { color: '#ff4d4f', width: 1.5 },
                    yaxis: 'y2',
                  },
                ]}
                layout={{
                  height: 360,
                  margin: { l: 50, r: 50, t: 30, b: 40 },
                  showlegend: true,
                  legend: { orientation: 'h', y: 1.1 },
                  yaxis: { title: { text: '价格' }, side: 'left' },
                  yaxis2: { title: { text: '预测分数' }, side: 'right', overlaying: 'y' },
                  xaxis: { rangeslider: { visible: false } },
                }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            )}
          </div>
        )}
      </Modal>

      {/* 训练曲线弹窗 */}
      <Modal
        title={
          <Space>
            <AreaChartOutlined />
            训练看板 — {curvesJob?.job_id}
            {curvesJob && statusTag(curvesJob.status)}
          </Space>
        }
        open={curvesOpen}
        onCancel={closeCurves}
        footer={null}
        width={1100}
        destroyOnClose
      >
        {curvesData && curvesData.epochs?.length > 0 ? (
          curvesData.hf_metrics ? (
          /* ===== 高频专用看板 ===== */
          <Row gutter={[16, 16]}>
            {/* Loss 曲线 */}
            <Col span={12}>
              <Plot
                data={[
                  { x: curvesData.epochs, y: curvesData.train_loss, type: 'scatter', mode: 'lines', name: 'Train Loss', line: { color: '#1890ff', width: 1.5 } },
                  { x: curvesData.epochs, y: curvesData.valid_loss, type: 'scatter', mode: 'lines', name: 'Valid Loss', line: { color: '#ff4d4f', width: 1.5 } },
                ]}
                layout={{ title: { text: '损失曲线 (Loss)' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: true, legend: { orientation: 'h', y: 1.15 }, xaxis: { title: { text: 'Epoch' } } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </Col>
            {/* 单位换手收益 */}
            <Col span={12}>
              <div style={{ height: 260, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#fafafa', borderRadius: 8 }}>
                <div style={{ color: '#666', fontSize: 13, marginBottom: 8 }}>单位换手收益（bp / 1%换手）</div>
                <div style={{ fontSize: 42, fontWeight: 700, color: (curvesData.hf_metrics.edge_per_turnover_bp ?? 0) >= 0 ? '#52c41a' : '#ff4d4f' }}>
                  {curvesData.hf_metrics.edge_per_turnover_bp != null ? curvesData.hf_metrics.edge_per_turnover_bp.toFixed(3) : '--'}
                </div>
                <div style={{ color: '#999', fontSize: 12, marginTop: 10 }}>
                  毛利率 {(curvesData.hf_metrics.cost_breakdown?.gross_alpha_bp ?? 0).toFixed(3)} bp/bar · 缓冲换手 {((curvesData.hf_metrics.avg_turnover ?? 0) * 100).toFixed(1)}%/次（每{curvesData.hf_metrics.rebalance_interval ?? 5}bars调仓） · 原始换手 {((curvesData.hf_metrics.raw_turnover ?? 0) * 100).toFixed(1)}%/bar · {curvesData.hf_metrics.n_bars} bars × {curvesData.hf_metrics.n_stocks} stocks
                </div>
              </div>
            </Col>
            {/* 成本分解 */}
            <Col span={12}>
              <Plot
                data={[
                  {
                    values: [curvesData.hf_metrics.cost_breakdown?.fee, curvesData.hf_metrics.cost_breakdown?.slippage, curvesData.hf_metrics.cost_breakdown?.impact].map(v => Math.abs(v ?? 0)),
                    labels: ['手续费', '滑点', '冲击成本'],
                    type: 'pie', hole: 0.45,
                    marker: { colors: ['#1890ff', '#faad14', '#ff4d4f'] },
                    textinfo: 'label+percent',
                    hovertemplate: '%{label}: %{value:.4f} bp<extra></extra>',
                  },
                ]}
                layout={{ title: { text: `成本分解（净α ${curvesData.hf_metrics.cost_breakdown?.net_alpha_bp ?? '--'} bp/bar）` }, height: 260, margin: { l: 20, r: 20, t: 40, b: 20 }, showlegend: true, legend: { orientation: 'h', y: -0.1 } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </Col>
            {/* 分桶成交后收益 */}
            <Col span={12}>
              <Plot
                data={[
                  {
                    x: ['D1','D2','D3','D4','D5','D6','D7','D8','D9','D10'],
                    y: curvesData.hf_metrics.decile_net_bp,
                    type: 'bar',
                    marker: { color: (curvesData.hf_metrics.decile_net_bp || []).map((v: number) => v >= 0 ? '#52c41a' : '#ff4d4f') },
                  },
                ]}
                layout={{ title: { text: '分桶成交后收益（bp/bar，已扣执行成本）' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: false, xaxis: { title: { text: '预测分桶（D1=最低 → D10=最高）' } }, yaxis: { title: { text: 'bp' }, zeroline: true, zerolinecolor: '#ddd' } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </Col>
            {/* 信号半衰期 */}
            <Col span={12}>
              <Plot
                data={[
                  { x: curvesData.hf_metrics.half_life?.horizons, y: curvesData.hf_metrics.half_life?.top_decile, type: 'scatter', mode: 'lines+markers', name: 'Top组前向收益', line: { color: '#1890ff', width: 2 } },
                  { x: curvesData.hf_metrics.half_life?.horizons, y: curvesData.hf_metrics.half_life?.ls, type: 'scatter', mode: 'lines+markers', name: 'Long-Short', line: { color: '#722ed1', width: 2 } },
                ]}
                layout={{ title: { text: '信号半衰期（预测后 N bars 收益衰减）' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: true, legend: { orientation: 'h', y: 1.15 }, xaxis: { title: { text: 'Horizon (bars)' }, dtick: 5 }, yaxis: { title: { text: 'bp' }, zeroline: true, zerolinecolor: '#ddd' } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </Col>
            {/* 容量曲线 */}
            <Col span={12}>
              <Plot
                data={[
                  { x: curvesData.hf_metrics.capacity?.aum, y: curvesData.hf_metrics.capacity?.net_alpha_bp, type: 'scatter', mode: 'lines+markers', name: 'Net Alpha', line: { color: '#13c2c2', width: 2 }, fill: 'tozeroy', fillcolor: 'rgba(19,194,194,0.08)' },
                ]}
                layout={{ title: { text: '容量曲线（资金规模 vs 净Alpha）' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: false, xaxis: { title: { text: 'AUM（亿元）' }, type: 'log' }, yaxis: { title: { text: 'bp/bar' }, zeroline: true, zerolinecolor: '#ff4d4f', zerolinewidth: 2 } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </Col>
          </Row>
          ) : (
          /* ===== 通用看板（日线模型） ===== */
          <Row gutter={[16, 16]}>
            {/* Loss 曲线 */}
            <Col span={12}>
              <Plot
                data={[
                  { x: curvesData.epochs, y: curvesData.train_loss, type: 'scatter', mode: 'lines', name: 'Train Loss', line: { color: '#1890ff', width: 1.5 } },
                  { x: curvesData.epochs, y: curvesData.valid_loss, type: 'scatter', mode: 'lines', name: 'Valid Loss', line: { color: '#ff4d4f', width: 1.5 } },
                ]}
                layout={{ title: { text: '损失曲线 (Loss)' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: true, legend: { orientation: 'h', y: 1.15 }, xaxis: { title: { text: 'Epoch' } } }}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: '100%' }}
              />
            </Col>
            {/* RankIC + 滚动均值 */}
            <Col span={12}>
              {curvesData.signal_curves ? (
                <Plot
                  data={[
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.rank_ic, type: 'scatter', mode: 'lines', name: 'RankIC', line: { color: 'rgba(24,144,255,0.4)', width: 1 } },
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.rank_ic_ma20, type: 'scatter', mode: 'lines', name: 'MA20', line: { color: '#1890ff', width: 2 } },
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.rank_ic_ma60, type: 'scatter', mode: 'lines', name: 'MA60', line: { color: '#ff4d4f', width: 2 } },
                  ]}
                  layout={{ title: { text: 'RankIC（验证集）+ 滚动均值' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: true, legend: { orientation: 'h', y: 1.15 }, xaxis: { title: { text: '日期' } }, yaxis: { zeroline: true, zerolinecolor: '#ddd' } }}
                  config={{ responsive: true, displayModeBar: false }}
                  style={{ width: '100%' }}
                />
              ) : <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>{curvesJob?.status === 'running' ? '信号曲线计算中...' : '该任务无信号曲线数据（需重新训练）'}</div>}
            </Col>
            {/* RankICIR */}
            <Col span={12}>
              {curvesData.signal_curves ? (
                <Plot
                  data={[
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.rank_icir, type: 'scatter', mode: 'lines', name: 'RankICIR', line: { color: '#722ed1', width: 2 }, fill: 'tozeroy', fillcolor: 'rgba(114,46,209,0.08)' },
                  ]}
                  layout={{ title: { text: 'RankICIR（累计信息比率）' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: false, xaxis: { title: { text: '日期' } }, yaxis: { zeroline: true, zerolinecolor: '#ddd' } }}
                  config={{ responsive: true, displayModeBar: false }}
                  style={{ width: '100%' }}
                />
              ) : <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>{curvesJob?.status === 'running' ? '信号曲线计算中...' : '该任务无信号曲线数据（需重新训练）'}</div>}
            </Col>
            {/* Long-Short 净值 + Net Alpha */}
            <Col span={12}>
              {curvesData.signal_curves ? (
                <Plot
                  data={[
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.ls_cum, type: 'scatter', mode: 'lines', name: 'Long-Short 累计', line: { color: '#1890ff', width: 2 } },
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.net_alpha_cum, type: 'scatter', mode: 'lines', name: 'Net Alpha（扣费后）', line: { color: '#52c41a', width: 2, dash: 'dot' } },
                  ]}
                  layout={{ title: { text: 'Long-Short 净值 & 成本后净Alpha' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: true, legend: { orientation: 'h', y: 1.15 }, xaxis: { title: { text: '日期' } }, yaxis: { zeroline: true, zerolinecolor: '#ddd' } }}
                  config={{ responsive: true, displayModeBar: false }}
                  style={{ width: '100%' }}
                />
              ) : <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>{curvesJob?.status === 'running' ? '信号曲线计算中...' : '该任务无信号曲线数据（需重新训练）'}</div>}
            </Col>
            {/* 分层累计收益 */}
            <Col span={12}>
              {curvesData.signal_curves?.decile_cum ? (
                <Plot
                  data={[
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.decile_cum.D10, type: 'scatter', mode: 'lines', name: 'Top (D10)', line: { color: '#ff4d4f', width: 2 } },
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.decile_cum.D1, type: 'scatter', mode: 'lines', name: 'Bottom (D1)', line: { color: '#1890ff', width: 2 } },
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.decile_cum.D5, type: 'scatter', mode: 'lines', name: 'Mid (D5)', line: { color: '#faad14', width: 1.5, dash: 'dash' } },
                  ]}
                  layout={{ title: { text: '分层累计收益（Decile）' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: true, legend: { orientation: 'h', y: 1.15 }, xaxis: { title: { text: '日期' } }, yaxis: { zeroline: true, zerolinecolor: '#ddd' } }}
                  config={{ responsive: true, displayModeBar: false }}
                  style={{ width: '100%' }}
                />
              ) : <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>{curvesJob?.status === 'running' ? '信号曲线计算中...' : '该任务无信号曲线数据（需重新训练）'}</div>}
            </Col>
            {/* 换手率 */}
            <Col span={12}>
              {curvesData.signal_curves ? (
                <Plot
                  data={[
                    { x: curvesData.signal_curves.dates, y: curvesData.signal_curves.turnover, type: 'scatter', mode: 'lines', name: 'Turnover', line: { color: '#13c2c2', width: 1.5 }, fill: 'tozeroy', fillcolor: 'rgba(19,194,194,0.1)' },
                  ]}
                  layout={{ title: { text: '换手率 (Turnover)' }, height: 260, margin: { l: 55, r: 20, t: 40, b: 35 }, showlegend: false, xaxis: { title: { text: '日期' } }, yaxis: { rangemode: 'tozero', tickformat: '.0%' } }}
                  config={{ responsive: true, displayModeBar: false }}
                  style={{ width: '100%' }}
                />
              ) : <div style={{ height: 260, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#999' }}>{curvesJob?.status === 'running' ? '信号曲线计算中...' : '该任务无信号曲线数据（需重新训练）'}</div>}
            </Col>
          </Row>
          )
        ) : (
          <div style={{ textAlign: 'center', padding: '40px 0', color: '#999' }}>
            {curvesJob?.status === 'running' ? <LoadingOutlined spin style={{ fontSize: 24, marginBottom: 8 }} /> : null}
            <div>{curvesJob?.status === 'running' ? '训练进行中，数据实时更新中...' : '暂无训练曲线数据'}</div>
          </div>
        )}
      </Modal>

      {/* 删除确认弹窗 */}
      <Modal
        title={null}
        open={!!deleteJobId}
        onCancel={() => setDeleteJobId(null)}
        centered
        width={420}
        footer={
          <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
            <Button onClick={() => setDeleteJobId(null)}>取消</Button>
            <Button danger type="primary" onClick={() => { if (deleteJobId) handleDelete(deleteJobId); setDeleteJobId(null) }}>
              确认删除
            </Button>
          </Space>
        }
      >
        <div style={{ textAlign: 'center', padding: '12px 0' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⚠️</div>
          <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>确定删除此训练任务？</div>
          <div style={{ fontSize: 13, color: '#ff4d4f', fontWeight: 500 }}>
            删除后，训练结果数据和模型文件均将被永久删除，无法恢复。
          </div>
        </div>
      </Modal>
    </div>
  )
}
