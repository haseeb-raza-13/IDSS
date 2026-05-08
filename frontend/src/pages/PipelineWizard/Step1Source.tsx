import { FileDropzone } from "@/components/common/FileDropzone";

interface Props {
  files: File[];
  onFilesChange: (f: File[]) => void;
  onNext: () => void;
}

export default function Step1Source({ files, onFilesChange, onNext }: Props) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-base font-medium text-gray-900 mb-1">Upload Genome Files</h2>
        <p className="text-sm text-gray-500">Upload one or more FASTA or FASTQ files from your sequencing run.</p>
      </div>

      <FileDropzone files={files} onFilesChange={onFilesChange} />

      <div className="flex justify-end">
        <button
          onClick={onNext}
          disabled={files.length === 0}
          className="bg-blue-600 text-white px-5 py-2 rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          Next →
        </button>
      </div>
    </div>
  );
}
