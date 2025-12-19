"use client";

import React from 'react';
import { X, Table as TableIcon, Database } from 'lucide-react';
import type { DataFramePreviewData } from '@/types';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

interface DataFramePanelProps {
    open: boolean;
    onClose: () => void;
    data: DataFramePreviewData | null;
}

const DataFramePanel: React.FC<DataFramePanelProps> = ({
    open,
    onClose,
    data
}) => {
    const pageSize = 20;


    const [page, setPage] = React.useState(0);

    // Reset page when df_id changes
    React.useEffect(() => {
        setPage(0);
    }, [data?.df_id]);

    // Guard - return early after all hooks are called
    if (!open || !data) return null;

    const totalPreviewRows = data.preview_rows;
    const totalPages = Math.max(1, Math.ceil(totalPreviewRows / pageSize));
    const currentPage = Math.min(page, totalPages - 1);
    const startIndex = currentPage * pageSize;
    const endIndex = startIndex + pageSize;
    const visibleRows = data.data.slice(startIndex, endIndex);

    const handlePrevPage = () => {
        setPage((p) => Math.max(0, p - 1));
    };

    const handleNextPage = () => {
        setPage((p) => Math.min(totalPages - 1, p + 1));
    };

    return (
        <div className={`fixed inset-y-0 right-0 w-full md:w-[600px] lg:w-[800px] bg-background border-l shadow-xl transform transition-transform duration-300 ease-in-out z-50 flex flex-col ${open ? 'translate-x-0' : 'translate-x-full'}`}>
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b">
                <div className="flex items-center gap-2">
                    <Database className="h-5 w-5 text-primary" />
                    <h2 className="text-lg font-semibold">Data Context</h2>
                </div>
                <button
                    onClick={onClose}
                    className="p-2 hover:bg-accent rounded-full transition-colors"
                >
                    <X className="h-5 w-5" />
                </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-hidden p-4 flex flex-col gap-4">
                {/* Metadata Card */}
                <Card>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-sm font-medium text-muted-foreground">DataFrame Info</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 gap-4 text-sm">
                            <div>
                                <span className="text-muted-foreground">Rows:</span>
                                <span className="ml-2 font-medium">{data.total_rows.toLocaleString()}</span>
                            </div>
                            <div>
                                <span className="text-muted-foreground">Columns:</span>
                                <span className="ml-2 font-medium">{data.columns.length}</span>
                            </div>
                            <div className="col-span-2">
                                <span className="text-muted-foreground">ID:</span>
                                <code className="ml-2 bg-muted px-1 py-0.5 rounded text-xs">{data.df_id}</code>
                            </div>
                        </div>
                    </CardContent>
                </Card>

                {/* Data Table */}
                <Card className="flex-1 flex flex-col min-h-0">
                    <CardHeader className="pb-2 flex flex-row items-center justify-between">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                            <TableIcon className="h-4 w-4" />
                            Preview (first {data.preview_rows} rows)
                        </CardTitle>
                        <div className="flex items-center gap-2 text-xs text-muted-foreground">
                            <span>
                                Rows {Math.min(startIndex + 1, totalPreviewRows)}-
                                {Math.min(endIndex, totalPreviewRows)} of {data.total_rows.toLocaleString()}
                            </span>
                            <Badge variant="outline">Read-only</Badge>
                        </div>
                    </CardHeader>
                    <CardContent className="flex-1 p-0 overflow-hidden flex flex-col">
                        {/* Scrollable table area */}
                        <ScrollArea className="flex-1 w-full">
                            <div className="p-4">
                                <Table>
                                    <TableHeader>
                                        <TableRow>
                                            {data.columns.map((col) => (
                                                <TableHead key={col} className="whitespace-nowrap">
                                                    {col}
                                                </TableHead>
                                            ))}
                                        </TableRow>
                                    </TableHeader>
                                    <TableBody>
                                        {visibleRows.map((row, idx) => (
                                            <TableRow key={`${startIndex + idx}`}>
                                                {data.columns.map((col) => (
                                                    <TableCell key={`${startIndex + idx}-${col}`} className="whitespace-nowrap">
                                                        {row[col] !== null ? String(row[col]) : <span className="text-muted-foreground italic">null</span>}
                                                    </TableCell>
                                                ))}
                                            </TableRow>
                                        ))}
                                    </TableBody>
                                </Table>
                            </div>
                        </ScrollArea>

                        {/* Fixed footer with pagination controls */}
                        <div className="flex items-center justify-between px-4 py-2 border-t text-xs text-muted-foreground bg-background/60 backdrop-blur-sm">
                            <span>
                                Page {currentPage + 1} of {totalPages}
                            </span>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={handlePrevPage}
                                    disabled={currentPage === 0}
                                    className="px-2 py-1 rounded border text-xs disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent"
                                >
                                    Prev
                                </button>
                                <button
                                    onClick={handleNextPage}
                                    disabled={currentPage >= totalPages - 1}
                                    className="px-2 py-1 rounded border text-xs disabled:opacity-50 disabled:cursor-not-allowed hover:bg-accent"
                                >
                                    Next
                                </button>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
};

export default DataFramePanel;
