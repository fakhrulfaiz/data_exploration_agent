"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  X,
  ImageIcon,
  FileSpreadsheet,
  RefreshCw,
  Download,
  Maximize2,
  ChevronDown,
  ChevronRight,
  Table as TableIcon,
} from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";

interface GeneratedFile {
  filename: string;
  url: string;
  size: number;
  modified: number;
}

interface GeneratedFilesResponse {
  plots: GeneratedFile[];
  outputs: GeneratedFile[];
}

interface CsvData {
  filename: string;
  columns: string[];
  total_rows: number;
  data: Record<string, any>[];
}

interface OutputsPanelProps {
  open: boolean;
  onClose: () => void;
  // Optional: specific files to show (from agent response)
  plotUrls?: string[];
  outputUrls?: string[];
}

const OutputsPanel: React.FC<OutputsPanelProps> = ({
  open,
  onClose,
  plotUrls,
  outputUrls,
}) => {
  const [loading, setLoading] = useState(false);
  const [files, setFiles] = useState<GeneratedFilesResponse | null>(null);
  const [expandedImage, setExpandedImage] = useState<string | null>(null);
  const [selectedCsv, setSelectedCsv] = useState<CsvData | null>(null);
  const [loadingCsv, setLoadingCsv] = useState(false);
  const [plotsExpanded, setPlotsExpanded] = useState(true);
  const [outputsExpanded, setOutputsExpanded] = useState(true);

  // Fetch all generated files
  const fetchGeneratedFiles = useCallback(async () => {
    setLoading(true);
    try {
      const response = await fetch("/api/v1/data/generated-files");
      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          setFiles(result.data);
        }
      }
    } catch (error) {
      console.error("Failed to fetch generated files:", error);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch CSV data for table display
  const fetchCsvData = async (filename: string) => {
    setLoadingCsv(true);
    try {
      const response = await fetch(`/api/v1/data/output/${filename}`);
      if (response.ok) {
        const result = await response.json();
        if (result.status === "success") {
          setSelectedCsv(result.data);
        }
      }
    } catch (error) {
      console.error("Failed to fetch CSV data:", error);
    } finally {
      setLoadingCsv(false);
    }
  };

  // Download a file
  const handleDownload = async (url: string, filename: string) => {
    try {
      const response = await fetch(url);
      const blob = await response.blob();
      const downloadUrl = window.URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(downloadUrl);
    } catch (error) {
      console.error("Failed to download file:", error);
    }
  };

  // Format file size
  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  // Format timestamp
  const formatTime = (timestamp: number): string => {
    const date = new Date(timestamp * 1000);
    return date.toLocaleString();
  };

  // Load files when panel opens
  useEffect(() => {
    if (open) {
      fetchGeneratedFiles();
    }
  }, [open, fetchGeneratedFiles]);

  // Determine which files to display
  const displayPlots = plotUrls?.length
    ? plotUrls.map((url) => ({
        filename: url.split("/").pop() || "plot",
        url,
        size: 0,
        modified: Date.now() / 1000,
      }))
    : files?.plots || [];

  const displayOutputs = outputUrls?.length
    ? outputUrls.map((url) => ({
        filename: url.split("/").pop() || "output.csv",
        url,
        size: 0,
        modified: Date.now() / 1000,
      }))
    : files?.outputs || [];

  if (!open) return null;

  return (
    <>
      {/* Main Panel */}
      <div
        className={`fixed inset-y-0 right-0 w-full md:w-[700px] lg:w-[900px] bg-background border-l shadow-xl transform transition-transform duration-300 ease-in-out z-50 flex flex-col ${
          open ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <div className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5 text-primary" />
            <h2 className="text-lg font-semibold">Generated Outputs</h2>
            <Badge variant="outline" className="ml-2">
              {displayPlots.length + displayOutputs.length} files
            </Badge>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={fetchGeneratedFiles}
              disabled={loading}
              title="Refresh"
            >
              <RefreshCw
                className={`h-5 w-5 ${loading ? "animate-spin" : ""}`}
              />
            </Button>
            <Button variant="ghost" size="icon" onClick={onClose}>
              <X className="h-5 w-5" />
            </Button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 space-y-6">
          {loading && !files ? (
            <div className="flex items-center justify-center h-32">
              <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {/* Plots Section */}
              <Collapsible open={plotsExpanded} onOpenChange={setPlotsExpanded}>
                <Card>
                  <CardHeader className="pb-2">
                    <CollapsibleTrigger asChild>
                      <button className="flex items-center justify-between w-full text-left">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                          <ImageIcon className="h-4 w-4" />
                          Plots & Visualizations
                          <Badge variant="secondary" className="ml-2">
                            {displayPlots.length}
                          </Badge>
                        </CardTitle>
                        {plotsExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                    </CollapsibleTrigger>
                  </CardHeader>
                  <CollapsibleContent>
                    <CardContent>
                      {displayPlots.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          No plots generated yet.
                        </p>
                      ) : (
                        <div
                          className="grid gap-4"
                          style={{
                            gridTemplateColumns:
                              displayPlots.length > 1
                                ? "repeat(auto-fit, minmax(280px, 1fr))"
                                : "1fr",
                          }}
                        >
                          {displayPlots.map((plot, idx) => (
                            <div
                              key={idx}
                              className="group relative rounded-lg border border-border overflow-hidden bg-muted/20"
                            >
                              <img
                                src={plot.url}
                                alt={plot.filename}
                                className="w-full h-auto object-contain max-h-[300px] cursor-pointer transition-transform hover:scale-[1.02]"
                                onClick={() => setExpandedImage(plot.url)}
                                onError={(e) => {
                                  (e.target as HTMLImageElement).style.display =
                                    "none";
                                }}
                              />
                              <div className="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                <button
                                  onClick={() => setExpandedImage(plot.url)}
                                  className="p-1.5 rounded bg-background/80 hover:bg-background"
                                  title="Expand"
                                >
                                  <Maximize2 className="w-4 h-4" />
                                </button>
                                <button
                                  onClick={() =>
                                    handleDownload(plot.url, plot.filename)
                                  }
                                  className="p-1.5 rounded bg-background/80 hover:bg-background"
                                  title="Download"
                                >
                                  <Download className="w-4 h-4" />
                                </button>
                              </div>
                              <div className="p-2 text-xs text-muted-foreground border-t bg-muted/30">
                                <span className="font-medium">
                                  {plot.filename}
                                </span>
                                {plot.size > 0 && (
                                  <span className="ml-2">
                                    ({formatSize(plot.size)})
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </CardContent>
                  </CollapsibleContent>
                </Card>
              </Collapsible>

              {/* Outputs (CSV) Section */}
              <Collapsible
                open={outputsExpanded}
                onOpenChange={setOutputsExpanded}
              >
                <Card>
                  <CardHeader className="pb-2">
                    <CollapsibleTrigger asChild>
                      <button className="flex items-center justify-between w-full text-left">
                        <CardTitle className="text-sm font-medium flex items-center gap-2">
                          <TableIcon className="h-4 w-4" />
                          Data Outputs (CSV)
                          <Badge variant="secondary" className="ml-2">
                            {displayOutputs.length}
                          </Badge>
                        </CardTitle>
                        {outputsExpanded ? (
                          <ChevronDown className="h-4 w-4" />
                        ) : (
                          <ChevronRight className="h-4 w-4" />
                        )}
                      </button>
                    </CollapsibleTrigger>
                  </CardHeader>
                  <CollapsibleContent>
                    <CardContent className="space-y-4">
                      {displayOutputs.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          No CSV outputs generated yet.
                        </p>
                      ) : (
                        <>
                          {/* File List */}
                          <div className="space-y-2">
                            {displayOutputs.map((output, idx) => (
                              <div
                                key={idx}
                                className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors ${
                                  selectedCsv?.filename === output.filename
                                    ? "border-primary bg-primary/5"
                                    : "border-border hover:bg-muted/50"
                                }`}
                                onClick={() => fetchCsvData(output.filename)}
                              >
                                <div className="flex items-center gap-3">
                                  <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
                                  <div>
                                    <p className="text-sm font-medium">
                                      {output.filename}
                                    </p>
                                    {output.size > 0 && (
                                      <p className="text-xs text-muted-foreground">
                                        {formatSize(output.size)} •{" "}
                                        {formatTime(output.modified)}
                                      </p>
                                    )}
                                  </div>
                                </div>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    handleDownload(output.url, output.filename);
                                  }}
                                >
                                  <Download className="h-4 w-4" />
                                </Button>
                              </div>
                            ))}
                          </div>

                          {/* Selected CSV Preview */}
                          {selectedCsv && (
                            <Card className="mt-4">
                              <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium flex items-center gap-2">
                                  <TableIcon className="h-4 w-4" />
                                  {selectedCsv.filename}
                                  <Badge variant="outline" className="ml-2">
                                    {selectedCsv.total_rows} rows
                                  </Badge>
                                </CardTitle>
                              </CardHeader>
                              <CardContent className="p-0">
                                {loadingCsv ? (
                                  <div className="flex items-center justify-center h-32">
                                    <RefreshCw className="h-5 w-5 animate-spin" />
                                  </div>
                                ) : (
                                  <div className="overflow-auto max-h-[400px] border-t">
                                    <Table>
                                      <TableHeader>
                                        <TableRow>
                                          {selectedCsv.columns.map((col) => (
                                            <TableHead
                                              key={col}
                                              className="whitespace-nowrap sticky top-0 bg-background z-10"
                                            >
                                              {col}
                                            </TableHead>
                                          ))}
                                        </TableRow>
                                      </TableHeader>
                                      <TableBody>
                                        {selectedCsv.data
                                          .slice(0, 50)
                                          .map((row, idx) => (
                                            <TableRow key={idx}>
                                              {selectedCsv.columns.map(
                                                (col) => (
                                                  <TableCell
                                                    key={`${idx}-${col}`}
                                                    className="whitespace-nowrap"
                                                  >
                                                    {row[col] !== null ? (
                                                      String(row[col])
                                                    ) : (
                                                      <span className="text-muted-foreground italic">
                                                        null
                                                      </span>
                                                    )}
                                                  </TableCell>
                                                )
                                              )}
                                            </TableRow>
                                          ))}
                                      </TableBody>
                                    </Table>
                                    {selectedCsv.total_rows > 50 && (
                                      <p className="text-xs text-muted-foreground text-center py-2 border-t">
                                        Showing first 50 of{" "}
                                        {selectedCsv.total_rows} rows
                                      </p>
                                    )}
                                  </div>
                                )}
                              </CardContent>
                            </Card>
                          )}
                        </>
                      )}
                    </CardContent>
                  </CollapsibleContent>
                </Card>
              </Collapsible>
            </>
          )}
        </div>
      </div>

      {/* Expanded Image Modal */}
      {expandedImage && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-black/80 p-4"
          onClick={() => setExpandedImage(null)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh]">
            <img
              src={expandedImage}
              alt="Expanded plot"
              className="max-w-full max-h-[90vh] object-contain rounded-lg"
            />
            <button
              onClick={() => setExpandedImage(null)}
              className="absolute top-2 right-2 p-2 rounded-full bg-background/80 hover:bg-background text-foreground"
            >
              ✕
            </button>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleDownload(
                  expandedImage,
                  expandedImage.split("/").pop() || "plot.png"
                );
              }}
              className="absolute top-2 right-12 p-2 rounded-full bg-background/80 hover:bg-background text-foreground"
              title="Download"
            >
              <Download className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </>
  );
};

export default OutputsPanel;
