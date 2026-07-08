import { useState, useEffect } from 'react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer,
} from 'recharts'
import { api } from '../api/client'

const COLOURS = [
  '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ec4899',
]

const fmtWeek = str => {
  const d = new Date(str + 'T00:00:00')
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export default function VendorWeeklyChart({ hotelId, dateRange = {} }) {
  const [chartData, setChartData] = useState(null)
  const key = JSON.stringify({ hotelId, dateRange })

  useEffect(() => {
    setChartData(null)
    api.vendorWeekly(hotelId, dateRange)
      .then(r => setChartData(r.data))
      .catch(() => setChartData({ vendors: [], weeks: [] }))
  }, [key]) // eslint-disable-line react-hooks/exhaustive-deps

  if (!chartData) return null
  if (!chartData.vendors.length || chartData.weeks.length < 2) return null

  const { vendors, weeks } = chartData
  const chartHeight = Math.max(200, weeks.length * 12 + 80)

  return (
    <div className="card p-4">
      <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">
        Weekly Vendor Breakdown
      </p>
      <p className="text-[10px] text-slate-400 mb-3">
        Bookings per week · top {vendors.length} vendors · excludes Cancelled
      </p>
      <ResponsiveContainer width="100%" height={chartHeight}>
        <BarChart
          data={weeks}
          margin={{ top: 4, right: 12, left: 0, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey="week"
            tickFormatter={fmtWeek}
            tick={{ fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 10 }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip
            formatter={(value, name) => [value, name]}
            labelFormatter={fmtWeek}
          />
          <Legend
            wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
            formatter={v => <span className="text-slate-600">{v}</span>}
          />
          {vendors.map((vendor, i) => (
            <Bar
              key={vendor}
              dataKey={vendor}
              stackId="v"
              fill={COLOURS[i % COLOURS.length]}
              maxBarSize={32}
              radius={i === vendors.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
