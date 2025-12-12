import { PieChart, Pie, Cell } from 'recharts';
import { useRef, useMemo } from 'react';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '../ui/chart';

type PieVariant = 'simple' | 'donut' | 'two-level' | 'straight-angle';

type PieConfig = {
    variant?: PieVariant;
    categoryKey?: string;
    valueKey?: string;
    innerRadius?: number;
    outerRadius?: number;
    showPercentage?: boolean;
    showLabels?: boolean;
    paddingAngle?: number;
    nested?: {
        enabled: boolean;
        innerData: Array<Record<string, any>>;
        outerData: Array<Record<string, any>>;
    };
    multiple?: {
        enabled: boolean;
        pies: Array<{
            data: Array<Record<string, any>>;
            cx: string;
            title: string;
        }>;
    };
};

export interface PieChartSpec {
	type: 'pie';
	title?: string;
	data: Array<Record<string, string | number>>;
	config?: PieConfig;
	metadata?: Record<string, unknown>;
}

interface PieChartVisualizerProps {
	spec: PieChartSpec;
}

// Use actual color values (will be themed via ChartContainer CSS variables)
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


// Helper to render labels based on configuration
interface LabelProps {
    payload: Record<string, any>;
    percent?: number;
}

const renderLabel = (props: LabelProps, config: PieConfig | undefined, categoryKey: string) => {
    const name = props.payload[categoryKey];
    if (config?.showPercentage && typeof props.percent === 'number') {
        return `${name} ${(props.percent * 100).toFixed(0)}%`;
    }
    return name;
};

function inferCategoryKey(rows: Array<Record<string, unknown>>, configuredKey?: string): string {
	if (configuredKey) return configuredKey;
	if (!rows || rows.length === 0) return '';
	const candidateKeys = Object.keys(rows[0] || {});
	return candidateKeys.find((k) => typeof (rows[0] as any)[k] === 'string') || candidateKeys[0] || '';
}

function inferValueKey(rows: Array<Record<string, unknown>>, configuredKey?: string, categoryKey?: string): string {
	if (configuredKey) return configuredKey;
	if (!rows || rows.length === 0) return '';
	const candidateKeys = Object.keys(rows[0] || {});
	return candidateKeys.find((k) => k !== categoryKey && typeof (rows[0] as any)[k] === 'number') || candidateKeys.find((k) => k !== categoryKey) || '';
}

export default function PieChartVisualizer({ spec }: PieChartVisualizerProps) {
    if (!spec) return null;
    
    const chartRef = useRef<HTMLDivElement>(null);
    const rows = Array.isArray(spec.data) ? spec.data : [];
    const categoryKey = inferCategoryKey(rows, spec?.config?.categoryKey);
    const valueKey = inferValueKey(rows, spec?.config?.valueKey, categoryKey);

    // Get configuration values with defaults
    const variant = spec.config?.variant || 'simple';
    const innerRadius = spec.config?.innerRadius ?? (variant === 'donut' ? 50 : 0);
    // Make pie smaller to prevent label clipping while keeping labels visible
    const outerRadius = spec.config?.outerRadius ?? 90;
    const paddingAngle = spec.config?.paddingAngle ?? 0;
    const showLabels = spec.config?.showLabels ?? true;

    // Detect dark mode
    const isDark = typeof document !== 'undefined' && document.documentElement.classList.contains('dark');
    const activeColors = isDark ? COLORS_DARK : COLORS;

    // Create chart config for shadcn chart components
    const chartConfig = useMemo<ChartConfig>(() => {
        const config: ChartConfig = {};
        // Add config for each unique category/value pair
        rows.forEach((row, index) => {
            const category = String(row[categoryKey] || `Item ${index}`);
            if (!config[category]) {
                config[category] = {
                    label: category,
                    color: activeColors[index % activeColors.length],
                };
            }
        });
        // Also add config for the value key
        if (valueKey && !config[valueKey]) {
            config[valueKey] = {
                label: valueKey,
            };
        }
        return config;
    }, [rows, categoryKey, valueKey, activeColors]);

    // Render different pie chart variants
    const renderPieChart = () => {
        switch (variant) {
            case 'two-level':
                const innerData = spec.config?.nested?.innerData || [];
                const outerData = spec.config?.nested?.outerData || [];
            
                // Create color map for parent categories
                const parentColorMap = new Map(
                    innerData.map((item, index) => [
                        item.name || item[categoryKey],
                        activeColors[index % activeColors.length]
                    ])
                );

                return (
                  <>
                        <Pie
                            data={innerData}
                            dataKey="count"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            outerRadius={90}
                            fill="#8884d8"
                            label={showLabels}
                        >
                            {innerData.map((_, index) => (
                                <Cell 
                                    key={`cell-inner-${index}`} 
                                    fill={activeColors[index % activeColors.length]} 
                                />
                            ))}
                        </Pie>
                        <Pie
                            data={outerData}
                            dataKey="count"
                            nameKey="name"
                            cx="50%"
                            cy="50%"
                            innerRadius={90}
                            outerRadius={120}
                            fill="#82ca9d"
                            label={showLabels}
                        >
                            {outerData.map((entry, index) => (
                                <Cell 
                                    key={`cell-outer-${index}`} 
                                    fill={parentColorMap.get(entry.parent) || activeColors[(index + 3) % activeColors.length]} 
                                    fillOpacity={0.7}
                                />
                            ))}
                        </Pie>
                    </>
                );
            
            
            case 'straight-angle':
                return (
                    <Pie
                        data={rows}
                        cx="50%"
                        cy="50%"
                        startAngle={0}
                        endAngle={180}
                        innerRadius={innerRadius}
                        outerRadius={outerRadius}
                        fill="#8884d8"
                        dataKey={valueKey}
                        nameKey={categoryKey}
                        label={showLabels ? (props) => renderLabel(props, spec.config, categoryKey) : false}
                        labelLine={showLabels}
                        paddingAngle={paddingAngle}
                    >
                        {rows.map((_, index) => (
                            <Cell key={`cell-${index}`} fill={activeColors[index % activeColors.length]} />
                        ))}
                    </Pie>
                );
            
            default: // simple or donut
                return (
                    <Pie
                        data={rows}
                        cx="50%"
                        cy="50%"
                        innerRadius={innerRadius}
                        outerRadius={outerRadius}
                        fill="#8884d8"
                        dataKey={valueKey}
                        nameKey={categoryKey}
                        label={showLabels ? (props) => renderLabel(props, spec.config, categoryKey) : false}
                        labelLine={showLabels}
                        paddingAngle={paddingAngle}
                    >
                        {rows.map((_, index) => (
                            <Cell key={`cell-${index}`} fill={activeColors[index % activeColors.length]} />
                        ))}
                    </Pie>
                );
        }
    };

    return (
        <div className={`${cardClass} overflow-visible`}>
            <div ref={chartRef} className="overflow-visible">
                {spec?.title && (
                    <h2 className="text-base font-semibold text-foreground mb-3">{spec.title}</h2>
                )}

                <div className="w-full h-[calc(60vh-2rem)] min-h-[300px] flex items-center gap-4">
                    {/* Chart on the left */}
                    <div className="flex-1 flex items-center justify-center min-w-0" style={{ overflow: 'visible' }}>
                        <div style={{ width: '100%', height: '100%', overflow: 'visible', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <ChartContainer 
                                config={chartConfig} 
                                className="h-full w-full aspect-square max-w-[min(100%,280px)]"
                                style={{ overflow: 'visible' }}
                            >
                                <PieChart 
                                    margin={{ top: 20, right: 100, left: 100, bottom: 20 }}
                                    style={{ overflow: 'visible' }}
                                >
                                    {renderPieChart()}
                                    <ChartTooltip 
                                        content={<ChartTooltipContent indicator="dot" />}
                                    />
                                </PieChart>
                            </ChartContainer>
                        </div>
                    </div>
                    {/* Legend on the right */}
                    <div className="flex-shrink-0 w-auto min-w-[150px] flex items-center justify-center">
                        <div className="flex flex-col gap-2">
                            {rows.map((row, index) => {
                                const category = String(row[categoryKey] || `Item ${index}`);
                                const color = activeColors[index % activeColors.length];
                                return (
                                    <div key={index} className="flex items-center gap-2 text-sm">
                                        <div 
                                            className="h-3 w-3 rounded-full shrink-0" 
                                            style={{ backgroundColor: color }}
                                        />
                                        <span className="text-foreground">{category}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}


