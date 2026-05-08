import { useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X } from "lucide-react";

interface Props {
  accept?: Record<string, string[]>;
  multiple?: boolean;
  files: File[];
  onFilesChange: (files: File[]) => void;
  label?: string;
}

const DEFAULT_ACCEPT = {
  "application/octet-stream": [".fasta", ".fa", ".fna", ".fastq", ".fq"],
};

export function FileDropzone({ accept = DEFAULT_ACCEPT, multiple = true, files, onFilesChange, label }: Props) {
  const onDrop = useCallback(
    (accepted: File[]) => {
      onFilesChange(multiple ? [...files, ...accepted] : accepted);
    },
    [files, multiple, onFilesChange]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({ onDrop, accept, multiple });

  function remove(idx: number) {
    onFilesChange(files.filter((_, i) => i !== idx));
  }

  return (
    <div className="space-y-2">
      <div
        {...getRootProps()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
          isDragActive ? "border-blue-400 bg-blue-50" : "border-gray-300 hover:border-gray-400"
        }`}
      >
        <input {...getInputProps()} />
        <Upload className="mx-auto mb-2 text-gray-400" size={28} />
        <p className="text-sm text-gray-600">
          {isDragActive ? "Drop files here…" : (label ?? "Drag & drop files, or click to browse")}
        </p>
        <p className="text-xs text-gray-400 mt-1">
          {Object.values(accept).flat().join(", ")}
        </p>
      </div>

      {files.length > 0 && (
        <ul className="space-y-1">
          {files.map((f, i) => (
            <li key={i} className="flex items-center justify-between text-sm bg-white border rounded px-3 py-1.5">
              <span className="text-gray-700 truncate">{f.name}</span>
              <div className="flex items-center gap-2 ml-2 shrink-0">
                <span className="text-gray-400 text-xs">{(f.size / 1024).toFixed(0)} KB</span>
                <button onClick={() => remove(i)} className="text-gray-400 hover:text-red-500">
                  <X size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
