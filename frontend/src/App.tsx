import { useState } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import { Layout, Menu, theme } from 'antd'
import {
  DashboardOutlined,
  DatabaseOutlined,
  ExperimentOutlined,
  ThunderboltOutlined,
  SettingOutlined,
} from '@ant-design/icons'
import Dashboard from './pages/Dashboard'
import DataManager from './pages/DataManager'
import BacktestPanel from './pages/BacktestPanel'
import TradingPanel from './pages/TradingPanel'
import Settings from './pages/Settings'

const { Header, Sider, Content } = Layout

const menuItems = [
  { key: '/dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
  { key: '/data', icon: <DatabaseOutlined />, label: '数据管理' },
  { key: '/backtest', icon: <ExperimentOutlined />, label: '训练回测' },
  { key: '/trading', icon: <ThunderboltOutlined />, label: '实盘交易' },
  { key: '/settings', icon: <SettingOutlined />, label: '系统设置' },
]

function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()
  const { token: { colorBgContainer, borderRadiusLG } } = theme.useToken()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider collapsible collapsed={collapsed} onCollapse={setCollapsed}>
        <div style={{
          height: 48, margin: 16, display: 'flex', alignItems: 'center',
          justifyContent: 'center', color: '#fff', fontWeight: 'bold', fontSize: collapsed ? 14 : 18,
        }}>
          {collapsed ? 'QT' : 'QTrader'}
        </div>
        <Menu
          theme="dark"
          selectedKeys={[location.pathname]}
          mode="inline"
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Layout>
        <Header style={{ padding: '0 24px', background: colorBgContainer, display: 'flex', alignItems: 'center' }}>
          <h3 style={{ margin: 0, fontWeight: 600 }}>QTrader · AI 量化交易平台</h3>
        </Header>
        <Content style={{ margin: '16px' }}>
          <div style={{
            padding: 24, minHeight: 360,
            background: colorBgContainer, borderRadius: borderRadiusLG,
          }}>
            <Routes>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/data" element={<DataManager />} />
              <Route path="/backtest" element={<BacktestPanel />} />
              <Route path="/trading" element={<TradingPanel />} />
              <Route path="/settings" element={<Settings />} />
              <Route path="*" element={<Navigate to="/dashboard" replace />} />
            </Routes>
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  )
}
