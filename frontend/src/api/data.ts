import axios from 'axios'

// === 数据源 ===
export const fetchSources = async () => {
  const res = await axios.get('/api/data/sources')
  return res.data
}

export const fetchSourceHealth = async () => {
  const res = await axios.get('/api/data/sources/health')
  return res.data
}

export const switchSource = async (sourceId: string) => {
  const res = await axios.put('/api/data/source', null, { params: { source_id: sourceId } })
  return res.data
}

// === 同步任务 ===
export const startSync = async (params: {
  source_id?: string
  market?: string
  freq?: string
  target?: string
}) => {
  const res = await axios.post('/api/data/sync/unified', null, { params })
  return res.data
}

export const fetchSyncJobs = async () => {
  const res = await axios.get('/api/data/sync/jobs')
  return res.data
}

export const stopSync = async () => {
  const res = await axios.post('/api/data/sync_qlib/stop')
  return res.data
}

// 兼容旧接口
export const startQlibSync = async (market = 'all') => {
  const res = await axios.post('/api/data/sync_qlib', null, { params: { market } })
  return res.data
}

export const fetchQlibSyncStatus = async () => {
  const res = await axios.get('/api/data/sync_qlib/status')
  return res.data
}

export const startMinuteSync = async (market = 'all', period = '1') => {
  const res = await axios.post('/api/data/sync_minute', null, { params: { market, period } })
  return res.data
}

export const fetchMinuteSyncStatus = async () => {
  const res = await axios.get('/api/data/sync_minute/status')
  return res.data
}

export const startConvert1min = async () => {
  const res = await axios.post('/api/data/convert_1min')
  return res.data
}

export const fetchConvertStatus = async () => {
  const res = await axios.get('/api/data/convert_1min/status')
  return res.data
}

// === 数据集 ===
export const fetchDatasets = async () => {
  const res = await axios.get('/api/data/datasets')
  return res.data
}

export const resyncDataset = async (datasetId: string) => {
  const res = await axios.post(`/api/data/datasets/${datasetId}/resync`)
  return res.data
}
