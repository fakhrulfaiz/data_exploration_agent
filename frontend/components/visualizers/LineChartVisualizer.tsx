import { useRef, useMemo } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid } from 'recharts';
import { ChartContainer, ChartTooltip, ChartTooltipContent, ChartLegend, ChartLegendContent, type ChartConfig } from '../ui/chart';

type YAxisConfig = {
  key: string;
  label?: string;
  color?: string;
};

export interface LineChartSpec {
  type: 'line';
  title?: string;
  data: Array<Record<string, string | number>>;
  config?: {
    xAxis?: { key?: string; label?: string };
    yAxis?: YAxisConfig[];
  };
  metadata?: Record<string, unknown>;
}

interface LineChartVisualizerProps {
  spec: LineChartSpec;
}

function inferXAxisKey(rows: Array<Record<string, unknown>>, configuredKey?: string): string {
  if (configuredKey) return configuredKey;
  if (!rows || rows.length === 0) return '';
  const candidateKeys = Object.keys(rows[0] || {});
  return candidateKeys[0] || '';
}

function inferYAxisKeys(
  rows: Array<Record<string, unknown>>,
  configuredKeys?: string[],
  xKey?: string
): string[] {
  if (configuredKeys && configuredKeys.length > 0) return configuredKeys;
  if (!rows || rows.length === 0) return [];
  const firstRow = rows[0] || {};
  return Object.keys(firstRow).filter((k) => k !== xKey);
}

// Use actual color values (matching pie chart style)
// These are fallback colors that work in both light and dark mode
const COLORS = [
  '#72e3ad', // chart-1 light
  '#3b82f6', // chart-2 light
  '#8b5cf6', // chart-3 light
  '#f59e0b', // chart-4 light
  '#10b981', // chart-5 light
  '#a78bfa',
  '#34d399'
];

// Dark mode colors
const COLORS_DARK = [
  '#4ade80', // chart-1 dark
  '#60a5fa', // chart-2 dark
  '#a78bfa', // chart-3 dark
  '#fbbf24', // chart-4 dark
  '#2dd4bf', // chart-5 dark
  '#a78bfa',
  '#34d399'
];

const cardClass = 'bg-background rounded-lg border border-border p-4';

export default function LineChartVisualizer({ spec }: LineChartVisualizerProps) {
  if (!spec) return null;

  const chartRef = useRef<HTMLDivElement>(null);
  const rows = Array.isArray(spec.data) ? spec.data : [];
  const xKey = inferXAxisKey(rows, spec?.config?.xAxis?.key);
  const yKeys = inferYAxisKeys(
    rows,
    spec?.config?.yAxis?.map((y) => y.key),
    xKey
  );


  // Detect dark mode
  const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
  const activeColors = isDark ? COLORS_DARK : COLORS;

  // Get color for each line from config or use default
  const getLineColor = (key: string, index: number): string => {
    const yAxisConfig = spec?.config?.yAxis?.find(y => y.key === key);
    return yAxisConfig?.color || activeColors[index % activeColors.length];
  };

  // Create chart config for shadcn chart components
  const chartConfig = useMemo<ChartConfig>(() => {
    const config: ChartConfig = {};
    yKeys.forEach((key, index) => {
      const yAxisConfig = spec?.config?.yAxis?.find(y => y.key === key);
      config[key] = {
        label: yAxisConfig?.label || key,
        color: yAxisConfig?.color || activeColors[index % activeColors.length],
      };
    });
    // Add x-axis config if needed
    if (xKey && !config[xKey]) {
      config[xKey] = {
        label: spec?.config?.xAxis?.label || xKey,
      };
    }
    return config;
  }, [yKeys, xKey, spec?.config, activeColors]);

  return (
    <div className={cardClass}>
      <div ref={chartRef}>
        {spec?.title ? (
          <h2 className="text-base font-semibold mb-3 text-foreground">{spec.title}</h2>
        ) : null}
        <div className="w-full h-[calc(60vh-2rem)] min-h-[300px]">
        <ChartContainer config={chartConfig} className="h-full w-full">
          <LineChart data={rows} margin={{ top: 20, right: 30, left: 20, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={typeof document !== 'undefined' && document.documentElement.classList.contains('dark') ? '#404040' : '#e5e7eb'} />
            <XAxis
              dataKey={xKey}
              label={spec?.config?.xAxis?.label ? { value: spec.config.xAxis.label, position: 'insideBottom', offset: -5 } : undefined}
              stroke={typeof document !== 'undefined' && document.documentElement.classList.contains('dark') ? '#d4d4d4' : '#6b7280'}
              height={80}
              angle={-45}
              textAnchor="end"
            />
            <YAxis stroke={typeof document !== 'undefined' && document.documentElement.classList.contains('dark') ? '#d4d4d4' : '#6b7280'} />
            <ChartTooltip 
              content={<ChartTooltipContent indicator="line" />}
            />
            <ChartLegend 
              content={<ChartLegendContent />}
              verticalAlign="bottom" 
              height={50}
              wrapperStyle={{ paddingTop: '10px', paddingBottom: '10px' }}
            />
            {yKeys.map((key, index) => (
              <Line
                key={key}
                type="monotone"
                dataKey={key}
                stroke={getLineColor(key, index)}
                strokeWidth={3}
                dot={{ fill: getLineColor(key, index), r: 4 }}
                activeDot={{ r: 6 }}
              />
            ))}
          </LineChart>
        </ChartContainer>
        </div>
      </div>
    </div>
  );
}