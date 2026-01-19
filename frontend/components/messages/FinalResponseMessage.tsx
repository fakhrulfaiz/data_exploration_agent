import React, { useState } from "react";
import { Download, FileSpreadsheet, Sparkles } from "lucide-react";
import { FinalizerContent } from "@/types/chat";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { saveAs } from "file-saver";
import { markdownComponents } from "@/utils/markdownComponents";
import DataService from "@/services/api/data.service";

interface FinalResponseMessageProps {
  data: FinalizerContent;
  onSuggestionClick?: (query: string) => void;
}

const FinalResponseMessage: React.FC<FinalResponseMessageProps> = ({
  data,
  onSuggestionClick,
}) => {
  const [isExporting, setIsExporting] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  // Handlers for actions
  const handleExport = async () => {
    if (!data.actions.export_dataframe?.df_id) return;

    setIsExporting(true);
    try {
      const blob = await DataService.exportDataFrame(
        data.actions.export_dataframe.df_id,
      );
      saveAs(blob, "data_export.xlsx");
    } catch (error) {
      console.error("Export failed:", error);
      alert(error instanceof Error ? error.message : "Could not export data.");
    } finally {
      setIsExporting(false);
    }
  };

  const handleDownloadPlots = async () => {
    if (!data.actions.download_plots?.plot_urls?.length) return;

    setIsDownloading(true);
    try {
      const blob = await DataService.downloadPlots(
        data.actions.download_plots.plot_urls,
      );
      const filename =
        data.actions.download_plots.plot_urls.length > 1
          ? "plots.zip"
          : "plot.png";
      saveAs(blob, filename);
    } catch (error) {
      console.error("Download failed:", error);
      alert("Could not download plots. They may have expired.");
    } finally {
      setIsDownloading(false);
    }
  };

  return (
    <div className="flex flex-col space-y-4 max-w-none">
      {/* 1. Final Response Text - Plain Markdown */}
      <div className="prose prose-neutral dark:prose-invert max-w-none">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={markdownComponents}
        >
          {data.response}
        </ReactMarkdown>
      </div>

      {/* 2. Actions Section - Optional */}
      {(data.actions.export_dataframe?.df_id ||
        data.actions.download_plots?.plot_urls) && (
        <div className="flex flex-wrap gap-2 pt-2 border-t border-border/50">
          {data.actions.export_dataframe?.df_id && (
            <Button
              variant="outline"
              size="sm"
              className="gap-2 text-muted-foreground hover:text-foreground hover:border-sidebar-accent border-dashed"
              onClick={handleExport}
              disabled={isExporting}
            >
              {isExporting ? (
                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
              ) : (
                <FileSpreadsheet className="w-4 h-4" />
              )}
              Export Data (XLSX)
            </Button>
          )}

          {data.actions.download_plots?.plot_urls && (
            <Button
              variant="outline"
              size="sm"
              className="gap-2 text-muted-foreground hover:text-foreground hover:border-sidebar-accent border-dashed"
              onClick={handleDownloadPlots}
              disabled={isDownloading}
            >
              {isDownloading ? (
                <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              {data.actions.download_plots?.plot_urls &&
              data.actions.download_plots.plot_urls.length > 1
                ? `Download All Plots (${data.actions.download_plots.plot_urls.length})`
                : "Download Plot"}
            </Button>
          )}
        </div>
      )}

      {/* 3. Next Query Suggestions - Optional */}
      {data.actions.next_queries && data.actions.next_queries.length > 0 && (
        <div className="animate-in fade-in slide-in-from-bottom-2 duration-500 delay-100">
          <div className="flex items-center gap-2 mb-2 text-xs font-medium text-muted-foreground/70 uppercase tracking-wider">
            <Sparkles className="w-3 h-3" />
            Suggested Next Steps
          </div>
          <div className="flex flex-wrap gap-2">
            {data.actions.next_queries.map((query, idx) => (
              <button
                key={idx}
                onClick={() => onSuggestionClick?.(query)}
                className="text-left text-sm px-3 py-1.5 rounded-full bg-muted/50 hover:bg-muted text-muted-foreground hover:text-foreground border border-transparent hover:border-border transition-all duration-200 cursor-pointer"
              >
                {query}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default FinalResponseMessage;
