import { useCallback, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import type { DocumentRecord } from "../state/types";

interface AggregateProgress {
  processed: number;
  total: number;
  percent: number; // 0-100
}

interface DocumentUploaderProps {
  documents: DocumentRecord[];
  onUpload: (files: FileList) => void;
  aggregateProgress?: AggregateProgress;
}

const DocumentUploader = ({
  documents,
  onUpload,
  aggregateProgress,
}: DocumentUploaderProps) => {
  const [isDragging, setIsDragging] = useState(false);

  const handleDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsDragging(false);
      if (event.dataTransfer.files && event.dataTransfer.files.length > 0) {
        onUpload(event.dataTransfer.files);
        event.dataTransfer.clearData();
      }
    },
    [onUpload]
  );

  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) {
      onUpload(event.target.files);
      event.target.value = "";
    }
  };

  return (
    <section
      className="modal-section"
      aria-labelledby="document-uploader-heading"
    >
      <header className="modal-header">
        <h2 id="document-uploader-heading">Document ingestion</h2>
        <p className="muted">Supported formats: PDF, DOCX, TXT, CSV.</p>
        {aggregateProgress && aggregateProgress.total > 0 && (
          <div className="ingest-aggregate">
            <CircularProgress percent={aggregateProgress.percent} />
            <div className="ingest-aggregate-text">
              <div>
                <strong>{aggregateProgress.processed}</strong> /{" "}
                {aggregateProgress.total} processed
              </div>
              <div className="muted" aria-hidden>
                {aggregateProgress.percent.toFixed(0)}%
              </div>
            </div>
          </div>
        )}
      </header>
      <div
        className={`dropzone ${isDragging ? "dropzone-active" : ""}`}
        role="button"
        tabIndex={0}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        aria-label="Document dropzone"
      >
        <p>
          {isDragging
            ? "Release to upload files"
            : "Drag & drop files or click to browse"}
        </p>
        <input
          type="file"
          multiple
          className="dropzone-input"
          onChange={handleFileInput}
        />
      </div>
      <ul className="upload-list">
        {documents.length === 0 ? (
          <li className="muted">No documents uploaded yet.</li>
        ) : (
          documents.map((document) => (
            <li
              key={document.id}
              className={`upload-card status-${document.status}`}
            >
              <div>
                <strong>{document.name}</strong>
                <span className="muted">
                  {Math.round(document.size / 1024)} KB
                </span>
              </div>
              <div className="upload-progress">
                <div
                  className="progress-bar"
                  style={{ width: `${document.progress}%` }}
                />
              </div>
              <span className="status-label">{document.status}</span>
              {document.error && (
                <span className="feedback feedback-error">
                  {document.error}
                </span>
              )}
            </li>
          ))
        )}
      </ul>
    </section>
  );
};

export default DocumentUploader;

function CircularProgress({
  percent,
  size = 48,
  stroke = 6,
}: {
  percent: number;
  size?: number;
  stroke?: number;
}) {
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset =
    circumference * (1 - Math.min(Math.max(percent, 0), 100) / 100);
  return (
    <svg
      className="circular-progress"
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      role="img"
      aria-label={`Ingestion progress ${percent.toFixed(0)} percent`}
    >
      <circle
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#eee"
        strokeWidth={stroke}
      />
      <circle
        className="circular-progress-bar"
        cx={size / 2}
        cy={size / 2}
        r={radius}
        fill="none"
        stroke="#0f0f0f"
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeDasharray={`${circumference} ${circumference}`}
        strokeDashoffset={offset}
        transform={`rotate(-90 ${size / 2} ${size / 2})`}
      />
    </svg>
  );
}
